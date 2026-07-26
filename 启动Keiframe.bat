@echo off
setlocal EnableExtensions

set "PROJECT_DIR=%~dp0"
set "PYTHONW=%PROJECT_DIR%.venv\Scripts\pythonw.exe"

if not exist "%PYTHONW%" (
    echo [ERROR] Keiframe Python runtime was not found:
    echo %PYTHONW%
    echo Keep the .venv folder inside the project directory.
    pause
    exit /b 1
)

rem Avoid starting a second Keiframe background process.
powershell.exe -NoProfile -Command "$running = @(Get-CimInstance Win32_Process).Where({ $_.Name -in @('python.exe', 'pythonw.exe') -and $_.CommandLine -match '-m\s+src\.main' }); if ($running.Count -gt 0) { exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 (
    start "" /d "%PROJECT_DIR%" "%PYTHONW%" -m src.main
    echo Keiframe started.
    powershell.exe -NoProfile -Command "Start-Sleep -Milliseconds 800"
) else (
    echo Keiframe is already running.
)

rem Activate the widget first, then open Xbox Game Bar so it is immediately editable.
powershell.exe -NoProfile -Command "Start-Process 'ms-gamebar:/activate/Keiframe.GameBar_83kdtmzvrsrdt_App_KeiframeOverlay'; Start-Sleep -Milliseconds 500; $gameBar = Get-AppxPackage Microsoft.XboxGamingOverlay; if (-not $gameBar) { exit 1 }; Start-Process -FilePath (Join-Path $gameBar.InstallLocation 'GameBar.exe')" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Xbox Game Bar could not be opened automatically.
    echo Open Xbox Game Bar once from the Start menu, then run this file again.
    endlocal
    exit /b 2
)

echo Xbox Game Bar and the Keiframe widget are open.
echo Pin the widget and enable click-through using the mouse icon in the top toolbar.
echo Press Esc to return to the game while keeping the pinned overlay visible.

endlocal
exit /b 0
