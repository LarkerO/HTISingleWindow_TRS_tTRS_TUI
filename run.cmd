@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1
if exist ".venv\Scripts\python.exe" goto venv
where uv >nul 2>nul
if not errorlevel 1 goto uv
if exist ".deps\textual" if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" goto bundled
echo Please install Python 3.12+ and run pip install -e . in a virtualenv, or use uv sync --locked.
popd
exit /b 1
:venv
".venv\Scripts\python.exe" -m ttrs %*
goto done
:uv
call uv run --locked ttrs %*
goto done
:bundled
"%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" dev.py %*
:done
set "ttrsExit=%errorlevel%"
popd
exit /b %ttrsExit%
