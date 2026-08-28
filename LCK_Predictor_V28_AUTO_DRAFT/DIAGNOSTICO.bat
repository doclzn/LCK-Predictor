@echo off
cd /d "%~dp0"
title Diagnostico LCK Predictor
echo LCK Predictor - Diagnostico
echo ==========================
echo.
echo Pasta: %CD%
echo.
if exist "runtime\python.exe" (
  echo [OK] Runtime encontrado.
  "runtime\python.exe" -c "import sys,sqlite3; print('[OK] Python',sys.version); print('[OK] SQLite',sqlite3.sqlite_version)"
) else (
  echo [!] Runtime ainda nao foi baixado.
)
echo.
if exist "data\lck_data_v1.sqlite" (
  echo [OK] Database encontrada.
) else (
  echo [ERRO] Database ausente.
)
echo.
if exist "static\index.html" (
  echo [OK] Interface encontrada.
) else (
  echo [ERRO] Interface ausente.
)
echo.
pause
