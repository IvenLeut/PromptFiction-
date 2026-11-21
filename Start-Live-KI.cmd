@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-FounderRadar.ps1" -LiveAI %*
if errorlevel 1 pause
