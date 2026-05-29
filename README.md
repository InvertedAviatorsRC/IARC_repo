# GPS Telemetry Visualizer

Create animated GPS path and speedometer videos from telemetry CSV files.

## Install

Python 3.9 or newer is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

The package includes Python dependencies in `pyproject.toml` and uses `imageio-ffmpeg` so users do not need to install FFmpeg separately for normal rendering.

## Run The App

Native desktop app:

```bash
gps-vis-desktop
```

Streamlit browser app:

```bash
gps-vis
```

Or:

```bash
python -m gps_telemetry_visualizer
```

For a direct Streamlit command:

```bash
streamlit run app.py
```

The app opens a local Streamlit UI with:

- CSV drag and drop on the left
- render settings in the middle
- live preview on the right
- output folder picker and file name controls
- a `Create` button that saves the animation to the selected folder

## Build A macOS App

Install the development extras first:

```bash
pip install -e ".[dev]"
```

Then build the double-clickable app:

```bash
bash scripts/build_macos_app.sh
```

The app will be created at:

```bash
dist/GPS Telemetry Visualizer.app
```

## Command Line Rendering

```bash
gps-vis-render Rustler-2026-05-13-224345.csv output/telemetry_both_overlay.mp4 --mode both
```

Use `.mov` output when you want a ProRes 4444 overlay with transparency:

```bash
gps-vis-render Rustler-2026-05-13-224345.csv output/telemetry_both_overlay.mov --mode both
```

## CSV Defaults

The app auto-detects common telemetry columns, including:

- `GPS`
- `GSpd(kmh)`
- `Hdg(°)`
- `Alt(m)`

You can choose different columns in the app if your CSV uses different names.
