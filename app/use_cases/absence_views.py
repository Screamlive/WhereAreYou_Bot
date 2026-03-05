"""Use-cases for absence list/report rendering."""

from utils import format_date_display


def build_my_absences_report(rows: list[tuple]) -> str:
    lines = []
    for abs_id, category, start_date, end_date, comment, status in rows:
        start_disp = format_date_display(start_date)
        end_disp = format_date_display(end_date)
        line = (
            f"#{abs_id} — {category}, {start_disp}–{end_disp}, "
            f"статус={status}, коммент: {comment or '—'}"
        )
        lines.append(line)
    return "Ваши заявки:\n" + "\n".join(lines)


def build_user_absences_report(user_fullname: str, rows: list[tuple]) -> str:
    lines = [f"Отсутствия {user_fullname}:"]
    for _abs_id, category, start_date, end_date, comment, status in rows:
        start_disp = format_date_display(start_date)
        end_disp = format_date_display(end_date)
        lines.append(f"- {category} {start_disp}–{end_disp}, [{status}], {comment or '—'}")
    return "\n".join(lines) + "\n"


def build_admin_delete_absences_report(user_fullname: str, rows: list[tuple]) -> str:
    lines = [f"Отсутствия {user_fullname}:"]
    for abs_id, category, start_date, end_date, comment, status in rows:
        start_disp = format_date_display(start_date)
        end_disp = format_date_display(end_date)
        lines.append(f"#{abs_id} {category} {start_disp}–{end_disp}, [{status}], {comment or '—'}")
    return "\n".join(lines) + "\n"


def build_admin_edit_absence_label(
    absence_id: int,
    category: str,
    start_date: str,
    end_date: str,
    status: str,
) -> str:
    start_disp = format_date_display(start_date)
    end_disp = format_date_display(end_date)
    return f"#{absence_id} {category} {start_disp}–{end_disp} [{status}]"


def build_admin_edit_current_text(
    category: str,
    start_date: str,
    end_date: str,
    comment: str,
    status: str,
) -> str:
    start_disp = format_date_display(start_date)
    end_disp = format_date_display(end_date)
    return (
        f"Текущие данные: {category} {start_disp}–{end_disp}, "
        f"коммент: {comment or '—'}, статус={status}\n"
        "Выберите новую категорию (можно выбрать ту же):"
    )

