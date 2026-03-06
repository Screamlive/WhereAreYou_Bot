from __future__ import annotations

import asyncio
import datetime as dt
import json
import socket
from pathlib import Path

from aiogram import Bot

from app.config.settings import read_required_secret
from app.ops.common import ROOT_DIR

CONTACTS_FILE = ROOT_DIR / ".runtime" / "ops_contacts.json"


def _ensure_runtime_dir() -> None:
    CONTACTS_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_contacts() -> list[int]:
    if not CONTACTS_FILE.exists():
        return []
    try:
        payload = json.loads(CONTACTS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    values = payload.get("telegram_ids", [])
    result: list[int] = []
    for item in values:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return sorted(set(result))


def save_contacts(contact_ids: list[int]) -> None:
    _ensure_runtime_dir()
    payload = {"telegram_ids": sorted(set(int(value) for value in contact_ids))}
    CONTACTS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def add_contact(contact_id: int) -> list[int]:
    current = load_contacts()
    if contact_id not in current:
        current.append(contact_id)
    save_contacts(current)
    return sorted(current)


def remove_contact(contact_id: int) -> list[int]:
    current = [value for value in load_contacts() if value != contact_id]
    save_contacts(current)
    return sorted(current)


async def _send_alert_async(contact_ids: list[int], text: str) -> tuple[int, list[tuple[int, str]]]:
    token = read_required_secret("TOKEN")
    bot = Bot(token=token)
    sent = 0
    failures: list[tuple[int, str]] = []
    try:
        for chat_id in contact_ids:
            try:
                await bot.send_message(chat_id=chat_id, text=text)
                sent += 1
            except Exception as exc:  # pragma: no cover - network/API path
                failures.append((chat_id, str(exc)))
    finally:
        await bot.session.close()
    return sent, failures


def send_alert(text: str, contact_ids: list[int] | None = None) -> tuple[int, list[tuple[int, str]]]:
    recipients = contact_ids if contact_ids is not None else load_contacts()
    if not recipients:
        return 0, []
    return asyncio.run(_send_alert_async(recipients, text))


def build_event_alert_text(unit: str, scope: str, source: str = "systemd OnFailure") -> str:
    host = socket.gethostname()
    now = dt.datetime.now(dt.UTC).strftime("%d.%m.%Y %H:%M:%S UTC")
    return (
        "Событийное уведомление техмониторинга.\n\n"
        f"Источник: {source}\n"
        f"Хост: {host}\n"
        f"Unit: {unit}\n"
        f"Scope: {scope}\n"
        f"Время: {now}\n\n"
        "Действие: проверьте `systemctl status` и логи."
    )
