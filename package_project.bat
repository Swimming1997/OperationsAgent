@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  AMiracle package
echo ========================================
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0package_project.ps1"
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% NEQ 0 (
    echo [FAILED] exit code: %EXIT_CODE%
) else (
    echo [DONE] package created
)
echo.
pause
endlocal & exit /b %EXIT_CODE%
