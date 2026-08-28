@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Importar Historico LCK

echo ============================================================
echo          LCK PREDICTOR - IMPORTAR HISTORICO
echo ============================================================
echo.
if not exist "runtime\python.exe" (
  echo O runtime portatil ainda nao existe.
  echo Abra ABRIR_LCK_PREDICTOR.bat uma vez primeiro.
  echo.
  pause
  exit /b 1
)
if not exist "scripts\import_lck_history.py" (
  echo Importador nao encontrado.
  pause
  exit /b 1
)

echo Este importador NAO baixa nem redistribui automaticamente
echo arquivos historicos de terceiros.
echo.
echo Informe uma pasta contendo CSVs no formato Oracle's Elixir.
echo Exemplo: C:\Dados\OracleElixir
echo.
set /p "HISTORY_DIR=Pasta dos CSVs: "
if "%HISTORY_DIR%"=="" exit /b 1

"runtime\python.exe" "scripts\import_lck_history.py" "%HISTORY_DIR%"
echo.
pause
endlocal
