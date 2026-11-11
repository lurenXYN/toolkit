#!/usr/bin/env bash
# Install a modern static ffmpeg (supports animated WebP) on the VPS.
# Default target: /opt/ffmpeg  + symlinks in /usr/local/bin
#
# Usage (on server):
#   sudo ./deploy/install-ffmpeg.sh
set -euo pipefail

INSTALL_ROOT="${INSTALL_ROOT:-/opt/ffmpeg}"
BIN_LINK_DIR="${BIN_LINK_DIR:-/usr/local/bin}"
# BtbN gpl linux64 static-ish shared build; includes libwebp and recent codecs.
FFMPEG_URL="${FFMPEG_URL:-https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz}"

run_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    echo "Need root or sudo to install into $INSTALL_ROOT"
    exit 1
  fi
}

echo "==> download $FFMPEG_URL"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

ARCHIVE="$TMP/ffmpeg.tar.xz"
curl -fsSL "$FFMPEG_URL" -o "$ARCHIVE"

echo "==> extract to $INSTALL_ROOT"
run_root rm -rf "$INSTALL_ROOT"
run_root mkdir -p "$INSTALL_ROOT"
run_root tar -xJf "$ARCHIVE" -C "$INSTALL_ROOT" --strip-components=1

if [[ ! -x "$INSTALL_ROOT/bin/ffmpeg" ]]; then
  echo "ffmpeg binary missing after extract"
  ls -la "$INSTALL_ROOT" || true
  exit 1
fi

echo "==> link into $BIN_LINK_DIR (ahead of /usr/bin)"
run_root mkdir -p "$BIN_LINK_DIR"
run_root ln -sfn "$INSTALL_ROOT/bin/ffmpeg" "$BIN_LINK_DIR/ffmpeg"
run_root ln -sfn "$INSTALL_ROOT/bin/ffprobe" "$BIN_LINK_DIR/ffprobe"

hash -r 2>/dev/null || true
echo "==> which ffmpeg: $(command -v ffmpeg)"
ffmpeg -version | head -n 3

# Quick animated-WebP capability hint (decode path present if libwebp enabled).
if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libwebp; then
  echo "==> libwebp encoder: yes"
else
  echo "==> libwebp encoder: not listed (decode may still work via native/webp)"
fi

echo "Done. Restart toolkit so PATH picks up the new binary:"
echo "  systemctl restart toolkit"
echo "  # or ensure ExecStart env PATH starts with $BIN_LINK_DIR"
