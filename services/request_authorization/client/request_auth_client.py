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


RECONNECT_BASE_DELAY_S = 1.0
RECONNECT_MAX_DELAY_S = 30.0


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
        self._gen = 0  # bumped on every reconnect; a superseded request iterator hands messages back
        self._failures = 0  # consecutive streams that ended before the server sent anything
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
        self._stream = self._stub.PermitStream(self._request_iter(self._gen))
        t = threading.Thread(target=self._recv_loop, args=(self._stream,), daemon=True)
        t.start()

    def _request_iter(self, gen: int):
        while not self._stopped.is_set() and gen == self._gen:
            try:
                msg = self._send_q.get(timeout=1.0)
            except queue.Empty:
                continue
            if msg is None:
                return
            if gen != self._gen:
                # This stream died while we waited: leave the message for the new one.
                self._send_q.put(msg)
                return
            yield msg

    def _recv_loop(self, stream) -> None:
        try:
            for msg in stream:
                self._failures = 0
                self._recv_loop_step(msg)
            error = "permit stream ended"
        except grpc.RpcError as e:
            error = str(e)
        if self._stopped.is_set():
            self._wake_all_pending(error)
            return
        # The server restarted or the connection dropped. Requests in flight fail (callers retry them);
        # anything queued from now on goes out on the next stream. Without this the client never
        # reconnected and every later acquire() blocked forever (2026-10-30, a request-auth rollout).
        with self._lock:
            self._gen += 1
        self._wake_all_pending(error)
        self._failures += 1
        delay = min(RECONNECT_MAX_DELAY_S, RECONNECT_BASE_DELAY_S * 2 ** (self._failures - 1))
        if self._stopped.wait(delay):
            return
        self._connect()

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
