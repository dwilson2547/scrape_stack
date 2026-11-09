from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

_client = None


def get_client():
    return _client


def init_client(address: str) -> None:
    global _client
    try:
        from request_auth_client import RequestAuthClient
        _client = RequestAuthClient(address)
        _log.info("request_auth client connected to %s", address)
    except Exception as exc:
        _log.warning("request_auth client unavailable (%s) — server-side download disabled", exc)


def override_client(instance) -> None:
    global _client
    _client = instance


def reset_client() -> None:
    global _client
    _client = None
