from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
PYTHON_BIN = sys.executable

_COLOR_CODES = {
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "cyan": "\033[36m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


def run_cmd(args: list[str], capture: bool = False) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, object] = {
        "cwd": str(ROOT_DIR),
        "text": True,
    }
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    return subprocess.run(args, **kwargs)


def print_result(result: subprocess.CompletedProcess[str]) -> int:
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def resolve_db_path() -> Path:
    raw = os.getenv("DB_NAME", "bot_database.db").strip() or "bot_database.db"
    db_path = Path(raw)
    if not db_path.is_absolute():
        db_path = ROOT_DIR / db_path
    return db_path


def supports_color() -> bool:
    return sys.stdout.isatty() and os.getenv("NO_COLOR") is None


def colorize(text: str, color: str) -> str:
    if not supports_color():
        return text
    start = _COLOR_CODES.get(color, "")
    end = _COLOR_CODES["reset"] if start else ""
    return f"{start}{text}{end}"


def clear_terminal() -> None:
    if not sys.stdout.isatty():
        return
    os.system("cls" if os.name == "nt" else "clear")


def human_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"
