[CmdletBinding()]
param(
    [switch]$ResetConfig,
    [switch]$NoStartup
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Repo ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$ConfigDir = Join-Path $env:APPDATA "MidiWin"
$Config = Join-Path $ConfigDir "config.json"

if (-not (Get-Command py -ErrorAction SilentlyContinue) -and
    -not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.11 or newer is required. Install it from python.org or winget."
}

if (-not (Test-Path $Venv)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3.11 -m venv $Venv
    } else {
        python -m venv $Venv
    }
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -e "$Repo[dev]"

New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ConfigDir "scripts") | Out-Null

if ($ResetConfig -and (Test-Path $Config)) {
    $Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Copy-Item $Config "$Config.backup-$Stamp"
    Remove-Item $Config
}
if (-not (Test-Path $Config)) {
    Copy-Item (Join-Path $Repo "config.default.json") $Config
}

if (-not $NoStartup) {
    $Startup = [Environment]::GetFolderPath("Startup")
    $Launcher = Join-Path $ConfigDir "start-midiwin.cmd"
    @"
@echo off
cd /d "$Repo"
"$Python" -m midiwin
"@ | Set-Content -Encoding ASCII $Launcher
    $ShortcutPath = Join-Path $Startup "MIDIWIN.lnk"
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $Launcher
    $Shortcut.WorkingDirectory = $Repo
    $Shortcut.WindowStyle = 7
    $Shortcut.Save()
}

& $Python -m midiwin --validate-config
& $Python -m pytest

Write-Host ""
Write-Host "MIDIWIN installed." -ForegroundColor Green
Write-Host "List devices:  .\.venv\Scripts\python.exe -m midiwin --list-devices"
Write-Host "Monitor input:  .\.venv\Scripts\python.exe -m midiwin --monitor"
Write-Host "Safe test:      .\.venv\Scripts\python.exe -m midiwin --dry-run"
Write-Host "Run normally:   .\.venv\Scripts\python.exe -m midiwin"
Write-Host "Config:         $Config"
