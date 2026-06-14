"""Unit tests for RequestAuthClient using a mock gRPC stream."""
import queue
import threading
import unittest
from unittest.mock import MagicMock, patch

import request_auth_client as request_auth_module
from request_auth_client import Permit, RequestAuthClient

permit_pb2 = request_auth_module.permit_pb2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_grant(req_id: int, permit_id: str = "test-permit") -> permit_pb2.ServerMessage:
    return permit_pb2.ServerMessage(
        grant=permit_pb2.PermitGrant(permit_id=permit_id, req_id=req_id, ttl_ms=1000)
    )


def make_error(req_id: int, msg: str = "boom") -> permit_pb2.ServerMessage:
    return permit_pb2.ServerMessage(
        error=permit_pb2.ServerError(req_id=req_id, message=msg)
    )


class FakeStream:
    """Simulates the server-side of the bidirectional stream."""

    def __init__(self, responses: list):
        self._responses = iter(responses)
        self.sent: list[permit_pb2.ClientMessage] = []

    def __iter__(self):
        return self._responses

    def write(self, msg):
        self.sent.append(msg)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPermit(unittest.TestCase):
    def _make_permit(self, permit_id="abc"):
        client = MagicMock()
        return Permit(permit_id=permit_id, client=client), client

    def test_release_calls_client(self):
        permit, client = self._make_permit()
        permit.release(200)
        client._release.assert_called_once_with("abc", 200)

    def test_release_only_once(self):
        permit, client = self._make_permit()
        permit.release(200)
        permit.release(200)
        client._release.assert_called_once()

    def test_set_status_used_on_exit(self):
        permit, client = self._make_permit()
        permit.set_status(404)
        permit.__exit__(None, None, None)
        client._release.assert_called_once_with("abc", 404)

    def test_context_manager_releases_on_exception(self):
        permit, client = self._make_permit()
        try:
            with permit:
                raise ValueError("oops")
        except ValueError:
            pass
        client._release.assert_called_once_with("abc", 0)

    def test_context_manager_releases_status(self):
        permit, client = self._make_permit()
        with permit:
            permit.set_status(200)
        client._release.assert_called_once_with("abc", 200)


class TestRequestAuthClientRecvLoop(unittest.TestCase):
    """Test _recv_loop by feeding messages directly into _pending."""

    def _make_client_no_grpc(self):
        """Create a client without starting a real gRPC connection."""
        with patch("grpc.insecure_channel"), \
             patch.object(RequestAuthClient, "_connect"):
            client = RequestAuthClient("localhost:9000")
        return client

    def test_grant_unblocks_pending(self):
        client = self._make_client_no_grpc()
        result_q: queue.Queue = queue.Queue()
        client._pending[1] = result_q

        grant_msg = make_grant(req_id=1, permit_id="permit-xyz")
        client._recv_loop_step(grant_msg)

        kind, payload = result_q.get_nowait()
        self.assertEqual(kind, "grant")
        self.assertEqual(payload.permit_id, "permit-xyz")

    def test_error_unblocks_pending(self):
        client = self._make_client_no_grpc()
        result_q: queue.Queue = queue.Queue()
        client._pending[2] = result_q

        err_msg = make_error(req_id=2, msg="unknown domain")
        client._recv_loop_step(err_msg)

        kind, payload = result_q.get_nowait()
        self.assertEqual(kind, "error")
        self.assertIn("unknown domain", payload)

    def test_wake_all_pending_on_disconnect(self):
        client = self._make_client_no_grpc()
        q1: queue.Queue = queue.Queue()
        q2: queue.Queue = queue.Queue()
        client._pending[1] = q1
        client._pending[2] = q2

        client._wake_all_pending("stream disconnected")

        for q in (q1, q2):
            kind, _ = q.get_nowait()
            self.assertEqual(kind, "error")
        self.assertEqual(len(client._pending), 0)


if __name__ == "__main__":
    unittest.main()
