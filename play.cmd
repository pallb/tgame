@echo off
setlocal
pushd "%~dp0" || exit /b 1
if exist ".deps\textual" (
    set "PYTHONPATH=%~dp0.deps;%PYTHONPATH%"
    goto choose_python
)

rem In a linked worktree, .git points to its metadata directory.
if not exist ".git" goto choose_python
if exist ".git\HEAD" goto choose_python
set "worktree_git="
set /p "worktree_git="<".git"
if not "%worktree_git:~0,8%"=="gitdir: " goto choose_python
set "worktree_git=%worktree_git:~8%"
if not exist "%worktree_git%\commondir" goto choose_python
set "common_git="
set /p "common_git="<"%worktree_git%\commondir"
if not defined common_git goto choose_python
for %%D in ("%worktree_git%\%common_git%\..\.deps") do if exist "%%~fD\textual" set "PYTHONPATH=%%~fD;%PYTHONPATH%"

:choose_python
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
