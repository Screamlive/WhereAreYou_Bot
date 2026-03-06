from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from app.ops.common import PYTHON_BIN, ROOT_DIR, colorize, run_cmd

RUN_COMPONENTS = {
    "bot": [PYTHON_BIN, "bot.py"],
    "webapp": [PYTHON_BIN, "webapp_api.py"],
    "notify-once": [PYTHON_BIN, "notifications.py"],
}

PID_DIR = ROOT_DIR / ".runtime" / "pids"
LOG_DIR = ROOT_DIR / ".runtime" / "logs"


def _pid_path(component: str) -> Path:
    return PID_DIR / f"{component}.pid"


def _log_path(component: str) -> Path:
    return LOG_DIR / f"{component}.log"


def _ensure_runtime_dirs() -> None:
    PID_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_process_cmdline(pid: int) -> str | None:
    proc_cmdline = Path("/proc") / str(pid) / "cmdline"
    try:
        raw = proc_cmdline.read_bytes()
    except OSError:
        raw = b""
    if raw:
        return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()

    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        return None
    value = (result.stdout or "").strip()
    return value or None


def _pid_matches_component(pid: int, component: str) -> bool:
    cmdline = _read_process_cmdline(pid)
    if not cmdline:
        return False
    normalized_cmdline = cmdline.lower()
    expected_cmd = _resolve_component(component)
    markers = [Path(arg).name.lower() for arg in expected_cmd[1:] if arg.strip()]
    if not markers:
        return True
    return all(marker in normalized_cmdline for marker in markers)


def _read_pid(component: str) -> int | None:
    path = _pid_path(component)
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    try:
        return int(raw)
    except ValueError:
        return None


def _clear_stale_pid(component: str) -> None:
    path = _pid_path(component)
    pid = _read_pid(component)
    if pid is None:
        path.unlink(missing_ok=True)
        return
    if not _is_process_alive(pid):
        path.unlink(missing_ok=True)
        return
    if not _pid_matches_component(pid, component):
        path.unlink(missing_ok=True)


def _resolve_component(component: str) -> list[str]:
    if component not in RUN_COMPONENTS:
        raise ValueError(f"Неизвестный компонент: {component}")
    return RUN_COMPONENTS[component]


def run_component_foreground(component: str) -> int:
    cmd = _resolve_component(component)
    result = run_cmd(cmd, capture=False)
    return result.returncode


def start_component_background(component: str) -> tuple[int, Path]:
    cmd = _resolve_component(component)
    _ensure_runtime_dirs()
    _clear_stale_pid(component)

    existing_pid = _read_pid(component)
    if existing_pid is not None and _is_process_alive(existing_pid):
        raise RuntimeError(f"Компонент {component} уже запущен в фоне (PID {existing_pid}).")

    log_file = _log_path(component)
    handle = open(log_file, "a", encoding="utf-8")
    handle.write("\n===== START =====\n")
    handle.flush()

    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT_DIR),
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    handle.close()

    _pid_path(component).write_text(str(proc.pid), encoding="utf-8")
    return proc.pid, log_file


def stop_component_background(component: str, force: bool = False) -> bool:
    _clear_stale_pid(component)
    pid = _read_pid(component)
    if pid is None:
        return False

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _pid_path(component).unlink(missing_ok=True)
        return False

    for _ in range(40):
        if not _is_process_alive(pid):
            try:
                os.waitpid(pid, os.WNOHANG)
            except (ChildProcessError, OSError):
                pass
            _pid_path(component).unlink(missing_ok=True)
            return True
        time.sleep(0.1)

    if force:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            os.waitpid(pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            pass
        _pid_path(component).unlink(missing_ok=True)
        return True

    return False


def get_component_background_status(component: str) -> tuple[bool, int | None, Path]:
    _resolve_component(component)
    _ensure_runtime_dirs()
    _clear_stale_pid(component)

    pid = _read_pid(component)
    if pid is None:
        return False, None, _log_path(component)
    return _is_process_alive(pid), pid, _log_path(component)


def format_component_status_line(component: str) -> str:
    running, pid, log_path = get_component_background_status(component)
    status = colorize("running", "green") if running else colorize("stopped", "red")
    pid_text = str(pid) if pid is not None else "-"
    return f"{component}: {status}, pid={pid_text}, log={log_path}"
