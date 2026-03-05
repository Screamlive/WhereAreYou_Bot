import os

try:
    import config as _config
except ImportError:  # pragma: no cover - runtime fallback when local config.py is absent.
    _config = None


_TOKEN_PLACEHOLDERS = {
    "",
    "PUT_YOUR_TOKEN_HERE",
    "your_token_here",
}


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

