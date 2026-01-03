@echo off
:: CCG One-Click Setup Launcher for Windows
:: Double-click this file to run setup.ps1

cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
pause
