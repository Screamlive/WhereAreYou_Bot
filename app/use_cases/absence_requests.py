"""Use-cases for absence request presentation and message payloads."""

from utils import format_date_display


def normalize_comment(raw_comment: str) -> str:
    comment = raw_comment.strip()
    if comment == "-":
        return ""
    return comment


def build_user_request_submitted_text(
    absence_id: int,
    category: str,
    start_date: str,
    end_date: str,
    comment: str,
) -> str:
    sd_disp = format_date_display(start_date)
    ed_disp = format_date_display(end_date)
    return (
        f"Заявка #{absence_id} на отсутствие '{category}' с {sd_disp} по {ed_disp}\n"
        f"Комментарий: {comment or '—'}\nОтправлена на рассмотрение."
    )


def build_admin_request_submitted_text(
    requester_fullname: str,
    absence_id: int,
    category: str,
    start_date: str,
    end_date: str,
    comment: str,
    target_fullname: str | None = None,
) -> str:
    sd_disp = format_date_display(start_date)
    ed_disp = format_date_display(end_date)
    if target_fullname:
        return (
            f"{requester_fullname} добавил заявку #{absence_id} "
            f"ДЛЯ {target_fullname}:\n"
            f"{category} {sd_disp}–{ed_disp}\n"
            f"Комментарий: {comment or '—'} (pending)"
        )
    return (
        f"{requester_fullname} добавил заявку #{absence_id}:\n"
        f"{category} {sd_disp}–{ed_disp}\n"
        f"Комментарий: {comment or '—'} (pending)"
    )


def build_added_for_another_text(
    absence_id: int,
    target_fullname: str,
    category: str,
    start_date: str,
    end_date: str,
    comment: str,
) -> str:
    sd_disp = format_date_display(start_date)
    ed_disp = format_date_display(end_date)
    return (
        f"Отсутствие #{absence_id} добавлено пользователю {target_fullname}.\n"
        f"Категория: {category}, {sd_disp}–{ed_disp}\n"
        f"Комментарий: {comment or '—'}\nСтатус: pending."
    )


def build_target_user_added_text(
    absence_id: int,
    category: str,
    start_date: str,
    end_date: str,
    comment: str,
) -> str:
    sd_disp = format_date_display(start_date)
    ed_disp = format_date_display(end_date)
    return (
        f"Вам добавлено отсутствие #{absence_id} ({category}, {sd_disp}–{ed_disp}) от другого пользователя.\n"
        f"Комментарий: {comment or '—'}\n(статус: pending)"
    )
