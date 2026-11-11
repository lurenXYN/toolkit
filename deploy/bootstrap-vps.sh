#!/usr/bin/env bash
# One-shot VPS bootstrap for toolkit (run ON the server as root or sudoer).
# Mirrors market-desk / news-radar install flow.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/lurenXYN/toolkit.git}"
REPO_DIR="${REPO_DIR:-$HOME/github/toolkit}"
INSTALL_DIR="${INSTALL_DIR:-/opt/toolkit}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8780}"

echo "==> packages"
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y git rsync curl python3 python3-venv python3-pip ffmpeg
else
  echo "Please install: git rsync curl python3-venv ffmpeg"
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required for media-convert"
  exit 1
fi

echo "==> clone $REPO_URL -> $REPO_DIR"
mkdir -p "$(dirname "$REPO_DIR")"
if [[ -d "$REPO_DIR/.git" ]]; then
  cd "$REPO_DIR"
  git fetch --prune origin
  git checkout main
  git reset --hard origin/main
else
  git clone "$REPO_URL" "$REPO_DIR"
  cd "$REPO_DIR"
fi

chmod +x deploy/install-systemd.sh deploy/remote-update.sh deploy/bootstrap-vps.sh

echo "==> install systemd service ($INSTALL_DIR :$PORT)"
INSTALL_DIR="$INSTALL_DIR" HOST="$HOST" PORT="$PORT" ./deploy/install-systemd.sh

echo "==> health (wait for uvicorn, up to ~60s)"
HEALTH_OK=0
for i in $(seq 1 30); do
  if body="$(curl -fsS --max-time 3 "http://127.0.0.1:${PORT}/api/health" 2>/dev/null)"; then
    echo "$body"
    HEALTH_OK=1
    break
  fi
  sleep 2
done
if [[ "$HEALTH_OK" != "1" ]]; then
  echo "Warning: health check not ready yet; service may still be starting."
  systemctl --no-pager --full status toolkit.service || true
fi
echo
echo "Bootstrap done."
echo "Portal:  http://127.0.0.1:${PORT}/"
echo "Convert: http://127.0.0.1:${PORT}/tools/media-convert/"
