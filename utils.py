import datetime


def format_date_display(date_str: str | None) -> str:
    if not date_str:
        return "—"
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.datetime.strptime(date_str, fmt).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return date_str
