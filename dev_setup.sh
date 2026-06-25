#!/usr/bin/env bash
# Create or refresh the local development environment.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=9
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

print_python_help() {
  cat <<'EOF'

GPS Telemetry Visualizer needs Python 3.9 or newer.

Install a current Python release, then run this script again. If Python is
installed somewhere unusual, point the script at it, for example:

  PYTHON_BIN=/path/to/python3.12 ./dev_setup.sh
EOF
}

python_is_supported() {
  "$1" -c "import sys; raise SystemExit(not (sys.version_info >= ($MIN_PYTHON_MAJOR, $MIN_PYTHON_MINOR)))"
}

if [[ -d "$VENV_DIR" ]]; then
  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "Found .venv, but it is incomplete or does not contain Python." >&2
    echo "Remove it with: rm -rf .venv" >&2
    exit 1
  fi

  if ! python_is_supported "$VENV_DIR/bin/python"; then
    echo "The existing .venv uses an unsupported Python version:" >&2
    "$VENV_DIR/bin/python" --version >&2 || true
    echo "Remove it with: rm -rf .venv, then rerun this script with Python 3.9+." >&2
    exit 1
  fi
else
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Could not find '$PYTHON_BIN'." >&2
    print_python_help >&2
    exit 1
  fi

  if ! python_is_supported "$PYTHON_BIN"; then
    echo "'$PYTHON_BIN' is too old:" >&2
    "$PYTHON_BIN" --version >&2 || true
    print_python_help >&2
    exit 1
  fi

  echo "Creating .venv with $($PYTHON_BIN --version)..."
  if ! "$PYTHON_BIN" -m venv "$VENV_DIR"; then
    echo "Could not create .venv. Check that Python's venv support is installed." >&2
    exit 1
  fi
fi

# Activating keeps the next commands and the commands shown to the user aligned.
source "$VENV_DIR/bin/activate"

echo "Using $(python --version)"
echo "Upgrading pip..."
python -m pip install --upgrade pip

echo "Installing GPS Telemetry Visualizer and developer tools..."
if ! python -m pip install -e ".[dev]"; then
  cat >&2 <<'EOF'

The editable install did not finish. Check the error above, confirm that you
have an internet connection, then run ./dev_setup.sh again.
EOF
  exit 1
fi

cat <<'EOF'

Local development setup is ready.

Next steps:
  ./dev_run_native.sh     # Final native PySide app
  ./dev_run_streamlit.sh  # Legacy browser prototype
  ./dev_test.sh           # Run automated tests
  ./dev_run_desktop.sh    # Alias for the native desktop app
  ./dev_build_desktop.sh  # Optional: build a local macOS app

You can also use: make native, make streamlit, make test, make desktop, or make build.
EOF
