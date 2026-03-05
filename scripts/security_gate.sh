#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-./.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "ERROR: Python interpreter not found: ${PYTHON_BIN}" >&2
  exit 1
fi

echo "[security-gate] Running focused security tests..."
"${PYTHON_BIN}" -m unittest \
  tests.test_webapp_api \
  tests.test_webapp_readonly \
  tests.test_security_handlers \
  tests.test_webapp_frontend_security

echo "[security-gate] Running full test suite..."
"${PYTHON_BIN}" -m unittest discover -s tests

echo "[security-gate] Running static checks..."
if rg -n "WebApp auth context is missing: path=%s.*path_qs" webapp_api.py >/dev/null; then
  echo "ERROR: Found unsafe path_qs logging pattern in webapp_api.py" >&2
  exit 1
fi

if rg -n 'localStorage\.setItem\("tg_init_data"|document\.cookie\s*=\s*`tg_init_data=|url\.searchParams\.set\("init_data"' webapp_static/app.js >/dev/null; then
  echo "ERROR: Found insecure initData transport/storage pattern in webapp_static/app.js" >&2
  exit 1
fi

echo "[security-gate] OK"
