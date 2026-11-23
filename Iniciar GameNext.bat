@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 11))" >nul 2>nul
    if not errorlevel 1 set "PYTHON=py -3"
)
if not defined PYTHON (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(sys.version_info < (3, 11))" >nul 2>nul
        if not errorlevel 1 set "PYTHON=python"
    )
)
if not defined PYTHON (
    echo Python 3.11 ou superior nao foi encontrado.
    echo Instale Python em https://www.python.org/downloads/ e execute este BAT novamente.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente Python...
    %PYTHON% -m venv .venv
    if errorlevel 1 goto :error
)

echo Instalando ou atualizando dependencias...
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -e .
if errorlevel 1 goto :error

echo Preparando runtime e modelo local. O modelo ocupa cerca de 2,1 GB.
.venv\Scripts\python.exe setup_runtime.py
if errorlevel 1 goto :error

echo Iniciando GameNext...
.venv\Scripts\python.exe run.py
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo A inicializacao falhou. Leia a mensagem acima e execute este BAT novamente apos corrigir o problema.
pause
exit /b 1
