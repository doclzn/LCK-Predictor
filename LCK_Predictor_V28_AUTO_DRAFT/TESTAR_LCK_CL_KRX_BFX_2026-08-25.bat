@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Teste live LCK Challengers - KRX vs BFX

if not exist "runtime\python.exe" (
  echo ERRO: execute ABRIR_LCK_PREDICTOR.bat uma vez para preparar o runtime.
  pause
  exit /b 1
)

echo.
echo Teste agendado para 25/08/2026 as 05:00 (horario de Brasilia).
echo Evento Riot: LCK Challengers - KRX Challengers vs BNK FEARX Youth.
echo MD5; captura de live e draft. Estatisticas ficam em modo contexto.
echo O servidor V28 deve estar aberto na porta 8828.
echo.
"runtime\python.exe" "scripts\test_lck_live_match.py" --start 2026-08-25T05:00:00-03:00 --league-id 98767991335774713 --team-a "KRX Challengers" --team-b "BNK FEARX Youth"
echo.
echo O teste terminou. Verifique o arquivo JSONL em data\live_tests.
pause
endlocal