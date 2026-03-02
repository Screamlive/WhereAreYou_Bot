import datetime

from db_repo import (
    get_absence_with_user,
    get_group_name,
    get_last_group_id,
    get_user_group_ids,
    get_user_groups,
    get_user_name_and_username,
    is_user_admin,
    is_user_approved,
    list_absences_for_period,
    list_all_groups,
    user_exists_in_db,
)

VALID_SCOPE_TYPES = {"global", "group", "superadmins"}
VALID_ABSENCE_STATUSES = {"pending", "approved", "declined"}
VALID_ABSENCE_CATEGORIES = {"vacation", "sick", "dayoff", "other"}
DEFAULT_TIMELINE_STATUSES = ["approved", "pending"]


class WebAppAccessError(Exception):
    def __init__(self, message: str, status_code: int = 403):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _ensure_user_can_use_webapp(user_id: int) -> None:
    if not user_exists_in_db(user_id):
        raise WebAppAccessError("Пользователь не найден.", status_code=404)
    if not is_user_approved(user_id):
        raise WebAppAccessError("Пользователь не одобрен.", status_code=403)


def _normalize_year(year: int | None) -> int:
    current_year = datetime.date.today().year
    if year is None:
        return current_year
    if year < 2000 or year > 2100:
        raise WebAppAccessError("Некорректный год.", status_code=400)
    return year


def _year_bounds(year: int) -> tuple[str, str]:
    return f"{year}-01-01", f"{year}-12-31"


def _normalize_filter(
    values: list[str] | None,
    allowed: set[str],
    default: list[str] | None = None,
) -> list[str]:
    if values is None:
        return list(default or [])
    normalized = sorted({value.strip().lower() for value in values if value and value.strip()})
    invalid = [value for value in normalized if value not in allowed]
    if invalid:
        raise WebAppAccessError(f"Некорректный фильтр: {', '.join(invalid)}", status_code=400)
    return normalized


def _profile_role(user_groups: list[tuple[int, str, str]], is_superadmin: bool) -> str:
    if is_superadmin:
        return "superadmin"
    if any(role == "admin" for _gid, _name, role in user_groups):
        return "group_admin"
    if any(role == "viewer" for _gid, _name, role in user_groups):
        return "group_viewer"
    return "user"


def get_webapp_profile(user_id: int) -> dict:
    _ensure_user_can_use_webapp(user_id)

    user_row = get_user_name_and_username(user_id)
    fullname, username = user_row if user_row else (f"User {user_id}", "")
    user_groups = get_user_groups(user_id)
    superadmin = is_user_admin(user_id)
    role = _profile_role(user_groups, superadmin)

    if superadmin:
        groups = [{"id": gid, "name": name, "role": "all"} for gid, name in list_all_groups()]
        group_ids = {group["id"] for group in groups}
        last_group_id = get_last_group_id(user_id)
        if last_group_id in group_ids:
            default_scope = {"type": "group", "group_id": last_group_id}
        else:
            default_scope = {"type": "global", "group_id": None}
        scopes = ["global", "group", "superadmins"]
    else:
        groups = [{"id": gid, "name": name, "role": role_name} for gid, name, role_name in user_groups]
        group_ids = {group["id"] for group in groups}
        last_group_id = get_last_group_id(user_id)
        default_group_id = None
        if group_ids:
            default_group_id = last_group_id if last_group_id in group_ids else groups[0]["id"]
        default_scope = {"type": "group", "group_id": default_group_id}
        scopes = ["group"]

    return {
        "user": {
            "id": user_id,
            "fullname": fullname,
            "username": username or "",
        },
        "role": role,
        "scopes": scopes,
        "groups": groups,
        "default_scope": default_scope,
    }


def resolve_webapp_scope(user_id: int, scope_type: str | None, group_id: int | None) -> tuple[str, int | None]:
    profile = get_webapp_profile(user_id)
    superadmin = profile["role"] == "superadmin"
    normalized_scope = (scope_type or profile["default_scope"]["type"]).strip().lower()

    if normalized_scope not in VALID_SCOPE_TYPES:
        raise WebAppAccessError("Некорректный scope.", status_code=400)

    if superadmin:
        if normalized_scope == "group":
            target_group_id = group_id or profile["default_scope"]["group_id"]
            if target_group_id is None:
                raise WebAppAccessError("Не выбрана группа.", status_code=400)
            known_group_ids = {item["id"] for item in profile["groups"]}
            if target_group_id not in known_group_ids:
                raise WebAppAccessError("Группа не найдена.", status_code=404)
            return "group", target_group_id
        return normalized_scope, None

    if normalized_scope != "group":
        raise WebAppAccessError("Недостаточно прав для выбранного scope.", status_code=403)

    allowed_group_ids = {item["id"] for item in profile["groups"]}
    if not allowed_group_ids:
        raise WebAppAccessError("Пользователь не состоит в группах.", status_code=403)

    target_group_id = group_id or profile["default_scope"]["group_id"]
    if target_group_id not in allowed_group_ids:
        raise WebAppAccessError("Нет доступа к выбранной группе.", status_code=403)
    return "group", target_group_id


def get_overlaps_payload(
    user_id: int,
    scope_type: str | None = None,
    group_id: int | None = None,
    year: int | None = None,
    statuses: list[str] | None = None,
    categories: list[str] | None = None,
    query: str | None = None,
) -> dict:
    resolved_scope, resolved_group_id = resolve_webapp_scope(user_id, scope_type, group_id)
    normalized_year = _normalize_year(year)
    start_date, end_date = _year_bounds(normalized_year)

    normalized_statuses = _normalize_filter(
        statuses,
        VALID_ABSENCE_STATUSES,
        default=DEFAULT_TIMELINE_STATUSES,
    )
    normalized_categories = _normalize_filter(categories, VALID_ABSENCE_CATEGORIES, default=[])

    rows = list_absences_for_period(
        start_date=start_date,
        end_date=end_date,
        statuses=normalized_statuses,
        categories=normalized_categories,
        group_id=resolved_group_id if resolved_scope == "group" else None,
        only_superadmins=resolved_scope == "superadmins",
        search_query=query,
    )

    users_by_id: dict[int, dict] = {}
    intervals: list[dict] = []
    for abs_id, absent_user_id, fullname, username, category, abs_start, abs_end, comment, status in rows:
        users_by_id.setdefault(
            absent_user_id,
            {
                "user_id": absent_user_id,
                "fullname": fullname,
                "username": username or "",
            },
        )
        intervals.append(
            {
                "absence_id": abs_id,
                "user_id": absent_user_id,
                "category": category,
                "start_date": abs_start,
                "end_date": abs_end,
                "comment": comment or "",
                "status": status,
            }
        )

    scope_payload = {"type": resolved_scope, "group_id": resolved_group_id}
    if resolved_scope == "group" and resolved_group_id is not None:
        scope_payload["group_name"] = get_group_name(resolved_group_id) or f"ID={resolved_group_id}"

    return {
        "scope": scope_payload,
        "period": {
            "year": normalized_year,
            "start_date": start_date,
            "end_date": end_date,
        },
        "filters": {
            "statuses": normalized_statuses,
            "categories": normalized_categories,
            "query": (query or "").strip(),
        },
        "users": sorted(users_by_id.values(), key=lambda item: item["fullname"]),
        "intervals": intervals,
        "meta": {
            "total_users": len(users_by_id),
            "total_intervals": len(intervals),
        },
    }


def get_absence_details_payload(user_id: int, absence_id: int) -> dict:
    _ensure_user_can_use_webapp(user_id)

    row = get_absence_with_user(absence_id)
    if not row:
        raise WebAppAccessError("Отсутствие не найдено.", status_code=404)

    abs_id, absent_user_id, category, start_date, end_date, comment, status, fullname, username = row

    if not is_user_admin(user_id):
        requester_groups = set(get_user_group_ids(user_id))
        if not requester_groups:
            raise WebAppAccessError("Нет доступа к отсутствию.", status_code=403)
        absent_user_groups = set(get_user_group_ids(absent_user_id))
        if not requester_groups.intersection(absent_user_groups):
            raise WebAppAccessError("Нет доступа к отсутствию.", status_code=403)

    return {
        "absence_id": abs_id,
        "user": {
            "id": absent_user_id,
            "fullname": fullname,
            "username": username or "",
        },
        "category": category,
        "start_date": start_date,
        "end_date": end_date,
        "comment": comment or "",
        "status": status,
    }
