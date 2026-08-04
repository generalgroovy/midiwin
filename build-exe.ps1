[CmdletBinding()]
param(
  [string]$Python
)
$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $Python) {
  $ProjectPython = Join-Path $Repo '.venv\Scripts\python.exe'
  if (Test-Path $ProjectPython) {
    $Python = $ProjectPython
  } else {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCommand) {
      $Python = $PythonCommand.Source
    }
  }
}

if (-not $Python -or -not (Test-Path $Python)) {
  throw 'Python was not found. Run setup.ps1 or pass -Python C:\path\to\python.exe.'
}

Write-Host "Building MIDIWIN with $Python" -ForegroundColor Cyan
& $Python -m pip install -e "$Repo[build]"
if ($LASTEXITCODE -ne 0) { throw 'Build dependencies could not be installed.' }

& $Python -m PyInstaller --noconfirm --clean --windowed `
  --name MIDIWIN `
  --collect-all libusb_package `
  --collect-all screen_brightness_control `
  --add-data "$Repo\config.default.json;." `
  "$Repo\midiwin-gui.py"
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }

$Executable = Join-Path $Repo 'dist\MIDIWIN\MIDIWIN.exe'
if (-not (Test-Path $Executable)) {
  throw "PyInstaller reported success but the executable is missing: $Executable"
}
Write-Host "Executable: $Executable" -ForegroundColor Green
