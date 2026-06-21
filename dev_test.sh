#!/usr/bin/env bash
# Run the project's automated tests against the editable local source tree.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Local environment not found. Run ./dev_setup.sh first." >&2
  exit 1
fi

cd "$ROOT_DIR"
source "$VENV_DIR/bin/activate"

if ! command -v pytest >/dev/null 2>&1; then
  echo "pytest is not installed in .venv. Run ./dev_setup.sh first." >&2
  exit 1
fi

exec pytest -q
