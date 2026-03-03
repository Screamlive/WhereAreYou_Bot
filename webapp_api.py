import hashlib
import hmac
import json
import logging
import os
import time
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


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _allow_dev_fallback() -> bool:
    return _env_flag("WEBAPP_ALLOW_DEV_FALLBACK", default=bool(CONFIG_WEBAPP_ALLOW_DEV_FALLBACK))


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
        or request.query.get("init_data")
        or request.query.get("tgWebAppData")
    )
    if init_data:
        return _verify_telegram_init_data(init_data)

    cookie_init_data = request.cookies.get("tg_init_data")
    if cookie_init_data:
        return _verify_telegram_init_data(cookie_init_data)

    referer_raw = request.headers.get("Referer") or ""
    referer_init_data = _extract_init_data_from_url(referer_raw)
    if referer_init_data:
        return _verify_telegram_init_data(referer_init_data)

    # Dev fallback for local testing without Telegram WebApp.
    if _allow_dev_fallback():
        user_id_raw = request.headers.get("X-Telegram-User-Id")
        if user_id_raw and user_id_raw.isdigit():
            return int(user_id_raw)

    logger.warning(
        (
            "WebApp auth context is missing: path=%s has_auth=%s has_init_header=%s "
            "has_init_cookie=%s has_referer=%s referer_has_tg=%s referer_has_init=%s referer_len=%s referer=%s ua=%s"
        ),
        request.path_qs,
        bool(auth_header),
        bool(request.headers.get("X-Telegram-Init-Data")),
        bool(request.cookies.get("tg_init_data")),
        bool(referer_raw),
        "tgWebAppData=" in referer_raw,
        "init_data=" in referer_raw or "initData=" in referer_raw,
        len(referer_raw),
        referer_raw[:200],
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
    app = web.Application()
    app.router.add_get("/webapp", handle_webapp_index)
    app.router.add_static("/webapp/static/", path=str(WEBAPP_STATIC_DIR), show_index=False)
    app.router.add_get("/webapp/v1/me", handle_me)
    app.router.add_get("/webapp/v1/overlaps", handle_overlaps)
    app.router.add_get("/webapp/v1/export/xlsx", handle_export_xlsx)
    app.router.add_get("/webapp/v1/absence/{absence_id}", handle_absence)
    return app


def main() -> None:
    init_db()
    port = int(os.getenv("WEBAPP_PORT", "8080"))
    web.run_app(create_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
