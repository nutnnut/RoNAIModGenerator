@echo off
setlocal
cd /d "%~dp0"
set PY=
for %%C in (py python) do (
  if not defined PY ( %%C -c "import sys;raise SystemExit(0 if sys.version_info>=(3,11) else 1)" >nul 2>&1 && set PY=%%C )
)
if not defined PY (
  echo.
  echo   Python 3.11 or newer is required.
  echo   Get it from https://www.python.org/downloads/  ^(tick "Add python.exe to PATH"^)
  echo.
  pause
  exit /b 1
)
%PY% app.py %*
if errorlevel 1 pause
