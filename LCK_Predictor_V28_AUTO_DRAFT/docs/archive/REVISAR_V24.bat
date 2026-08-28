@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title LCK Predictor - QA V24
if not exist "runtime\python.exe" (
  echo Abra ABRIR_LCK_PREDICTOR.bat uma vez primeiro para criar o runtime.
  pause
  exit /b 1
)
"runtime\python.exe" "scripts\qa_review_v24.py"
echo.
pause
endlocal
