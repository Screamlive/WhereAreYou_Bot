"""Auth helpers for Telegram WebApp API."""

import hashlib
import hmac
import json
import logging
import os
import time
from urllib.parse import parse_qsl, unquote, urlparse

from aiohttp import web

from settings import TOKEN
from app.webapp.service import WebAppAccessError

try:
    from config import WEBAPP_ALLOW_DEV_FALLBACK as CONFIG_WEBAPP_ALLOW_DEV_FALLBACK
except ImportError:
    CONFIG_WEBAPP_ALLOW_DEV_FALLBACK = False
try:
    from config import WEBAPP_ALLOW_INITDATA_COMPAT as CONFIG_WEBAPP_ALLOW_INITDATA_COMPAT
except ImportError:
    CONFIG_WEBAPP_ALLOW_INITDATA_COMPAT = True

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _allow_dev_fallback() -> bool:
    return _env_flag("WEBAPP_ALLOW_DEV_FALLBACK", default=bool(CONFIG_WEBAPP_ALLOW_DEV_FALLBACK))


def _allow_initdata_compat() -> bool:
    return _env_flag("WEBAPP_ALLOW_INITDATA_COMPAT", default=bool(CONFIG_WEBAPP_ALLOW_INITDATA_COMPAT))


def normalize_init_data(init_data: str) -> str:
    value = (init_data or "").strip()

    if value.lower().startswith("tma "):
        value = value[4:].strip()

    if value.startswith("tgWebAppData="):
        parsed = dict(parse_qsl(value, keep_blank_values=True))
        tg_data = parsed.get("tgWebAppData")
        if tg_data:
            value = tg_data

    if "hash=" not in value and ("%26" in value or "%3D" in value):
        decoded = unquote(value)
        if "hash=" in decoded:
            value = decoded

    return value


def verify_telegram_init_data(init_data: str) -> int:
    normalized_init_data = normalize_init_data(init_data)
    parsed = dict(parse_qsl(normalized_init_data, keep_blank_values=True))
    provided_hash = parsed.pop("hash", None)
    if not provided_hash:
        raise WebAppAccessError("Отсутствует hash в initData.", status_code=401)

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, provided_hash):
        raise WebAppAccessError("Невалидная подпись initData.", status_code=401)

    auth_date_raw = parsed.get("auth_date")
    if auth_date_raw and auth_date_raw.isdigit():
        now = int(time.time())
        auth_date = int(auth_date_raw)
        if now - auth_date > 24 * 60 * 60:
            raise WebAppAccessError("initData устарел.", status_code=401)

    user_raw = parsed.get("user")
    if not user_raw:
        raise WebAppAccessError("В initData отсутствует user.", status_code=401)
    try:
        user_obj = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise WebAppAccessError("Некорректный user в initData.", status_code=401) from exc

    user_id = user_obj.get("id")
    if not isinstance(user_id, int):
        raise WebAppAccessError("Некорректный user.id в initData.", status_code=401)
    return user_id


def extract_init_data_from_url(raw_url: str | None) -> str:
    if not raw_url:
        return ""
    try:
        parsed = urlparse(raw_url)
    except Exception:
        return ""

    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key in ("tgWebAppData", "init_data", "initData"):
        value = query_params.get(key)
        if value:
            return value

    fragment = parsed.fragment or ""
    if fragment.startswith("/?"):
        fragment = fragment[2:]
    elif fragment.startswith("?"):
        fragment = fragment[1:]
    fragment_params = dict(parse_qsl(fragment, keep_blank_values=True))
    for key in ("tgWebAppData", "init_data", "initData"):
        value = fragment_params.get(key)
        if value:
            return value
    return ""


def extract_user_id(request: web.Request) -> int:
    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header.lower().startswith("tma "):
        return verify_telegram_init_data(auth_header[4:].strip())

    init_data = request.headers.get("X-Telegram-Init-Data")
    if init_data:
        return verify_telegram_init_data(init_data)

    referer_raw = request.headers.get("Referer") or ""
    if _allow_initdata_compat():
        init_data_compat = request.query.get("init_data") or request.query.get("tgWebAppData")
        if init_data_compat:
            return verify_telegram_init_data(init_data_compat)

        cookie_init_data = request.cookies.get("tg_init_data")
        if cookie_init_data:
            return verify_telegram_init_data(cookie_init_data)

        referer_init_data = extract_init_data_from_url(referer_raw)
        if referer_init_data:
            return verify_telegram_init_data(referer_init_data)

    if _allow_dev_fallback():
        user_id_raw = request.headers.get("X-Telegram-User-Id")
        if user_id_raw and user_id_raw.isdigit():
            return int(user_id_raw)

    referer_has_tg = "tgWebAppData=" in referer_raw
    referer_has_init = "init_data=" in referer_raw or "initData=" in referer_raw
    logger.warning(
        (
            "WebApp auth context is missing: path=%s has_auth=%s has_init_header=%s "
            "has_init_cookie=%s has_referer=%s referer_has_tg=%s referer_has_init=%s referer_len=%s ua=%s"
        ),
        request.path,
        bool(auth_header),
        bool(request.headers.get("X-Telegram-Init-Data")),
        bool(request.cookies.get("tg_init_data")),
        bool(referer_raw),
        referer_has_tg,
        referer_has_init,
        len(referer_raw),
        (request.headers.get("User-Agent") or "")[:120],
    )
    raise WebAppAccessError("Не передан Telegram initData.", status_code=401)
