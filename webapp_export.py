import io
import zipfile
from xml.sax.saxutils import escape


CATEGORY_LABELS = {
    "vacation": "Отпуск",
    "sick": "Больничный",
    "dayoff": "DayOff",
    "other": "Другое",
}

STATUS_LABELS = {
    "pending": "На согласовании",
    "approved": "Одобрено",
    "declined": "Отклонено",
}


def _column_name(index: int) -> str:
    name = ""
    n = index
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _cell_ref(row_index: int, col_index: int) -> str:
    return f"{_column_name(col_index)}{row_index}"


def _string_cell(row_index: int, col_index: int, value: str) -> str:
    safe_text = escape(value)
    ref = _cell_ref(row_index, col_index)
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{safe_text}</t></is></c>'


def _build_sheet_xml(rows: list[list[str]]) -> str:
    xml_rows: list[str] = []
    for row_idx, row_values in enumerate(rows, start=1):
        cells = "".join(
            _string_cell(row_idx, col_idx, value)
            for col_idx, value in enumerate(row_values, start=1)
        )
        xml_rows.append(f'<row r="{row_idx}">{cells}</row>')

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(xml_rows)}</sheetData>"
        "</worksheet>"
    )


def _format_iso_date(date_value: str) -> str:
    parts = date_value.split("-")
    if len(parts) != 3:
        return date_value
    return f"{parts[2]}.{parts[1]}.{parts[0]}"


def _scope_label(scope: dict) -> str:
    scope_type = scope.get("type")
    if scope_type == "global":
        return "Глобально"
    if scope_type == "superadmins":
        return "Суперадмины"
    if scope_type == "group":
        group_name = scope.get("group_name") or f"ID={scope.get('group_id')}"
        return f"Группа: {group_name}"
    return str(scope_type)


def build_overlaps_export_rows(payload: dict) -> list[list[str]]:
    users_by_id = {user["user_id"]: user for user in payload.get("users", [])}
    intervals = sorted(
        payload.get("intervals", []),
        key=lambda item: (
            users_by_id.get(item["user_id"], {}).get("fullname", ""),
            item.get("start_date", ""),
            item.get("absence_id", 0),
        ),
    )

    statuses = payload.get("filters", {}).get("statuses", [])
    categories = payload.get("filters", {}).get("categories", [])
    query = payload.get("filters", {}).get("query", "")
    period = payload.get("period", {})

    rows: list[list[str]] = [
        ["Выгрузка пересечений отсутствий", ""],
        ["Scope", _scope_label(payload.get("scope", {}))],
        [
            "Период",
            f"{_format_iso_date(period.get('start_date', ''))} - {_format_iso_date(period.get('end_date', ''))}",
        ],
        ["Статусы", ", ".join(STATUS_LABELS.get(status, status) for status in statuses) or "Все"],
        ["Категории", ", ".join(CATEGORY_LABELS.get(category, category) for category in categories) or "Все"],
        ["Поиск", query or "—"],
        ["", ""],
        ["ID", "ФИО", "Username", "Категория", "Дата начала", "Дата окончания", "Статус", "Комментарий"],
    ]

    for interval in intervals:
        user = users_by_id.get(interval["user_id"], {})
        username = user.get("username", "")
        rows.append(
            [
                str(interval.get("absence_id", "")),
                user.get("fullname", f"ID {interval['user_id']}"),
                f"@{username}" if username else "—",
                CATEGORY_LABELS.get(interval.get("category", ""), interval.get("category", "")),
                _format_iso_date(interval.get("start_date", "")),
                _format_iso_date(interval.get("end_date", "")),
                STATUS_LABELS.get(interval.get("status", ""), interval.get("status", "")),
                interval.get("comment") or "—",
            ]
        )

    if not intervals:
        rows.append(["", "Нет данных за выбранный период", "", "", "", "", "", ""])

    return rows


def build_overlaps_xlsx(payload: dict) -> bytes:
    rows = build_overlaps_export_rows(payload)
    sheet_xml = _build_sheet_xml(rows)

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )

    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Пересечения" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )

    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", rels_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return stream.getvalue()


def build_overlaps_export_filename(payload: dict) -> str:
    scope = payload.get("scope", {})
    scope_type = scope.get("type", "scope")
    if scope_type == "group":
        scope_part = f"group_{scope.get('group_id', 'na')}"
    else:
        scope_part = scope_type
    period = payload.get("period", {})
    start_part = (period.get("start_date", "start") or "start").replace("-", "")
    end_part = (period.get("end_date", "end") or "end").replace("-", "")
    return f"overlaps_{scope_part}_{start_part}_{end_part}.xlsx"
