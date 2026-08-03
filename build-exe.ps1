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
  --hidden-import screen_brightness_control `
  --add-data "$Repo\config.default.json;." `
  "$Repo\midiwin\gui.py"
Write-Host "Executable: $Repo\dist\MIDIWIN\MIDIWIN.exe" -ForegroundColor Green
