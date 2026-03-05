import json
import logging
from pathlib import Path
from urllib.parse import quote

from aiohttp import web

from app.webapp import auth as webapp_auth
from app.webapp.http import (
    clear_rate_limiter_state as _clear_rate_limiter_state,
    rate_limit_middleware,
    security_headers_middleware,
)
from webapp_export import build_overlaps_export_filename, build_overlaps_xlsx
from webapp_readonly import (
    WebAppAccessError,
    get_absence_details_payload,
    get_overlaps_payload,
    get_webapp_profile,
)

WEBAPP_STATIC_DIR = Path(__file__).resolve().parent / "webapp_static"
logger = logging.getLogger(__name__)

# Keep shared logger wiring so tests patching webapp_api.logger still capture auth warnings.
webapp_auth.logger = logger


# Compatibility aliases for existing tests/imports.
_verify_telegram_init_data = webapp_auth.verify_telegram_init_data
_normalize_init_data = webapp_auth.normalize_init_data
_extract_init_data_from_url = webapp_auth.extract_init_data_from_url
_extract_user_id = webapp_auth.extract_user_id


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
    app = web.Application(middlewares=[security_headers_middleware, rate_limit_middleware])
    app.router.add_get("/webapp", handle_webapp_index)
    app.router.add_static("/webapp/static/", path=str(WEBAPP_STATIC_DIR), show_index=False)
    app.router.add_get("/webapp/v1/me", handle_me)
    app.router.add_get("/webapp/v1/overlaps", handle_overlaps)
    app.router.add_get("/webapp/v1/export/xlsx", handle_export_xlsx)
    app.router.add_get("/webapp/v1/absence/{absence_id}", handle_absence)
    return app


def main() -> None:
    # Thin wrapper for backward compatibility with "python webapp_api.py".
    from app.entrypoints.webapp_main import main as run_main

    run_main()


if __name__ == "__main__":
    main()
