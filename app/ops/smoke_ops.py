from __future__ import annotations

import os
import urllib.error
import urllib.request


def _normalize_base_url(base_url: str | None) -> str:
    if base_url and base_url.strip():
        return base_url.rstrip("/")

    env_url = os.getenv("WEBAPP_URL", "").strip().rstrip("/")
    if env_url:
        return env_url
    return "http://127.0.0.1:8080/webapp"


def run_smoke(base_url: str | None = None) -> int:
    root = _normalize_base_url(base_url)
    me_url = f"{root}/v1/me"

    print(f"Smoke target: {root}")

    try:
        with urllib.request.urlopen(me_url, timeout=8) as resp:
            status = resp.status
            print(f"GET {me_url} -> {status}")
            if status == 401:
                print("OK: без auth контекста endpoint закрыт.")
                return 0
            print("WARN: ожидался 401 без auth контекста.")
            return 1
    except urllib.error.HTTPError as exc:
        print(f"GET {me_url} -> {exc.code}")
        if exc.code in {401, 429}:
            print("OK: endpoint защищен (401/429).")
            return 0
        print("FAIL: неожиданный код ответа.")
        return 1
    except Exception as exc:
        print(f"FAIL: запрос не выполнен: {exc}")
        return 1

