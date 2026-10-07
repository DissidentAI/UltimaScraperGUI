@echo off
rem Construit UltimaScraper.exe et UltimaScraper-Setup.exe dans le dossier dist\
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\build.ps1"
pause
