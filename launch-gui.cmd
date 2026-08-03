@echo off
setlocal
set "ROOT=%~dp0"
if not exist "%ROOT%.venv\Scripts\pythonw.exe" (
  echo MIDIWIN is not installed. Run setup.ps1 first.
  pause
  exit /b 1
)
start "MIDIWIN" "%ROOT%.venv\Scripts\pythonw.exe" -m midiwin.gui
