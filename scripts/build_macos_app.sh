#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller-cache"
mkdir -p "$PYINSTALLER_CONFIG_DIR"
export MPLCONFIGDIR="$PYINSTALLER_CONFIG_DIR/matplotlib"
mkdir -p "$MPLCONFIGDIR"

python scripts/prepare_app_icon.py

python -m PyInstaller \
  --name "GPS Telemetry Visualizer" \
  --windowed \
  --noconfirm \
  --clean \
  --icon "$PYINSTALLER_CONFIG_DIR/gps_app_icon.png" \
  --collect-all gps_telemetry_visualizer \
  --collect-all imageio_ffmpeg \
  --collect-all PySide6 \
  --hidden-import matplotlib.backends.backend_agg \
  native_desktop_app.py

binary="dist/GPS Telemetry Visualizer.app/Contents/MacOS/GPS Telemetry Visualizer"
binary_info="$(file "$binary")"

case "$binary_info" in
  *arm64*)
    archive_name="GPS-Telemetry-Visualizer-macOS-Apple-Silicon.zip"
    ;;
  *x86_64*)
    archive_name="GPS-Telemetry-Visualizer-macOS-Intel.zip"
    ;;
  *)
    echo "Unsupported macOS executable architecture: $binary_info" >&2
    exit 1
    ;;
esac

mkdir -p release
rm -f "release/$archive_name"
ditto -c -k --sequesterRsrc --keepParent \
  "dist/GPS Telemetry Visualizer.app" \
  "release/$archive_name"

echo "Built release/$archive_name"
