@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Teste LCK Predictor

echo ============================================================
echo             TESTE DE INSTALACAO - LCK PREDICTOR
echo ============================================================
echo.

if not exist "server.py" (
  echo [ERRO] server.py ausente
  goto FAIL
)
if not exist "riot_feed.py" (
  echo [ERRO] riot_feed.py ausente
  goto FAIL
)
if not exist "data\lck_data_v1.sqlite" (
  echo [ERRO] banco de dados ausente
  goto FAIL
)

echo [OK] server.py
echo [OK] riot_feed.py
echo [OK] banco SQLite

if not exist "runtime\python.exe" (
  echo.
  echo Runtime ainda nao foi baixado. Rode ABRIR_LCK_PREDICTOR.bat primeiro.
  goto END
)

echo.
echo Testando import local com o Python portatil...
"runtime\python.exe" -c "import sys; from pathlib import Path; p=str(Path(r'%CD%').resolve()); sys.path.insert(0,p); import riot_feed; print('[OK] riot_feed importado:', riot_feed.__file__)"
if errorlevel 1 goto FAIL

echo.
echo [OK] Instalacao pronta.
goto END

:FAIL
echo.
echo [FALHA] Extraia novamente o ZIP completo em uma pasta nova.

:END
echo.
pause
endlocal
