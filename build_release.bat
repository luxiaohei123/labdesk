@echo off
setlocal

cd /d "%~dp0"

set "PYTHON="

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PYTHON=venv\Scripts\python.exe"
) else if exist "D:\python\python.exe" (
    set "PYTHON=D:\python\python.exe"
) else (
    for %%P in (py.exe python.exe) do (
        if not defined PYTHON where %%P >nul 2>nul && set "PYTHON=%%P"
    )
)

if not defined PYTHON (
    echo Python was not found.
    pause
    exit /b 1
)

%PYTHON% -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo PyInstaller is not installed.
    echo Run: %PYTHON% -m pip install pyinstaller
    pause
    exit /b 1
)

echo Building LabDesk release...
%PYTHON% -m PyInstaller LabDesk.spec
if errorlevel 1 (
    echo.
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Build complete. See the dist\ folder.
