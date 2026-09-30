@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-keiframe.ps1"
exit /b %ERRORLEVEL%
