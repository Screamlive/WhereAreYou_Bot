import hashlib
import hmac
import json
import logging
import os
import time
from collections import deque
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse
from urllib.parse import quote

from aiohttp import web

from config import TOKEN
from database import init_db
from webapp_export import build_overlaps_export_filename, build_overlaps_xlsx
from webapp_readonly import (
    WebAppAccessError,
    get_absence_details_payload,
    get_overlaps_payload,
    get_webapp_profile,
)

WEBAPP_STATIC_DIR = Path(__file__).resolve().parent / "webapp_static"
logger = logging.getLogger(__name__)
try:
    from config import WEBAPP_ALLOW_DEV_FALLBACK as CONFIG_WEBAPP_ALLOW_DEV_FALLBACK
except ImportError:
    CONFIG_WEBAPP_ALLOW_DEV_FALLBACK = False
try:
    from config import WEBAPP_ALLOW_INITDATA_COMPAT as CONFIG_WEBAPP_ALLOW_INITDATA_COMPAT
except ImportError:
    CONFIG_WEBAPP_ALLOW_INITDATA_COMPAT = True
try:
    from config import WEBAPP_HOST as CONFIG_WEBAPP_HOST
except ImportError:
    CONFIG_WEBAPP_HOST = "127.0.0.1"
try:
    from config import WEBAPP_PORT as CONFIG_WEBAPP_PORT
except ImportError:
    CONFIG_WEBAPP_PORT = 8080
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


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _allow_dev_fallback() -> bool:
    return _env_flag("WEBAPP_ALLOW_DEV_FALLBACK", default=bool(CONFIG_WEBAPP_ALLOW_DEV_FALLBACK))


def _allow_initdata_compat() -> bool:
    return _env_flag("WEBAPP_ALLOW_INITDATA_COMPAT", default=bool(CONFIG_WEBAPP_ALLOW_INITDATA_COMPAT))


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


def _status_from_error(exc: WebAppAccessError) -> int:
    return exc.status_code if 400 <= exc.status_code < 600 else 403


def _http_error(exc: WebAppAccessError) -> web.HTTPException:
    status_code = _status_from_error(exc)
    payload = {"error": exc.message}
    if status_code == 400:
        return web.HTTPBadRequest(text=json.dumps(payload), content_type="application/json")
    if status_code == 401:
        return web.HTTPUnauthorized(text=json.dumps(payload), content_type="application/json")
    if status_code == 404:
        return web.HTTPNotFound(text=json.dumps(payload), content_type="application/json")
    return web.HTTPForbidden(text=json.dumps(payload), content_type="application/json")


def _verify_telegram_init_data(init_data: str) -> int:
    normalized_init_data = _normalize_init_data(init_data)
    parsed = dict(parse_qsl(normalized_init_data, keep_blank_values=True))
    provided_hash = parsed.pop("hash", None)
    if not provided_hash:
        raise WebAppAccessError("Отсутствует hash в initData.", status_code=401)

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, provided_hash):
        raise WebAppAccessError("Невалидная подпись initData.", status_code=401)

    auth_date_raw = parsed.get("auth_date")
    if auth_date_raw and auth_date_raw.isdigit():
        now = int(time.time())
        auth_date = int(auth_date_raw)
        if now - auth_date > 24 * 60 * 60:
            raise WebAppAccessError("initData устарел.", status_code=401)

    user_raw = parsed.get("user")
    if not user_raw:
        raise WebAppAccessError("В initData отсутствует user.", status_code=401)
    try:
        user_obj = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise WebAppAccessError("Некорректный user в initData.", status_code=401) from exc

    user_id = user_obj.get("id")
    if not isinstance(user_id, int):
        raise WebAppAccessError("Некорректный user.id в initData.", status_code=401)
    return user_id


def _normalize_init_data(init_data: str) -> str:
    value = (init_data or "").strip()

    # Some clients send Authorization: tma <initData>.
    if value.lower().startswith("tma "):
        value = value[4:].strip()

    # If full launch hash query is passed, extract tgWebAppData.
    if value.startswith("tgWebAppData="):
        parsed = dict(parse_qsl(value, keep_blank_values=True))
        tg_data = parsed.get("tgWebAppData")
        if tg_data:
            value = tg_data

    # Defensive: accept initData encoded one more time as a whole string.
    if "hash=" not in value and ("%26" in value or "%3D" in value):
        decoded = unquote(value)
        if "hash=" in decoded:
            value = decoded

    return value


def _extract_init_data_from_url(raw_url: str | None) -> str:
    if not raw_url:
        return ""
    try:
        parsed = urlparse(raw_url)
    except Exception:
        return ""

    # Query params (normal case).
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key in ("tgWebAppData", "init_data", "initData"):
        value = query_params.get(key)
        if value:
            return value

    # Hash fragment fallback.
    fragment = parsed.fragment or ""
    if fragment.startswith("/?"):
        fragment = fragment[2:]
    elif fragment.startswith("?"):
        fragment = fragment[1:]
    fragment_params = dict(parse_qsl(fragment, keep_blank_values=True))
    for key in ("tgWebAppData", "init_data", "initData"):
        value = fragment_params.get(key)
        if value:
            return value
    return ""


def _extract_user_id(request: web.Request) -> int:
    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header.lower().startswith("tma "):
        return _verify_telegram_init_data(auth_header[4:].strip())

    init_data = (
        request.headers.get("X-Telegram-Init-Data")
    )
    if init_data:
        return _verify_telegram_init_data(init_data)

    referer_raw = request.headers.get("Referer") or ""
    if _allow_initdata_compat():
        init_data_compat = request.query.get("init_data") or request.query.get("tgWebAppData")
        if init_data_compat:
            return _verify_telegram_init_data(init_data_compat)

        cookie_init_data = request.cookies.get("tg_init_data")
        if cookie_init_data:
            return _verify_telegram_init_data(cookie_init_data)

        referer_init_data = _extract_init_data_from_url(referer_raw)
        if referer_init_data:
            return _verify_telegram_init_data(referer_init_data)

    # Dev fallback for local testing without Telegram WebApp.
    if _allow_dev_fallback():
        user_id_raw = request.headers.get("X-Telegram-User-Id")
        if user_id_raw and user_id_raw.isdigit():
            return int(user_id_raw)

    # Do not log raw Referer/query fragments to avoid leaking Telegram launch payloads.
    referer_has_tg = "tgWebAppData=" in referer_raw
    referer_has_init = "init_data=" in referer_raw or "initData=" in referer_raw
    logger.warning(
        (
            "WebApp auth context is missing: path=%s has_auth=%s has_init_header=%s "
            "has_init_cookie=%s has_referer=%s referer_has_tg=%s referer_has_init=%s referer_len=%s ua=%s"
        ),
        request.path,
        bool(auth_header),
        bool(request.headers.get("X-Telegram-Init-Data")),
        bool(request.cookies.get("tg_init_data")),
        bool(referer_raw),
        referer_has_tg,
        referer_has_init,
        len(referer_raw),
        (request.headers.get("User-Agent") or "")[:120],
    )
    raise WebAppAccessError("Не передан Telegram initData.", status_code=401)


def _parse_list_param(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    values = [part.strip() for part in raw.split(",")]
    return [value for value in values if value]


def _parse_int_param(raw: str | None, name: str) -> int | None:
    if raw is None or raw == "":
        return None
    if not raw.isdigit():
        raise WebAppAccessError(f"Параметр {name} должен быть числом.", status_code=400)
    return int(raw)


def _parse_overlaps_query(request: web.Request) -> dict:
    return {
        "scope_type": request.query.get("scope_type"),
        "group_id": _parse_int_param(request.query.get("group_id"), "group_id"),
        "year": _parse_int_param(request.query.get("year"), "year"),
        "start_date": request.query.get("start_date"),
        "end_date": request.query.get("end_date"),
        "statuses": _parse_list_param(request.query.get("statuses")),
        "categories": _parse_list_param(request.query.get("categories")),
        "query": request.query.get("q"),
    }


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


def _clear_rate_limiter_state() -> None:
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


async def handle_me(request: web.Request) -> web.Response:
    try:
        user_id = _extract_user_id(request)
        payload = get_webapp_profile(user_id)
        return web.json_response(payload)
    except WebAppAccessError as exc:
        raise _http_error(exc) from exc


async def handle_overlaps(request: web.Request) -> web.Response:
    try:
        user_id = _extract_user_id(request)
        overlaps_query = _parse_overlaps_query(request)
        payload = get_overlaps_payload(
            user_id=user_id,
            **overlaps_query,
        )
        return web.json_response(payload)
    except WebAppAccessError as exc:
        raise _http_error(exc) from exc


async def handle_export_xlsx(request: web.Request) -> web.Response:
    try:
        user_id = _extract_user_id(request)
        overlaps_query = _parse_overlaps_query(request)
        payload = get_overlaps_payload(
            user_id=user_id,
            **overlaps_query,
        )
        body = build_overlaps_xlsx(payload)
        filename = build_overlaps_export_filename(payload)
        return web.Response(
            body=body,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            },
        )
    except WebAppAccessError as exc:
        raise _http_error(exc) from exc


async def handle_absence(request: web.Request) -> web.Response:
    try:
        user_id = _extract_user_id(request)
        absence_id_raw = request.match_info["absence_id"]
        if not absence_id_raw.isdigit():
            raise WebAppAccessError("absence_id должен быть числом.", status_code=400)
        payload = get_absence_details_payload(user_id, int(absence_id_raw))
        return web.json_response(payload)
    except WebAppAccessError as exc:
        raise _http_error(exc) from exc


async def handle_webapp_index(_request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEBAPP_STATIC_DIR / "index.html")


def create_app() -> web.Application:
    app = web.Application(middlewares=[security_headers_middleware, rate_limit_middleware])
    app.router.add_get("/webapp", handle_webapp_index)
    app.router.add_static("/webapp/static/", path=str(WEBAPP_STATIC_DIR), show_index=False)
    app.router.add_get("/webapp/v1/me", handle_me)
    app.router.add_get("/webapp/v1/overlaps", handle_overlaps)
    app.router.add_get("/webapp/v1/export/xlsx", handle_export_xlsx)
    app.router.add_get("/webapp/v1/absence/{absence_id}", handle_absence)
    return app


def main() -> None:
    init_db()
    host = os.getenv("WEBAPP_HOST", str(CONFIG_WEBAPP_HOST))
    port = int(os.getenv("WEBAPP_PORT", str(CONFIG_WEBAPP_PORT)))
    web.run_app(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
