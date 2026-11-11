@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%PYTHON%" (
  "%PYTHON%" aplicativo\app.py
) else (
  py aplicativo\app.py
)
if errorlevel 1 (
  echo Nao foi possivel iniciar. Consulte LEIA-ME.md.
  pause
)
