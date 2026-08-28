@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Teste live LCK - KT Rolster vs HANJIN BRION

if not exist "runtime\python.exe" (
  echo ERRO: execute ABRIR_LCK_PREDICTOR.bat uma vez para preparar o runtime.
  pause
  exit /b 1
)

echo.
echo Teste agendado para 26/08/2026 as 05:00 (horario de Brasilia).
echo O servidor V28 deve estar aberto na porta 8828.
echo O monitor iniciara 20 minutos antes e salvara o log em data\live_tests.
echo.
"runtime\python.exe" "scripts\test_lck_live_match.py"
echo.
echo O teste terminou. Verifique o arquivo JSONL em data\live_tests.
pause
endlocal