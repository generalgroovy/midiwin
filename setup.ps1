[CmdletBinding()]
param(
    [switch]$ResetConfig,
    [switch]$NoStartup,
    [switch]$BuildExe
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Repo ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$PythonW = Join-Path $Venv "Scripts\pythonw.exe"
$ConfigDir = Join-Path $env:APPDATA "MidiWin"
$Config = Join-Path $ConfigDir "config.json"

function Resolve-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $Versions = & py -0p 2>$null
        if ($LASTEXITCODE -eq 0) {
            foreach ($Line in $Versions) {
                if ($Line -match '-V:(3\.(1[1-9]|[2-9][0-9]))') {
                    return @('py', '-3')
                }
            }
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $Version = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ([version]$Version -ge [version]'3.11') {
            return @('python')
        }
    }
    throw "Python 3.11 or newer is required. Install it with: winget install Python.Python.3.13"
}

if (-not (Test-Path $Venv)) {
    $PythonCommand = Resolve-Python
    if ($PythonCommand[0] -eq 'py') {
        & py -3 -m venv $Venv
    } else {
        & python -m venv $Venv
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

$ActiveLauncher = Join-Path $ConfigDir "start-midiwin.cmd"
@"
@echo off
cd /d "$Repo"
"$Python" -m midiwin
"@ | Set-Content -Encoding ASCII $ActiveLauncher

$GuiLauncher = Join-Path $ConfigDir "start-midiwin-gui.cmd"
@"
@echo off
cd /d "$Repo"
start "MIDIWIN" "$PythonW" -m midiwin.gui
"@ | Set-Content -Encoding ASCII $GuiLauncher

$Shell = New-Object -ComObject WScript.Shell
$Desktop = [Environment]::GetFolderPath("Desktop")
$GuiShortcut = $Shell.CreateShortcut((Join-Path $Desktop "MIDIWIN Controller Console.lnk"))
$GuiShortcut.TargetPath = $GuiLauncher
$GuiShortcut.WorkingDirectory = $Repo
$GuiShortcut.Description = "Configure and monitor Traktor F1/X1 Windows controls"
$GuiShortcut.Save()

$Programs = [Environment]::GetFolderPath("Programs")
$ProgramsShortcut = $Shell.CreateShortcut((Join-Path $Programs "MIDIWIN Controller Console.lnk"))
$ProgramsShortcut.TargetPath = $GuiLauncher
$ProgramsShortcut.WorkingDirectory = $Repo
$ProgramsShortcut.Description = "Configure and monitor Traktor F1/X1 Windows controls"
$ProgramsShortcut.Save()

if (-not $NoStartup) {
    $Startup = [Environment]::GetFolderPath("Startup")
    $Shortcut = $Shell.CreateShortcut((Join-Path $Startup "MIDIWIN Runtime.lnk"))
    $Shortcut.TargetPath = $ActiveLauncher
    $Shortcut.WorkingDirectory = $Repo
    $Shortcut.WindowStyle = 7
    $Shortcut.Save()
}

& $Python -m midiwin --validate-config
& $Python -m pytest

if ($BuildExe) {
    & (Join-Path $Repo "build-exe.ps1")
}

Write-Host ""
Write-Host "MIDIWIN installed." -ForegroundColor Green
Write-Host "GUI shortcut:    Desktop -> MIDIWIN Controller Console"
Write-Host "Open GUI:        .\launch-gui.cmd"
Write-Host "List devices:    .\.venv\Scripts\python.exe -m midiwin --list-devices"
Write-Host "Monitor input:   .\.venv\Scripts\python.exe -m midiwin --monitor"
Write-Host "Safe test:       .\.venv\Scripts\python.exe -m midiwin --dry-run"
Write-Host "Run normally:    .\.venv\Scripts\python.exe -m midiwin"
Write-Host "Config:          $Config"
