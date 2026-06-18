@echo off
REM Easy BDD Server Restart Script for Windows
REM Stops any running server instances and starts a fresh one

echo.
echo ========================================
echo Easy BDD Server Restart Script
echo ========================================
echo.

REM Get the script directory
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Step 1: Find and stop running server processes
echo Step 1: Stopping existing server processes...

REM Find processes using port 8000 (Windows)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo   Stopping process %%a...
    taskkill /PID %%a /F >nul 2>&1
)

REM Also find Python processes running start_builder.py
for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq python.exe" /FO CSV ^| findstr /V "INFO:"') do (
    wmic process where "ProcessId=%%a" get CommandLine 2>nul | findstr /i "start_builder.py" >nul
    if !errorlevel! == 0 (
        echo   Stopping start_builder.py process %%a...
        taskkill /PID %%a /F >nul 2>&1
    )
)

timeout /t 2 /nobreak >nul
echo   Server processes stopped
echo.

REM Step 2: Start the server
echo Step 2: Starting server...
echo   Server will be available at: http://localhost:8000
echo   API docs will be at: http://localhost:8000/docs
echo.
echo   Press Ctrl+C to stop the server
echo.

cd frontend
python start_builder.py

