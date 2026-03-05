"""Validation helpers for WebApp API request parameters."""

from aiohttp import web

from app.webapp.service import WebAppAccessError


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


def parse_overlaps_query(request: web.Request) -> dict:
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


def parse_absence_id(absence_id_raw: str) -> int:
    if not absence_id_raw.isdigit():
        raise WebAppAccessError("absence_id должен быть числом.", status_code=400)
    return int(absence_id_raw)

