[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Repo '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw 'Run setup.ps1 first.' }
& $Python -m pip install -e "$Repo[build]"
& $Python -m PyInstaller --noconfirm --clean --windowed `
  --name MIDIWIN `
  --collect-all libusb_package `
  --collect-all screen_brightness_control `
  --add-data "$Repo\config.default.json;." `
  "$Repo\midiwin-gui.py"
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
Write-Host "Executable: $Repo\dist\MIDIWIN\MIDIWIN.exe" -ForegroundColor Green
