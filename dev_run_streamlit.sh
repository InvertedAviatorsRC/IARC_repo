#!/usr/bin/env bash
# Run the Streamlit interface directly from the editable local source tree.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Local environment not found. Run ./dev_setup.sh first." >&2
  exit 1
fi

cd "$ROOT_DIR"
source "$VENV_DIR/bin/activate"

if ! command -v streamlit >/dev/null 2>&1; then
  echo "Streamlit is not installed in .venv. Run ./dev_setup.sh first." >&2
  exit 1
fi

cat <<'EOF'
Starting GPS Telemetry Visualizer in Streamlit.
Open the local URL printed below. Streamlit reloads the app when source files change.
Press Ctrl-C here when you are done.
EOF

exec streamlit run gps_telemetry_visualizer/ui.py
