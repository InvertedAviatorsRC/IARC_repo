$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$env:PYINSTALLER_CONFIG_DIR = Join-Path (Get-Location) ".pyinstaller-cache"
New-Item -ItemType Directory -Force -Path $env:PYINSTALLER_CONFIG_DIR | Out-Null
$env:MPLCONFIGDIR = Join-Path $env:PYINSTALLER_CONFIG_DIR "matplotlib"
New-Item -ItemType Directory -Force -Path $env:MPLCONFIGDIR | Out-Null

python scripts/prepare_app_icon.py

python -m PyInstaller `
  --name "GPS Telemetry Visualizer" `
  --windowed `
  --noconfirm `
  --clean `
  --icon "$env:PYINSTALLER_CONFIG_DIR\gps_app_icon.png" `
  --add-data "gps_telemetry_visualizer;gps_telemetry_visualizer" `
  --collect-all streamlit `
  --collect-all gps_telemetry_visualizer `
  --collect-all imageio_ffmpeg `
  --hidden-import matplotlib.backends.backend_agg `
  streamlit_desktop_app.py

$archive = "release\GPS-Telemetry-Visualizer-Windows-x64.zip"
New-Item -ItemType Directory -Force -Path "release" | Out-Null
Remove-Item -Force -ErrorAction SilentlyContinue $archive
Compress-Archive -Path "dist\GPS Telemetry Visualizer" -DestinationPath $archive

Write-Host "Built $archive"
