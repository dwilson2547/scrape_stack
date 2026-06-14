"""
Sync Python client for the Request Authorization gRPC service.

Usage::

    from request_auth_client import RequestAuthClient

    client = RequestAuthClient("localhost:9000")

    # Explicit release
    permit = client.acquire("rockauto.com")
    try:
        response = requests.get(url)
        permit.release(response.status_code)
    except Exception:
        permit.release(0)

    # Context manager (preferred — auto-releases with status 0 on exception)
    with client.acquire("rockauto.com") as permit:
        response = requests.get(url)
        permit.set_status(response.status_code)
"""

import queue
import threading
from typing import Optional

import grpc

from request_auth_proto import permit_pb2
from request_auth_proto import permit_pb2_grpc


class RequestAuthClient:
    """Manages one gRPC bidirectional stream to the permit server.

    Thread-safe. Multiple threads can call acquire() concurrently;
    each blocks independently until the server issues a grant.
    """

    def __init__(self, address: str, insecure: bool = True) -> None:
        self._address = address
        if insecure:
            self._channel = grpc.insecure_channel(address)
        else:
            self._channel = grpc.secure_channel(address, grpc.ssl_channel_credentials())
        self._stub = permit_pb2_grpc.PermitServiceStub(self._channel)

        self._lock = threading.Lock()
        self._req_id = 0
        self._pending: dict[int, queue.Queue] = {}
        self._send_q: queue.Queue = queue.Queue()
        self._stopped = threading.Event()
        self._connect()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def acquire(self, domain: str) -> "Permit":
        """Block until the server grants a permit for domain."""
        with self._lock:
            self._req_id += 1
            req_id = self._req_id
            result_q: queue.Queue = queue.Queue()
            self._pending[req_id] = result_q

        self._send_q.put(permit_pb2.ClientMessage(
            request=permit_pb2.PermitRequest(domain=domain, req_id=req_id)
        ))

        kind, payload = result_q.get()
        if kind == "error":
            raise RuntimeError(f"permit acquisition failed for {domain!r}: {payload}")
        return Permit(permit_id=payload.permit_id, client=self)

    def close(self) -> None:
        self._stopped.set()
        self._send_q.put(None)  # unblock the request iterator
        self._channel.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _release(self, permit_id: str, status_code: int) -> None:
        self._send_q.put(permit_pb2.ClientMessage(
            ret=permit_pb2.PermitReturn(permit_id=permit_id, status_code=status_code)
        ))

    def _connect(self) -> None:
        self._stream = self._stub.PermitStream(self._request_iter())
        t = threading.Thread(target=self._recv_loop, daemon=True)
        t.start()

    def _request_iter(self):
        while not self._stopped.is_set():
            try:
                msg = self._send_q.get(timeout=1.0)
                if msg is None:
                    return
                yield msg
            except queue.Empty:
                continue

    def _recv_loop(self) -> None:
        try:
            for msg in self._stream:
                self._recv_loop_step(msg)
        except grpc.RpcError as e:
            self._wake_all_pending(str(e))

    def _recv_loop_step(self, msg) -> None:
        if msg.HasField("grant"):
            with self._lock:
                q = self._pending.pop(msg.grant.req_id, None)
            if q:
                q.put(("grant", msg.grant))
        elif msg.HasField("error"):
            with self._lock:
                q = self._pending.pop(msg.error.req_id, None)
            if q:
                q.put(("error", msg.error.message))

    def _wake_all_pending(self, error_msg: str) -> None:
        with self._lock:
            pending = dict(self._pending)
            self._pending.clear()
        for q in pending.values():
            q.put(("error", error_msg))


class Permit:
    """Handle returned by RequestAuthClient.acquire().

    Call release(status_code) when done, or use as a context manager.
    """

    def __init__(self, permit_id: str, client: RequestAuthClient) -> None:
        self._permit_id = permit_id
        self._client = client
        self._status_code: int = 0
        self._released = False

    def set_status(self, status_code: int) -> None:
        """Set the HTTP status code to report when the permit is released."""
        self._status_code = status_code

    def release(self, status_code: Optional[int] = None) -> None:
        """Release the permit back to the server."""
        if self._released:
            return
        self._released = True
        code = status_code if status_code is not None else self._status_code
        self._client._release(self._permit_id, code)

    def __enter__(self) -> "Permit":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
