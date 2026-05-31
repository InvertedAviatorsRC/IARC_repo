$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$env:PYINSTALLER_CONFIG_DIR = Join-Path (Get-Location) ".pyinstaller-cache"
New-Item -ItemType Directory -Force -Path $env:PYINSTALLER_CONFIG_DIR | Out-Null
$env:MPLCONFIGDIR = Join-Path $env:PYINSTALLER_CONFIG_DIR "matplotlib"
New-Item -ItemType Directory -Force -Path $env:MPLCONFIGDIR | Out-Null

python -m PyInstaller `
  --name "GPS Telemetry Visualizer" `
  --windowed `
  --noconfirm `
  --clean `
  --collect-all imageio_ffmpeg `
  --hidden-import matplotlib.backends.backend_agg `
  desktop_app.py

$archive = "release\GPS-Telemetry-Visualizer-Windows-x64.zip"
New-Item -ItemType Directory -Force -Path "release" | Out-Null
Remove-Item -Force -ErrorAction SilentlyContinue $archive
Compress-Archive -Path "dist\GPS Telemetry Visualizer" -DestinationPath $archive

Write-Host "Built $archive"
