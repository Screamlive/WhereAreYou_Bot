import os
from pathlib import Path

try:
    import config as _config
except ImportError:  # pragma: no cover - runtime fallback when local config.py is absent.
    _config = None


_TOKEN_PLACEHOLDERS = {
    "",
    "PUT_YOUR_TOKEN_HERE",
    "your_token_here",
}


def _iter_env_candidates() -> list[Path]:
    root_dir = Path(__file__).resolve().parents[2]
    candidates: list[Path] = []

    custom_env = os.getenv("TELEGRAM_BOT_ENV_FILE", "").strip()
    if custom_env:
        candidates.append(Path(custom_env).expanduser())

    candidates.append(Path.home() / ".config/telegram_bot/telegram_bot.env")
    candidates.append(Path("/etc/telegram_bot/telegram_bot.env"))
    candidates.append(root_dir / ".env")
    return candidates


def _parse_env_line(raw_line: str) -> tuple[str, str] | None:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[7:].strip()
    if "=" not in line:
        return None

    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None

    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]
    elif "#" in value:
        # Allow inline comments for unquoted values.
        value = value.split("#", 1)[0].strip()

    return key, value


def _load_env_file(path: Path) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return

    for raw_line in content.splitlines():
        parsed = _parse_env_line(raw_line)
        if not parsed:
            continue
        key, value = parsed
        os.environ.setdefault(key, value)


def _bootstrap_env() -> None:
    for path in _iter_env_candidates():
        if path.exists() and path.is_file():
            _load_env_file(path)


_bootstrap_env()


def _from_config(name: str, default=None):
    if _config is None:
        return default
    return getattr(_config, name, default)


def read_str(name: str, default=None) -> str:
    env_value = os.getenv(name)
    if env_value is not None:
        return str(env_value)
    cfg_value = _from_config(name, default)
    if cfg_value is None:
        return ""
    return str(cfg_value)


def read_int(name: str, default: int) -> int:
    raw_value = read_str(name, str(default)).strip()
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def read_bool(name: str, default: bool) -> bool:
    raw_value = read_str(name, "1" if default else "0").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def read_required_secret(name: str) -> str:
    value = read_str(name, "").strip()
    if value in _TOKEN_PLACEHOLDERS:
        raise RuntimeError(
            f"Обязательный секрет {name} не задан. "
            f"Укажите его в EnvironmentFile/systemd или локальном config.py."
        )
    return value


TOKEN = read_required_secret("TOKEN")
