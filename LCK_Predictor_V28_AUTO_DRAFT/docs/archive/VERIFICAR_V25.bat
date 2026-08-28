@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Verificar LCK Predictor V25
set "PYEXE=%~dp0runtime\python.exe"
if not exist "%PYEXE%" (
  echo Runtime ainda nao existe. Abra ABRIR_LCK_PREDICTOR.bat uma vez primeiro.
  pause
  exit /b 1
)
echo Testando agenda, versao, porta e interface V25...
"%PYEXE%" "%~dp0tests\test_v25_fresh_ui.py"
if errorlevel 1 goto ERR
"%PYEXE%" "%~dp0tests\test_core_invariants_v25.py"
if errorlevel 1 goto ERR
echo.
echo V25 OK.
echo O topo da interface deve mostrar: V25 - PORTA 8825 - NOVA INTERFACE
pause
exit /b 0
:ERR
echo.
echo FALHA NA VERIFICACAO V25.
pause
exit /b 1
