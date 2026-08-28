@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title LCK Predictor - Live Model V21

echo ============================================================
echo          LIVE MODEL - PROTOCOLO PRE-REGISTRADO V21
echo ============================================================
echo.
if not exist "runtime\python.exe" (
  echo O runtime portatil ainda nao existe.
  echo Abra ABRIR_LCK_PREDICTOR.bat uma vez primeiro.
  echo.
  pause
  exit /b 1
)
"runtime\python.exe" "scripts\train_live_model_v21.py"
echo.
echo Se o gate ainda nao tiver sido atingido, nenhum modelo sera treinado.
echo Se o protocolo ja tiver aberto o test set, o script recusara novo retuning.
echo.
pause
endlocal
