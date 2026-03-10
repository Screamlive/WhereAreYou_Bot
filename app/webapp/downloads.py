"""Short-lived one-time download tickets for WebApp file exports."""

from __future__ import annotations

import secrets
import time
from threading import Lock


_DOWNLOAD_TICKETS: dict[str, dict] = {}
_DOWNLOAD_TICKETS_LOCK = Lock()
_DEFAULT_TTL_SEC = 60


def _cleanup_expired_locked(now_ts: float) -> None:
    expired_tokens = [
        token
        for token, ticket in _DOWNLOAD_TICKETS.items()
        if float(ticket.get("expires_at", 0)) <= now_ts
    ]
    for token in expired_tokens:
        _DOWNLOAD_TICKETS.pop(token, None)


def _copy_overlaps_query(overlaps_query: dict) -> dict:
    copied: dict = {}
    for key, value in overlaps_query.items():
        if isinstance(value, list):
            copied[key] = list(value)
        else:
            copied[key] = value
    return copied


def issue_download_ticket(user_id: int, overlaps_query: dict, ttl_sec: int = _DEFAULT_TTL_SEC) -> str:
    now_ts = time.time()
    ttl = max(5, int(ttl_sec))
    token = secrets.token_urlsafe(32)
    ticket = {
        "user_id": int(user_id),
        "overlaps_query": _copy_overlaps_query(overlaps_query),
        "expires_at": now_ts + ttl,
    }
    with _DOWNLOAD_TICKETS_LOCK:
        _cleanup_expired_locked(now_ts)
        _DOWNLOAD_TICKETS[token] = ticket
    return token


def consume_download_ticket(token: str | None) -> dict | None:
    normalized = (token or "").strip()
    if not normalized:
        return None

    now_ts = time.time()
    with _DOWNLOAD_TICKETS_LOCK:
        _cleanup_expired_locked(now_ts)
        ticket = _DOWNLOAD_TICKETS.pop(normalized, None)
    if not ticket:
        return None
    if float(ticket.get("expires_at", 0)) <= now_ts:
        return None
    return ticket


def clear_download_ticket_store() -> None:
    with _DOWNLOAD_TICKETS_LOCK:
        _DOWNLOAD_TICKETS.clear()
