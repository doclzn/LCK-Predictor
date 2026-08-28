@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title LCK Predictor V28 - Porta 8828

echo.
echo ============================================================
echo             LCK PREDICTOR V28 - AUTO DRAFT
echo ============================================================
echo.

set "PYDIR=%~dp0runtime"
set "PYEXE=%PYDIR%\python.exe"
set "PYZIP=%TEMP%\lck_python_embed.zip"
set "PYURL=https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"

if exist "%PYEXE%" goto STARTAPP

echo Primeira execucao: preparando o app...
echo.
echo O LCK Predictor vai baixar o runtime oficial do Python.org
echo para dentro desta pasta. Nao instala nada no Windows.
echo Tamanho aproximado: 11 MB.
echo.

if not exist "%PYDIR%" mkdir "%PYDIR%"

echo [1/2] Baixando runtime...
where curl.exe >nul 2>nul
if %errorlevel%==0 (
    curl.exe -L --fail --retry 2 -o "%PYZIP%" "%PYURL%"
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
      "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri '%PYURL%' -OutFile '%PYZIP%'"
)

if not exist "%PYZIP%" goto DOWNLOADERROR
for %%A in ("%PYZIP%") do if %%~zA LSS 5000000 goto DOWNLOADERROR

echo [2/2] Extraindo runtime...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "Expand-Archive -LiteralPath '%PYZIP%' -DestinationPath '%PYDIR%' -Force"

del /q "%PYZIP%" >nul 2>nul

if not exist "%PYEXE%" goto EXTRACTERROR

:STARTAPP
echo Verificando arquivos do aplicativo...
if not exist "%~dp0server.py" goto APPFILESERROR
if not exist "%~dp0riot_feed.py" goto APPFILESERROR
if not exist "%~dp0data\lck_data_v1.sqlite" goto APPFILESERROR

echo Iniciando LCK Predictor V28 na porta 8828...
echo Esta versao usa uma porta nova para NAO abrir servidores antigos.
echo.
"%PYEXE%" "%~dp0server.py"
set "APPERROR=%errorlevel%"

if "%APPERROR%"=="0" goto END
echo.
echo ============================================================
echo O servidor terminou com erro %APPERROR%.
echo A janela ficara aberta para voce poder ver o erro.
echo ============================================================
echo.
pause
goto END

:APPFILESERROR
echo.
echo ============================================================
echo ERRO: arquivos do aplicativo estao incompletos.
echo ============================================================
echo.
echo Confirme que estes arquivos existem na MESMA pasta:
echo   server.py
echo   riot_feed.py
echo   data\lck_data_v1.sqlite
echo.
echo Recomendo extrair o ZIP inteiro para uma pasta nova.
echo.
pause
goto END

:DOWNLOADERROR
echo.
echo ERRO: nao foi possivel baixar o runtime.
echo Verifique sua conexao com a internet e tente novamente.
echo.
echo URL oficial:
echo %PYURL%
echo.
pause
goto END

:EXTRACTERROR
echo.
echo ERRO: o runtime foi baixado, mas nao foi extraido corretamente.
echo Tente apagar a pasta "runtime" e executar este arquivo novamente.
echo.
pause
goto END

:END
endlocal
