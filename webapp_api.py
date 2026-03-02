import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web

from config import TOKEN
from database import init_db
from webapp_readonly import (
    WebAppAccessError,
    get_absence_details_payload,
    get_overlaps_payload,
    get_webapp_profile,
)

WEBAPP_STATIC_DIR = Path(__file__).resolve().parent / "webapp_static"


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
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
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


def _extract_user_id(request: web.Request) -> int:
    init_data = request.headers.get("X-Telegram-Init-Data") or request.query.get("init_data")
    if init_data:
        return _verify_telegram_init_data(init_data)

    # Dev fallback for local testing without Telegram WebApp.
    user_id_raw = request.headers.get("X-Telegram-User-Id")
    if user_id_raw and user_id_raw.isdigit():
        return int(user_id_raw)

    raise WebAppAccessError("Не передан контекст пользователя.", status_code=401)


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
        scope_type = request.query.get("scope_type")
        group_id = _parse_int_param(request.query.get("group_id"), "group_id")
        year = _parse_int_param(request.query.get("year"), "year")
        statuses = _parse_list_param(request.query.get("statuses"))
        categories = _parse_list_param(request.query.get("categories"))
        query = request.query.get("q")

        payload = get_overlaps_payload(
            user_id=user_id,
            scope_type=scope_type,
            group_id=group_id,
            year=year,
            statuses=statuses,
            categories=categories,
            query=query,
        )
        return web.json_response(payload)
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
    app.router.add_get("/webapp/v1/absence/{absence_id}", handle_absence)
    return app


def main() -> None:
    init_db()
    port = int(os.getenv("WEBAPP_PORT", "8080"))
    web.run_app(create_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
