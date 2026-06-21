# GPS Telemetry Visualizer

Create animated GPS path and speedometer videos from telemetry CSV files.

The app reads a telemetry CSV, shows a preview of the animated map and speedometer, then exports an `.mp4` or transparent `.mov` overlay.

## Download The App

You do not need to install Python or use the terminal.

1. Open the [GitHub Releases page](https://github.com/InvertedAviatorsRC/IARC_repo/releases).
2. Open the newest GPS Telemetry Visualizer release.
3. Download the ZIP file for your computer:

| Computer | Download |
| --- | --- |
| Windows PC | `GPS-Telemetry-Visualizer-Windows-x64.zip` |
| Mac with an Apple M-series chip | `GPS-Telemetry-Visualizer-macOS-Apple-Silicon.zip` |
| Mac with an Intel processor | `GPS-Telemetry-Visualizer-macOS-Intel.zip` |

### Which Mac Download Do I Need?

1. Click the Apple menu in the top-left corner of the screen.
2. Click `About This Mac`.
3. Look for `Chip` or `Processor`.

Choose `Apple Silicon` if the chip name starts with `Apple M`, such as M1, M2, M3, M4, or M5. Choose `Intel` if the processor name contains `Intel`.

## Install On Windows

1. Download `GPS-Telemetry-Visualizer-Windows-x64.zip`.
2. Open your Downloads folder.
3. Right-click the ZIP file and select `Extract All`.
4. Open the extracted folder.
5. Double-click `GPS Telemetry Visualizer.exe`.

Windows may show a security message the first time you open the app because the download is not code-signed yet. If you trust this repository, click `More info`, then `Run anyway`.

## Install On macOS

1. Download the ZIP file that matches your Mac.
2. Double-click the ZIP file to unzip it.
3. Drag `GPS Telemetry Visualizer.app` into your Applications folder.
4. Open your Applications folder.
5. Right-click `GPS Telemetry Visualizer.app`, then click `Open`.
6. Confirm that you want to open the app.

The right-click step is normally only needed the first time because the download is not notarized yet.

## Use The App

1. Drag a telemetry CSV file into the CSV area, or click `Browse CSV`.
2. Check the detected GPS and speed columns.
3. Choose your output folder.
4. Adjust the output type, speed units, colors, FPS, or other settings.
5. Review the preview.
6. Click `Create`.

The desktop app lets you:

- Drag and drop a CSV file
- Choose GPS, speed, heading, and altitude columns
- Set speed units, FPS, timing, and max speed
- Pick colors for the path, speedometer, dot, needle, and background
- Choose an output folder with a file browser
- Preview the overlay before creating the final video
- Export `.mp4` or `.mov`

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

Use `.mp4` for a normal video with a solid background.

Use `.mov` when you want a ProRes 4444 overlay with transparency for video editing software.

## Build From Source

The downloadable apps above are the easiest option. These instructions are for developers who want to run or modify the source code.

For the recommended local development workflow, including fast Streamlit UI testing,
see [DEVELOPMENT.md](DEVELOPMENT.md).

### Requirements

- Python 3.9 or newer
- Git, or a ZIP download of the source code

Clone the branch:

```bash
git clone https://github.com/InvertedAviatorsRC/IARC_repo.git
cd IARC_repo
git checkout codex/gps-telemetry-visualizer-package
```

Create and activate a virtual environment on macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Create and activate a virtual environment on Windows:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

Install the app:

```bash
python -m pip install -e .
```

Run the native desktop app:

```bash
gps-vis-desktop
```

## Optional Browser App

Developers can also run a local Streamlit version:

```bash
gps-vis
```

Or:

```bash
streamlit run app.py
```

## Build Desktop Downloads Locally

Install the development tools:

```bash
python -m pip install -e ".[dev]"
```

Build a macOS ZIP:

```bash
bash scripts/build_macos_app.sh
```

Build a Windows ZIP from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows_app.ps1
```

The finished ZIP file will be created in the `release` folder.

## Publish Downloads With GitHub Actions

The repository includes `.github/workflows/build-desktop-releases.yml`.

To test the builds without publishing a release:

1. Open the repository's `Actions` tab.
2. Select `Build desktop downloads`.
3. Click `Run workflow`.
4. Leave `release_tag` blank.

To publish downloadable apps:

1. Open the repository's `Actions` tab.
2. Select `Build desktop downloads`.
3. Click `Run workflow`.
4. Enter a new version in `release_tag`, such as `v0.1.0`.
5. Run the workflow.

GitHub will build and publish the Windows, Apple Silicon Mac, and Intel Mac ZIP files on the Releases page.

Pushing a Git tag that starts with `v`, such as `v0.1.0`, also publishes a release automatically.

## Command Line Rendering

Developers can render directly from a terminal:

```bash
gps-vis-render path/to/telemetry.csv output/telemetry_both_overlay.mp4 --mode both
```

Use `.mov` when you want a ProRes 4444 overlay with transparency:

```bash
gps-vis-render path/to/telemetry.csv output/telemetry_both_overlay.mov --mode both
```

## Troubleshooting Source Builds

If `gps-vis-desktop` is not found, activate the virtual environment and try again.

On macOS or Linux:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

If installation fails, upgrade `pip`:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

If the app cannot find your CSV columns, manually choose the correct GPS and speed columns in the app settings.
