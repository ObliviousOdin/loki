@echo off
REM Loki Windows installer wrapper. Run from an authenticated checkout or release archive.
REM This project is private: download the preview using gh release download first.
echo Loki Installer
powershell -NoProfile -File "%~dp0install.ps1" %*
exit /b %ERRORLEVEL%
