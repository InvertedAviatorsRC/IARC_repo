# Local Development

This guide is for working on GPS Telemetry Visualizer from source. For normal use,
download the packaged desktop app from the project releases. Local source runs are
faster when you are changing the UI, preview layout, timeline, colors, or editor
interactions.

## Requirements

- Git
- Python 3.9 or newer
- macOS or Linux for the included Bash helper scripts

Windows developers can use the same Python commands from PowerShell; the supplied
Windows package build script is `scripts/build_windows_app.ps1`.

## Get The Source

Clone the repository and enter it:

```bash
git clone https://github.com/InvertedAviatorsRC/IARC_repo.git
cd IARC_repo
```

To work on a branch created by Codex, first fetch the latest remote branches, then
switch to the branch name supplied with the change:

```bash
git fetch origin
git switch codex/<branch-name>
git pull --ff-only
```

If this is the first time the branch is used locally, Git may ask you to create a
tracking branch. This command does that explicitly:

```bash
git switch --track origin/codex/<branch-name>
```

For an existing checkout, update your current branch before starting work:

```bash
git pull --ff-only
```

## Recommended Local Iteration Workflow

For UI and layout work, do not wait for GitHub Actions to build the desktop app
after every change.

1. Run `./dev_setup.sh` once.
2. Run `./dev_run_streamlit.sh` for the fastest UI iteration loop.
3. Edit the local source files.
4. Refresh the browser, or let Streamlit reload automatically.
5. Run `./dev_test.sh`.
6. Run `./dev_run_desktop.sh` only when you need to test the native desktop wrapper.
7. Push and trigger the GitHub desktop build only after the feature looks good locally.

The same commands are available through `make`:

```bash
make setup
make streamlit
make test
make desktop
make build
```

## First-Time Setup

Run the setup script from the repository root:

```bash
./dev_setup.sh
```

It creates `.venv` when needed, installs the project in editable mode, and installs
the test and packaging tools. Editable mode means changes to the source code are used
immediately; you do not need to reinstall the project after every edit.

If your normal `python3` command points to an older Python, run setup with a newer
interpreter explicitly:

```bash
PYTHON_BIN=/path/to/python3.12 ./dev_setup.sh
```

## Run The Streamlit UI

For preview, layout, timeline, drag, resize-handle, color, and warning changes, run:

```bash
./dev_run_streamlit.sh
```

The terminal prints a local address, normally `http://localhost:8501`. Open it in a
browser. Streamlit watches the source files and reloads after relevant changes.
Press `Ctrl-C` in the terminal to stop it.

## Run The Desktop App From Source

To test the native wrapper without creating a packaged `.app`:

```bash
./dev_run_desktop.sh
```

This starts `gps-vis-desktop` from the editable local install. Close the app window
when finished.

## Run Tests

Run the automated suite before sharing changes:

```bash
./dev_test.sh
```

This runs `pytest -q` against the local source tree.

## Optional Local Desktop Build

Desktop builds are slower and are not needed for ordinary Streamlit UI work. On
macOS, build a local app and ZIP only when you need to test the packaged result:

```bash
./dev_build_desktop.sh
```

The build outputs go to `dist/` and `release/`. On Windows, use PowerShell instead:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows_app.ps1
```

Use the GitHub Actions Apple Silicon build when you need the distributable ZIP for
other Mac users, need a clean build environment, or are ready to publish a release.
It is not the recommended loop for ordinary UI changes.

## Commit And Push When Ready

Once the feature is working locally and tests pass:

```bash
git status
git add <files-you-changed>
git commit -m "Describe the change"
git push -u origin HEAD
```

Open a pull request or merge according to the repository workflow. Trigger the
GitHub Actions desktop build only after the source-based checks look right locally.
