@echo off
setlocal
pushd "%~dp0" || exit /b 1
if exist ".deps\textual" set "PYTHONPATH=%~dp0.deps;%PYTHONPATH%"

py -3 -c "import sys, sqlite3; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
    py -3 -m rpg %*
    goto done
)

set "bundled=%ProgramFiles%\WindowsApps\OpenAI.CodexPrimaryRuntime.v26-1123-915-0_26.1123.915.0_x64__3k8sg7r9htsxt\dependencies\python\python.exe"
"%bundled%" -c "import sqlite3" >nul 2>&1
if not errorlevel 1 goto bundled

for /f "usebackq delims=" %%P in (`powershell.exe -NoProfile -Command "(Get-AppxPackage -Name OpenAI.CodexPrimaryRuntime -ErrorAction SilentlyContinue).InstallLocation"`) do set "bundled=%%P\dependencies\python\python.exe"
"%bundled%" -c "import sqlite3" >nul 2>&1
if not errorlevel 1 goto bundled

python -c "import sys, sqlite3; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
    python -m rpg %*
    goto done
)

echo Ashenfell needs Python 3.10 or newer. Install Python and reopen your terminal. 1>&2
popd
exit /b 1

:bundled
"%bundled%" -m rpg %*

:done
set "result=%errorlevel%"
popd
exit /b %result%
