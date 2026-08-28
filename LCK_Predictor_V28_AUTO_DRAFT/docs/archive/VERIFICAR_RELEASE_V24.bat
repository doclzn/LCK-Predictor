@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist "runtime\python.exe" (
  echo Abra ABRIR_LCK_PREDICTOR.bat uma vez primeiro.
  pause
  exit /b 1
)
"runtime\python.exe" "scripts\verify_release_v24.py"
pause
