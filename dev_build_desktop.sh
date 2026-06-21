#!/usr/bin/env bash
# Optional local packaging command. Normal UI work should use dev_run_streamlit.sh.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Local environment not found. Run ./dev_setup.sh first." >&2
  exit 1
fi

cd "$ROOT_DIR"
source "$VENV_DIR/bin/activate"

if ! python -c "import PyInstaller" >/dev/null 2>&1; then
  echo "PyInstaller is not installed in .venv. Run ./dev_setup.sh first." >&2
  exit 1
fi

case "$(uname -s)" in
  Darwin)
    echo "Building a local macOS app. This is slower than source-based testing."
    echo "The packaged app and ZIP will be written to dist/ and release/."
    exec bash scripts/build_macos_app.sh
    ;;
  MINGW*|MSYS*|CYGWIN*)
    cat >&2 <<'EOF'
This Bash helper does not build Windows packages. From PowerShell, run:

  powershell -ExecutionPolicy Bypass -File scripts\build_windows_app.ps1
EOF
    exit 1
    ;;
  *)
    cat >&2 <<'EOF'
Local desktop packaging is currently provided for macOS through this script.
For Windows, run scripts/build_windows_app.ps1 from PowerShell.
EOF
    exit 1
    ;;
esac
