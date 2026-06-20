@echo off
set "PROJECT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%local_agent\scripts\start_local_workspace.ps1"
if errorlevel 1 (
  echo.
  echo Failed to start the local workspace. See the error above.
  pause
)
