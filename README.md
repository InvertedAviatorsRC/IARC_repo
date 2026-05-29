# GPS Telemetry Visualizer

Create animated GPS path and speedometer videos from telemetry CSV files.

The app can be used as a native desktop program, a Streamlit browser app, or a command line renderer. It reads a CSV with GPS telemetry, previews the map and speedometer, then exports an `.mp4` or transparent `.mov` overlay.

## What You Need

- A Mac, Windows PC, or Linux computer
- Python 3.9 or newer
- A telemetry CSV file with GPS location data

The project installs its Python packages from `pyproject.toml` or `requirements.txt`. It also uses `imageio-ffmpeg`, so most users do not need to install FFmpeg separately.

## Download The Program

1. Open the GitHub repository page.
2. Click the green `Code` button.
3. Click `Download ZIP`.
4. Unzip the downloaded file.
5. Move the unzipped folder somewhere easy to find, such as your Desktop or Documents folder.

You can also download it with Git if you already use Git:

```bash
git clone https://github.com/InvertedAviatorsRC/IARC_repo.git
cd IARC_repo
git checkout codex/gps-telemetry-visualizer-package
```

If you downloaded the ZIP from a branch page, the folder name may include the branch name. That is fine.

## Install Python

Check whether Python is already installed:

```bash
python3 --version
```

If that prints Python 3.9 or newer, you are ready for the next step.

If Python is not installed, install it from:

[https://www.python.org/downloads/](https://www.python.org/downloads/)

On macOS, the installer may add `python3` and `pip3` commands. On Windows, make sure to check `Add python.exe to PATH` during installation.

## Set Up The Program

Open a terminal in the project folder.

On macOS:

```bash
cd ~/Desktop/IARC_repo
```

Use the real folder path if you saved it somewhere else.

Create a virtual environment:

```bash
python3 -m venv .venv
```

Turn it on:

```bash
source .venv/bin/activate
```

Install the app:

```bash
pip install -e .
```

That installs the GPS Telemetry Visualizer and all required packages.

## Run The Desktop App

After setup, run:

```bash
gps-vis-desktop
```

The desktop app lets you:

- Drag and drop a CSV file
- Choose GPS, speed, heading, and altitude columns
- Set speed units, FPS, timing, and max speed
- Pick colors for the path, speedometer, dot, needle, and background
- Choose an output folder with a file browser
- Preview the overlay before creating the final video
- Export `.mp4` or `.mov`

## Run The Browser App

You can also run the Streamlit version:

```bash
gps-vis
```

Or:

```bash
streamlit run app.py
```

Streamlit opens the app in your web browser. It still runs locally on your computer.

## Build A Double-Clickable macOS App

If you want an app you can open from Finder without using the terminal every time, build the macOS app bundle.

Install the development tools:

```bash
pip install -e ".[dev]"
```

Build the app:

```bash
bash scripts/build_macos_app.sh
```

The finished app will be created here:

```bash
dist/GPS Telemetry Visualizer.app
```

You can drag `GPS Telemetry Visualizer.app` into your Applications folder or onto your Desktop.

If macOS blocks the app the first time you open it, right-click the app, choose `Open`, then confirm that you want to open it.

## Command Line Rendering

You can render directly from the terminal:

```bash
gps-vis-render path/to/telemetry.csv output/telemetry_both_overlay.mp4 --mode both
```

Use `.mov` when you want a ProRes 4444 overlay with transparency:

```bash
gps-vis-render path/to/telemetry.csv output/telemetry_both_overlay.mov --mode both
```

## CSV Defaults

The app auto-detects common telemetry columns, including:

- `GPS`
- `GSpd(kmh)`
- `Hdg(°)`
- `Alt(m)`

You can choose different columns in the app if your CSV uses different names.

The GPS column should contain latitude and longitude in one cell, such as:

```text
44.766099 -93.331609
```

or:

```text
44.766099,-93.331609
```

## Output Files

Use `.mp4` for normal videos with a solid background.

Use `.mov` when you want a transparent overlay that can be placed over other video in editing software.

## Troubleshooting

If `gps-vis-desktop` is not found, make sure the virtual environment is active:

```bash
source .venv/bin/activate
```

Then try again.

If installation fails, upgrade `pip`:

```bash
python -m pip install --upgrade pip
pip install -e .
```

If the app cannot find your CSV columns, open the settings in the app and manually choose the correct GPS and speed columns.

If rendering is slow, lower the FPS or increase the seconds between GPS points less aggressively. Higher FPS and long CSV files create more video frames.
