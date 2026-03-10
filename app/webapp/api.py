"""WebApp API handlers and application factory."""

import json
import logging
from pathlib import Path
from urllib.parse import quote

from aiohttp import web

from app.webapp import auth as webapp_auth
from app.webapp.downloads import consume_download_ticket, issue_download_ticket
from app.webapp.export import build_overlaps_export_filename, build_overlaps_xlsx
from app.webapp.http import rate_limit_middleware, security_headers_middleware
from app.webapp.service import (
    WebAppAccessError,
    get_absence_details_payload,
    get_overlaps_payload,
    get_webapp_profile,
)
from app.webapp.validation import parse_absence_id, parse_overlaps_query

WEBAPP_STATIC_DIR = Path(__file__).resolve().parents[2] / "webapp_static"
# Keep legacy logger name to preserve existing log filters/alerts.
logger = logging.getLogger("webapp_api")

# Use a single logger object for auth warnings and API layer logs.
webapp_auth.logger = logger


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


def _build_xlsx_response(payload: dict) -> web.Response:
    body = build_overlaps_xlsx(payload)
    filename = build_overlaps_export_filename(payload)
    return web.Response(
        body=body,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


async def handle_me(request: web.Request) -> web.Response:
    try:
        user_id = webapp_auth.extract_user_id(request)
        payload = get_webapp_profile(user_id)
        return web.json_response(payload)
    except WebAppAccessError as exc:
        raise _http_error(exc) from exc


async def handle_overlaps(request: web.Request) -> web.Response:
    try:
        user_id = webapp_auth.extract_user_id(request)
        overlaps_query = parse_overlaps_query(request)
        payload = get_overlaps_payload(user_id=user_id, **overlaps_query)
        return web.json_response(payload)
    except WebAppAccessError as exc:
        raise _http_error(exc) from exc


async def handle_export_xlsx(request: web.Request) -> web.Response:
    try:
        download_token = request.query.get("download_token")
        if download_token:
            ticket = consume_download_ticket(download_token)
            if not ticket:
                raise WebAppAccessError("Ссылка на экспорт недействительна или устарела.", status_code=401)
            payload = get_overlaps_payload(
                user_id=ticket["user_id"],
                **ticket["overlaps_query"],
            )
            return _build_xlsx_response(payload)

        user_id = webapp_auth.extract_user_id(request)
        overlaps_query = parse_overlaps_query(request)
        payload = get_overlaps_payload(user_id=user_id, **overlaps_query)
        return _build_xlsx_response(payload)
    except WebAppAccessError as exc:
        raise _http_error(exc) from exc


async def handle_export_xlsx_ticket(request: web.Request) -> web.Response:
    try:
        user_id = webapp_auth.extract_user_id(request)
        overlaps_query = parse_overlaps_query(request)
        payload = get_overlaps_payload(user_id=user_id, **overlaps_query)
        token = issue_download_ticket(user_id=user_id, overlaps_query=overlaps_query)
        filename = build_overlaps_export_filename(payload)
        return web.json_response(
            {
                "download_url": f"/webapp/v1/export/xlsx?download_token={quote(token)}",
                "filename": filename,
                "expires_in": 60,
            }
        )
    except WebAppAccessError as exc:
        raise _http_error(exc) from exc


async def handle_absence(request: web.Request) -> web.Response:
    try:
        user_id = webapp_auth.extract_user_id(request)
        absence_id = parse_absence_id(request.match_info["absence_id"])
        payload = get_absence_details_payload(user_id, absence_id)
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
    app.router.add_get("/webapp/v1/export/xlsx-ticket", handle_export_xlsx_ticket)
    app.router.add_get("/webapp/v1/export/xlsx", handle_export_xlsx)
    app.router.add_get("/webapp/v1/absence/{absence_id}", handle_absence)
    return app
