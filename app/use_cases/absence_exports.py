"""Use-cases for absence export/report rendering."""

from utils import format_date_display


CSV_HEADER = "fullname;username;category;start_date;end_date;comment"


def build_absence_export_filename(start_date: str, end_date: str) -> str:
    start_disp = format_date_display(start_date)
    end_disp = format_date_display(end_date)
    return f"absences_{start_disp}_{end_disp}.csv"


def build_absence_export_csv_text(rows: list[tuple]) -> str:
    lines = [CSV_HEADER]
    for (_uid, category, start_date, end_date, comment, fullname, username) in rows:
        comment_escaped = (comment or "").replace(";", ",")
        start_disp = format_date_display(start_date)
        end_disp = format_date_display(end_date)
        if username:
            user_display = f"{fullname} (@{username})"
        else:
            user_display = fullname
        lines.append(
            f"{user_display};{username or ''};{category};{start_disp};{end_disp};{comment_escaped}"
        )
    return "\n".join(lines)


def build_today_absences_report(today_display: str, rows: list[tuple]) -> str:
    lines = []
    for (_uid, category, start_date, end_date, comment, fullname, _username) in rows:
        start_disp = format_date_display(start_date)
        end_disp = format_date_display(end_date)
        comment_text = comment if comment else "—"
        lines.append(
            f"{fullname} ({category}, {start_disp} - {end_disp}), комментарий: {comment_text}"
        )
    return f"Отсутствия на сегодня ({today_display}):\n\n" + "\n\n".join(lines)

