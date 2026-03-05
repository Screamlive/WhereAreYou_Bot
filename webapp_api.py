"""Backward-compatible WebApp API module.

Core implementation lives in app.webapp.* modules.
"""

from app.webapp import auth as webapp_auth
from app.webapp.api import (
    _http_error,
    _status_from_error,
    create_app,
    handle_absence,
    handle_export_xlsx,
    handle_me,
    handle_overlaps,
    handle_webapp_index,
    logger,
    parse_overlaps_query as _parse_overlaps_query,
)
from app.webapp.http import (
    clear_rate_limiter_state as _clear_rate_limiter_state,
    rate_limit_middleware,
    security_headers_middleware,
)

# Keep shared logger wiring so tests patching webapp_api.logger still capture auth warnings.
webapp_auth.logger = logger

# Compatibility aliases for existing tests/imports.
_verify_telegram_init_data = webapp_auth.verify_telegram_init_data
_normalize_init_data = webapp_auth.normalize_init_data
_extract_init_data_from_url = webapp_auth.extract_init_data_from_url
_extract_user_id = webapp_auth.extract_user_id


def main() -> None:
    # Thin wrapper for backward compatibility with "python webapp_api.py".
    from app.entrypoints.webapp_main import main as run_main

    run_main()


if __name__ == "__main__":
    main()
