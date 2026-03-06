#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: deploy/setup.sh [--dev] [--with-systemd] [--force-service]

--dev            install dev dependencies (pytest)
--with-systemd   install/enable system service (requires sudo)
--force-service  overwrite /etc/systemd/system/telegram_bot.service
USAGE
}

INSTALL_DEV=0
INSTALL_SYSTEMD=0
FORCE_SERVICE=0

for arg in "$@"; do
  case "$arg" in
    --dev) INSTALL_DEV=1 ;;
    --with-systemd) INSTALL_SYSTEMD=1 ;;
    --force-service) FORCE_SERVICE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $arg"; usage; exit 1 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT/.venv"

if [ ! -e "$VENV_DIR" ]; then
  if [ -d "$ROOT/venv" ]; then
    ln -s "$ROOT/venv" "$VENV_DIR"
  else
    python3 -m venv "$VENV_DIR"
  fi
fi

"$VENV_DIR/bin/python" -m pip install -r "$ROOT/requirements.txt"
if [ "$INSTALL_DEV" -eq 1 ]; then
  "$VENV_DIR/bin/python" -m pip install -r "$ROOT/requirements-dev.txt"
fi

mkdir -p "$HOME/.config/systemd/user"
cp "$ROOT/deploy/systemd-user/telegram_bot_notify.service" "$HOME/.config/systemd/user/"
cp "$ROOT/deploy/systemd-user/telegram_bot_notify.timer" "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now telegram_bot_notify.timer

if [ "$INSTALL_SYSTEMD" -eq 1 ]; then
  SERVICE_PATH="/etc/systemd/system/telegram_bot.service"
  ENV_DIR="/etc/telegram_bot"
  ENV_PATH="$ENV_DIR/telegram_bot.env"
  SERVICE_TEMPLATE="$ROOT/deploy/systemd/telegram_bot.service.example"
  ENV_TEMPLATE="$ROOT/deploy/env/telegram_bot.env.example"
  if [ -f "$SERVICE_PATH" ] && [ "$FORCE_SERVICE" -ne 1 ]; then
    echo "telegram_bot.service exists; skipping (use --force-service to overwrite)."
  else
    sudo install -d -m 755 "$ENV_DIR"
    if [ ! -f "$ENV_PATH" ]; then
      sudo install -m 600 -o "$USER" -g "$USER" "$ENV_TEMPLATE" "$ENV_PATH"
      echo "Created $ENV_PATH from template. Update TOKEN before production use."
    fi
    sed "s/%i/$USER/g" "$SERVICE_TEMPLATE" | sudo tee "$SERVICE_PATH" >/dev/null
    sudo systemctl daemon-reload
    sudo systemctl enable --now telegram_bot
  fi
fi

cat <<EOF
Done.
If you want the timer to work without an active session:
  sudo loginctl enable-linger $USER
EOF
