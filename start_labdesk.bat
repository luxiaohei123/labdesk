@echo off
setlocal

cd /d "%~dp0"

set "PYTHON="

if exist ".venv\Scripts\pythonw.exe" (
    set "PYTHON=.venv\Scripts\pythonw.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else if exist "venv\Scripts\pythonw.exe" (
    set "PYTHON=venv\Scripts\pythonw.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PYTHON=venv\Scripts\python.exe"
) else (
    for %%P in (py.exe python.exe) do (
        if not defined PYTHON where %%P >nul 2>nul && set "PYTHON=%%P"
    )
)

if not defined PYTHON (
    echo Python was not found.
    echo Install Python 3.9+ or create a local venv, then try again.
    pause
    exit /b 1
)

%PYTHON% -c "import PIL, matplotlib" >nul 2>nul
if errorlevel 1 (
    echo Required Python packages are missing.
    echo Run: %PYTHON% -m pip install -r requirements.txt
    echo Or create a fresh virtual environment first.
    pause
    exit /b 1
)

echo Starting LabDesk...
%PYTHON% labdesk.py
set "EXITCODE=%errorlevel%"

if not "%EXITCODE%"=="0" (
    echo.
    echo LabDesk exited with an error.
    pause
)
