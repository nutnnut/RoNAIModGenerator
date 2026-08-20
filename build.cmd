@echo off
rem Command-line build using config.toml. The web UI is the normal way in:
rem run "MAX SUSPECT Generator.cmd" instead.
setlocal
cd /d "%~dp0"
set PY=python
if exist "%~dp0runtime\python\python.exe" set "PY=%~dp0runtime\python\python.exe"
"%PY%" generate.py %*
if errorlevel 1 pause
