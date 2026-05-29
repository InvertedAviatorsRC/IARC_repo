#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller-cache"
mkdir -p "$PYINSTALLER_CONFIG_DIR"

.venv/bin/pyinstaller \
  --name "GPS Telemetry Visualizer" \
  --windowed \
  --noconfirm \
  --clean \
  --collect-all imageio_ffmpeg \
  --hidden-import matplotlib.backends.backend_agg \
  desktop_app.py

echo "Built dist/GPS Telemetry Visualizer.app"
