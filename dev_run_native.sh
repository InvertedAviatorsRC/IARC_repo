#!/usr/bin/env bash
# Run the final native PySide desktop app from the editable local source tree.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Local environment not found. Run ./dev_setup.sh first." >&2
  exit 1
fi

cd "$ROOT_DIR"
source "$VENV_DIR/bin/activate"

echo "Starting the native desktop app. Close its window when you are done."
python native_desktop_app.py
