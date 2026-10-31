@echo off
setlocal
cd /d "%~dp0"
title Coliseum demo

echo ==========================================
echo   Coliseum  -  agentic trading orgs (sim)
echo ==========================================
echo.

rem ---- find a working Python (skip the Microsoft Store stub, which exits 9009)
set "PY="
for %%P in (py python python3) do (
  if not defined PY (
    %%P -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>&1 && set "PY=%%P"
  )
)
for %%V in (312 313 311) do (
  if not defined PY if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" set "PY=%LocalAppData%\Programs\Python\Python%%V\python.exe"
)
if not defined PY (
  echo Python 3.11+ not found. Installing Python 3.12 with winget ^(you may get a prompt^)...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
)
if not defined PY (
  echo.
  echo Could not find or install Python. Get it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" in the installer, then run this file again.
  start https://www.python.org/downloads/
  pause
  exit /b 1
)
echo Using Python: %PY%

rem ---- virtual env + deps (first run takes a minute or two)
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  "%PY%" -m venv .venv || goto :fail
)
set "VPY=%~dp0.venv\Scripts\python.exe"
echo Installing dependencies...
"%VPY%" -m pip install -q --upgrade pip
"%VPY%" -m pip install -q -r requirements.txt || goto :fail

echo.
echo Starting Coliseum. Your browser will open http://localhost:8000
echo Close this window (or press Ctrl-C) to stop everything.
echo.
"%VPY%" scripts\demo.py || goto :fail
exit /b 0

:fail
echo.
echo Something went wrong - scroll up for the error.
pause
exit /b 1
