"""HTTP-level middlewares/helpers for WebApp API."""

import json
import os
import time
from collections import deque

from aiohttp import web

try:
    from config import WEBAPP_RATE_LIMIT_MAX_REQUESTS as CONFIG_WEBAPP_RATE_LIMIT_MAX_REQUESTS
except ImportError:
    CONFIG_WEBAPP_RATE_LIMIT_MAX_REQUESTS = 120
try:
    from config import WEBAPP_RATE_LIMIT_WINDOW_SEC as CONFIG_WEBAPP_RATE_LIMIT_WINDOW_SEC
except ImportError:
    CONFIG_WEBAPP_RATE_LIMIT_WINDOW_SEC = 60

_RATE_LIMIT_BUCKETS: dict[str, deque[float]] = {}
_RATE_LIMIT_LAST_CLEANUP_AT = 0.0


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default


def _rate_limit_window_sec() -> int:
    return max(0, _env_int("WEBAPP_RATE_LIMIT_WINDOW_SEC", int(CONFIG_WEBAPP_RATE_LIMIT_WINDOW_SEC)))


def _rate_limit_max_requests() -> int:
    return max(0, _env_int("WEBAPP_RATE_LIMIT_MAX_REQUESTS", int(CONFIG_WEBAPP_RATE_LIMIT_MAX_REQUESTS)))


def _extract_client_ip(request: web.Request) -> str:
    cloudflare_ip = (request.headers.get("CF-Connecting-IP") or "").strip()
    if cloudflare_ip:
        return cloudflare_ip

    forwarded_for = request.headers.get("X-Forwarded-For") or ""
    if forwarded_for:
        first_ip = forwarded_for.split(",")[0].strip()
        if first_ip:
            return first_ip

    real_ip = (request.headers.get("X-Real-IP") or "").strip()
    if real_ip:
        return real_ip

    if request.remote:
        return request.remote
    return "unknown"


def _maybe_cleanup_rate_limit_buckets(now_ts: float, window_sec: int) -> None:
    global _RATE_LIMIT_LAST_CLEANUP_AT
    cleanup_interval = max(window_sec, 30)
    if now_ts - _RATE_LIMIT_LAST_CLEANUP_AT < cleanup_interval:
        return

    stale_before = now_ts - (window_sec * 2)
    stale_keys = []
    for key, bucket in _RATE_LIMIT_BUCKETS.items():
        while bucket and bucket[0] < stale_before:
            bucket.popleft()
        if not bucket:
            stale_keys.append(key)
    for key in stale_keys:
        _RATE_LIMIT_BUCKETS.pop(key, None)
    _RATE_LIMIT_LAST_CLEANUP_AT = now_ts


def _consume_rate_limit_slot(client_key: str, now_ts: float, limit: int, window_sec: int) -> int | None:
    bucket = _RATE_LIMIT_BUCKETS.setdefault(client_key, deque())
    threshold = now_ts - window_sec
    while bucket and bucket[0] <= threshold:
        bucket.popleft()

    if len(bucket) >= limit:
        retry_after = max(1, int(window_sec - (now_ts - bucket[0])) + 1)
        return retry_after

    bucket.append(now_ts)
    _maybe_cleanup_rate_limit_buckets(now_ts, window_sec)
    return None


def clear_rate_limiter_state() -> None:
    global _RATE_LIMIT_LAST_CLEANUP_AT
    _RATE_LIMIT_BUCKETS.clear()
    _RATE_LIMIT_LAST_CLEANUP_AT = 0.0


@web.middleware
async def security_headers_middleware(request: web.Request, handler):
    try:
        response = await handler(request)
    except web.HTTPException as exc:
        response = exc
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        (
            "default-src 'self'; "
            "script-src 'self' https://telegram.org; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org; "
            "base-uri 'none'; form-action 'none'"
        ),
    )
    return response


@web.middleware
async def rate_limit_middleware(request: web.Request, handler):
    if not request.path.startswith("/webapp/v1/"):
        return await handler(request)

    window_sec = _rate_limit_window_sec()
    max_requests = _rate_limit_max_requests()
    if window_sec <= 0 or max_requests <= 0:
        return await handler(request)

    now_ts = time.time()
    client_key = _extract_client_ip(request)
    retry_after = _consume_rate_limit_slot(client_key, now_ts, max_requests, window_sec)
    if retry_after is not None:
        raise web.HTTPTooManyRequests(
            text=json.dumps({"error": "Слишком много запросов к WebApp API. Повторите позже."}),
            content_type="application/json",
            headers={"Retry-After": str(retry_after)},
        )

    return await handler(request)

