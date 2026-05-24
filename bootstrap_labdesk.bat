@echo off
setlocal

cd /d "%~dp0"

set "PYTHON="

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else if exist ".venv\Scripts\pythonw.exe" (
    set "PYTHON=.venv\Scripts\pythonw.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PYTHON=venv\Scripts\python.exe"
) else if exist "venv\Scripts\pythonw.exe" (
    set "PYTHON=venv\Scripts\pythonw.exe"
) else (
    for %%P in (py.exe python.exe) do (
        if not defined PYTHON where %%P >nul 2>nul && set "PYTHON=%%P"
    )
)

if not defined PYTHON (
    echo Python was not found.
    echo Install Python 3.9+ first.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" if not exist ".venv\Scripts\pythonw.exe" (
    echo Creating virtual environment...
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

set "VENV_PY=.venv\Scripts\python.exe"
if not exist "%VENV_PY%" set "VENV_PY=.venv\Scripts\pythonw.exe"

echo Installing requirements...
"%VENV_PY%" -m pip install --upgrade pip --disable-pip-version-check
if errorlevel 1 goto :fail
"%VENV_PY%" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto :fail

echo Launching LabDesk...
"%VENV_PY%" labdesk.py
if errorlevel 1 goto :fail

exit /b 0

:fail
echo.
echo Setup or launch failed.
echo If pip cannot reach PyPI, install dependencies in another network
echo or use the existing working Python at D:\python\python.exe.
pause
exit /b 1
