@echo off
rem Opens the generator in your browser. Nothing is installed and nothing is
rem written outside this folder until you press Build.
setlocal
cd /d "%~dp0"
call :findpy
if not defined PY (
  echo.
  echo   No Python found.
  echo.
  echo   This copy did not come with a bundled runtime. Either install Python
  echo   3.11 or newer from https://www.python.org/downloads/
  echo   ^(tick "Add python.exe to PATH"^), or download the bundled release,
  echo   which needs nothing at all.
  echo.
  pause
  exit /b 1
)
"%PY%" app.py %*
if errorlevel 1 pause
exit /b

:findpy
rem A runtime unpacked beside us wins, so the zip release never touches
rem whatever Python the machine already has.
set PY=
if exist "%~dp0runtime\python\python.exe" (
  set "PY=%~dp0runtime\python\python.exe"
  exit /b
)
for %%C in (py python) do (
  if not defined PY (
    %%C -c "import sys;raise SystemExit(0 if sys.version_info>=(3,11) else 1)" >nul 2>&1 && set "PY=%%C"
  )
)
exit /b
