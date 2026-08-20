@echo off
rem Removes the generated pak. Finds the game through Steam, so this works
rem wherever you keep this folder.
setlocal
cd /d "%~dp0"
set PY=
if exist "%~dp0runtime\python\python.exe" set "PY=%~dp0runtime\python\python.exe"
if not defined PY (
  for %%C in (py python) do (
    if not defined PY (
      %%C -c "import sys;raise SystemExit(0 if sys.version_info>=(3,11) else 1)" >nul 2>&1 && set "PY=%%C"
    )
  )
)
if defined PY (
  "%PY%" uninstall.py %*
) else (
  echo Python not found - falling back to a folder next to this one.
  set NAME=pakchunk9999-Mods_MaxSuspect_P.pak
  for %%P in ("%~dp0..\ReadyOrNot\Content\Paks\%NAME%" "%~dp0..\ReadyOrNot\Content\Paks\~mods\%NAME%") do (
    if exist "%%~P" ( del /q "%%~P" && echo Removed %%~P )
  )
)
echo.
pause
