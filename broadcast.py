import argparse
import asyncio
import sys

from aiogram import Bot

from app.config.settings import read_required_secret
from app.repositories.groups_repo import get_group_members, get_group_name, list_all_groups
from app.repositories.users_repo import get_admins, get_all_users, get_approved_users
from database import init_db


def _parse_group_audience(audience: str) -> int | None:
    if not audience.startswith("group:"):
        return None
    raw = audience.split(":", 1)[1].strip()
    if not raw:
        raise ValueError("Формат audience для группы: group:<id>")
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError("ID группы в audience должен быть числом.") from exc


def _resolve_recipient_ids(audience: str) -> list[int]:
    group_id = _parse_group_audience(audience)
    if group_id is not None:
        group_name = get_group_name(group_id)
        if not group_name:
            raise ValueError(f"Группа с ID={group_id} не найдена.")
        return sorted({user_id for (user_id, _fname, _username, _role) in get_group_members(group_id)})

    if audience == "all":
        return sorted({user_id for (user_id, _fname, _username) in get_all_users()})
    if audience == "approved":
        return sorted({user_id for (user_id, _fname, _username) in get_approved_users()})
    if audience == "superadmins":
        return sorted(set(get_admins()))
    if audience == "group_admins":
        ids: set[int] = set()
        for group_id, _group_name in list_all_groups():
            for user_id, _fname, _username, role in get_group_members(group_id):
                if role == "admin":
                    ids.add(user_id)
        return sorted(ids)

    raise ValueError(
        "Неверный audience. Допустимо: all | approved | group:<id> | superadmins | group_admins"
    )


def _load_text(text: str | None, file_path: str | None) -> str:
    if text is not None:
        payload = text.strip()
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            payload = f.read().strip()
    if not payload:
        raise ValueError("Текст рассылки пустой.")
    return payload


def _extract_latest_changelog_section(changelog_path: str) -> str:
    with open(changelog_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    start = None
    for idx, line in enumerate(lines):
        if line.startswith("## "):
            start = idx
            break
    if start is None:
        raise ValueError("В CHANGELOG не найдено секций вида '## ...'.")

    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break

    section = "\n".join(lines[start:end]).strip()
    if not section:
        raise ValueError("Не удалось извлечь актуальный блок CHANGELOG.")
    return section


def _load_broadcast_text(
    text: str | None,
    file_path: str | None,
    changelog_path: str | None,
) -> str:
    if changelog_path is not None:
        return _extract_latest_changelog_section(changelog_path)
    return _load_text(text, file_path)


async def _send_broadcast(
    recipient_ids: list[int],
    text: str,
    delay_sec: float,
) -> tuple[int, list[tuple[int, str]]]:
    bot = Bot(token=read_required_secret("TOKEN"))
    sent = 0
    failures: list[tuple[int, str]] = []
    try:
        for idx, user_id in enumerate(recipient_ids, start=1):
            try:
                await bot.send_message(user_id, text)
                sent += 1
            except Exception as exc:  # pragma: no cover - depends on Telegram API.
                failures.append((user_id, str(exc)))
            if delay_sec > 0 and idx < len(recipient_ids):
                await asyncio.sleep(delay_sec)
    finally:
        await bot.session.close()
    return sent, failures


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Сервисная рассылка сообщений пользователям Telegram-бота.")
    parser.add_argument(
        "--audience",
        required=True,
        help="all | approved | group:<id> | superadmins | group_admins",
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="Текст сообщения.")
    source.add_argument("--file", help="Путь к .txt/.md файлу с текстом сообщения.")
    source.add_argument(
        "--changelog-latest",
        nargs="?",
        const="CHANGELOG.md",
        metavar="PATH",
        help="Взять только верхний блок из CHANGELOG (по умолчанию PATH=CHANGELOG.md).",
    )

    parser.add_argument("--dry-run", action="store_true", help="Только показать получателей, без отправки.")
    parser.add_argument("--limit", type=int, default=None, help="Ограничить число получателей.")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.08,
        help="Пауза между отправками в секундах (по умолчанию 0.08).",
    )
    return parser


def _preview_text(text: str, limit: int = 700) -> str:
    normalized = text.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "\n... [обрезано]"


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        print("Ошибка: --limit должен быть >= 1.")
        return 2
    if args.delay < 0:
        print("Ошибка: --delay должен быть >= 0.")
        return 2

    init_db()
    try:
        text = _load_broadcast_text(args.text, args.file, args.changelog_latest)
        recipients = _resolve_recipient_ids(args.audience)
    except ValueError as exc:
        print(f"Ошибка: {exc}")
        return 2

    if args.limit is not None:
        recipients = recipients[: args.limit]

    print(f"Audience: {args.audience}")
    print(f"Получателей: {len(recipients)}")
    print("--- Текст сообщения (preview) ---")
    print(_preview_text(text))
    print("--- Конец preview ---")
    if recipients:
        preview = ", ".join(str(x) for x in recipients[:15])
        if len(recipients) > 15:
            preview += ", ..."
        print(f"ID (preview): {preview}")

    if args.dry_run:
        print("Dry-run: отправка не выполнялась.")
        return 0

    if not recipients:
        print("Получателей нет, отправка пропущена.")
        return 0

    sent, failures = asyncio.run(_send_broadcast(recipients, text, args.delay))
    print(f"Отправлено: {sent}")
    print(f"Ошибок: {len(failures)}")
    if failures:
        print("Ошибки (первые 20):")
        for user_id, err in failures[:20]:
            print(f"- {user_id}: {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
