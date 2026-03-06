from __future__ import annotations

import datetime as dt
import os
import shutil
import sqlite3
from pathlib import Path

from app.ops.common import ROOT_DIR, resolve_db_path

BACKUP_DIR = ROOT_DIR / "backups"
DEFAULT_WARN_FREE_PERCENT = 20.0
DEFAULT_CRITICAL_FREE_PERCENT = 10.0


def _ensure_backup_dir() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


def _utc_timestamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%d_%H%M%S")


def _check_enough_space(required_bytes: int, target_dir: Path) -> None:
    usage = shutil.disk_usage(target_dir)
    # Keep 10% headroom after copy to reduce risk of filling the disk.
    minimum_free_after_copy = max(int(usage.total * 0.10), 50 * 1024 * 1024)
    if usage.free - required_bytes < minimum_free_after_copy:
        raise RuntimeError(
            "Недостаточно свободного места для безопасного backup. "
            f"Нужно ~{required_bytes} байт + запас, свободно {usage.free} байт."
        )


def disk_usage_report(target_dir: Path | None = None) -> tuple[int, int, float]:
    path = target_dir or _ensure_backup_dir()
    usage = shutil.disk_usage(path)
    free_percent = (usage.free / usage.total) * 100 if usage.total else 0.0
    return usage.free, usage.total, free_percent


def _read_percent(name: str, fallback: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    try:
        value = float(raw)
    except ValueError:
        return fallback
    if value < 0:
        return fallback
    return value


def disk_guardrail_status(
    target_dir: Path | None = None,
    warn_percent: float | None = None,
    critical_percent: float | None = None,
) -> tuple[str, str, int, int, float]:
    free, total, free_percent = disk_usage_report(target_dir)
    warn_value = warn_percent if warn_percent is not None else _read_percent("BACKUP_DISK_WARN_PCT", DEFAULT_WARN_FREE_PERCENT)
    critical_value = (
        critical_percent
        if critical_percent is not None
        else _read_percent("BACKUP_DISK_CRITICAL_PCT", DEFAULT_CRITICAL_FREE_PERCENT)
    )
    if warn_value < critical_value:
        warn_value, critical_value = critical_value, warn_value

    if free_percent <= critical_value:
        return (
            "critical",
            f"Свободное место {free_percent:.1f}% (критический порог {critical_value:.1f}%).",
            free,
            total,
            free_percent,
        )
    if free_percent <= warn_value:
        return (
            "warning",
            f"Свободное место {free_percent:.1f}% (порог warning {warn_value:.1f}%).",
            free,
            total,
            free_percent,
        )
    return (
        "ok",
        f"Свободное место {free_percent:.1f}%.",
        free,
        total,
        free_percent,
    )


def create_backup() -> Path:
    db_path = resolve_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Файл БД не найден: {db_path}")

    backup_dir = _ensure_backup_dir()
    status, message, _free, _total, _free_percent = disk_guardrail_status(backup_dir)
    if status == "critical":
        raise RuntimeError(f"Backup остановлен: {message}")
    _check_enough_space(db_path.stat().st_size, backup_dir)

    backup_path = backup_dir / f"{db_path.stem}_{_utc_timestamp()}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def list_backups() -> list[Path]:
    if not BACKUP_DIR.exists():
        return []
    return sorted([p for p in BACKUP_DIR.glob("*.db") if p.is_file()], reverse=True)


def verify_backup(path: Path | None = None) -> tuple[Path, bool, str]:
    target = path
    if target is None:
        backups = list_backups()
        if not backups:
            raise FileNotFoundError("Бэкапы не найдены.")
        target = backups[0]

    if not target.exists():
        raise FileNotFoundError(f"Файл не найден: {target}")

    with sqlite3.connect(target) as conn:
        row = conn.execute("PRAGMA integrity_check;").fetchone()
    result = (row[0] if row else "")
    is_ok = result.lower() == "ok"
    return target, is_ok, result


def restore_backup(path: Path, create_safety_backup: bool = True) -> tuple[Path, Path | None]:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Файл не найден: {path}")

    db_path = resolve_db_path()
    backup_dir = _ensure_backup_dir()
    status, message, _free, _total, _free_percent = disk_guardrail_status(backup_dir)
    if status == "critical":
        raise RuntimeError(f"Restore остановлен: {message}")
    _check_enough_space(path.stat().st_size, backup_dir)

    safety_backup: Path | None = None
    if create_safety_backup and db_path.exists():
        safety_backup = backup_dir / f"{db_path.stem}_pre_restore_{_utc_timestamp()}{db_path.suffix}"
        shutil.copy2(db_path, safety_backup)

    shutil.copy2(path, db_path)
    return db_path, safety_backup


def prune_backups(retain_count: int) -> list[Path]:
    if retain_count < 1:
        raise ValueError("retain_count должен быть >= 1.")
    backups = list_backups()
    to_delete = backups[retain_count:]
    for item in to_delete:
        item.unlink(missing_ok=True)
    return to_delete
