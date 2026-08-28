@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title LCK Predictor - Governanca V21

echo ============================================================
echo          LCK PREDICTOR - MODEL GOVERNANCE V21
echo ============================================================
echo.
if not exist "runtime\python.exe" (
  echo O runtime portatil ainda nao existe.
  echo Abra ABRIR_LCK_PREDICTOR.bat uma vez primeiro.
  echo.
  pause
  exit /b 1
)
"runtime\python.exe" "scripts\governance_report_v21.py"
echo.
pause
endlocal
