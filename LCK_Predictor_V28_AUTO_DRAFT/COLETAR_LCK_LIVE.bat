@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title LCK Predictor - Live Collector
set "PYEXE=%~dp0runtime\python.exe"
if not exist "%PYEXE%" (
  echo O runtime portatil ainda nao existe.
  echo Execute ABRIR_LCK_PREDICTOR.bat uma vez primeiro.
  echo.
  pause
  exit /b 1
)
if not exist "%~dp0server.py" goto ERROR
if not exist "%~dp0riot_feed.py" goto ERROR
if not exist "%~dp0data\lck_data_v1.sqlite" goto ERROR
set "LCK_COLLECTOR_ONLY=1"
echo ============================================================
echo          LCK PREDICTOR - LIVE COLLECTOR V20
echo ============================================================
echo.
echo Deixe esta janela aberta durante as partidas da LCK.
echo O coletor procura eventos Riot, guarda snapshots brutos e cria
echo um dataset compacto de 1 checkpoint por minuto de jogo.
echo.
echo Ctrl+C encerra o coletor.
echo.
"%PYEXE%" "%~dp0server.py"
exit /b %errorlevel%
:ERROR
echo Arquivos do aplicativo incompletos.
pause
exit /b 1
