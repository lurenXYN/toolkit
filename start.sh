#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
echo "Starting toolkit at http://127.0.0.1:8780"
exec .venv/bin/python -m toolkit serve --host 127.0.0.1 --port 8780
