@echo off
REM Start the MetrixBot in the project's virtual environment.
REM Double-click this file to start the bot detached.

SET SCRIPT_DIR=%~dp0
SET PYTHON=%SCRIPT_DIR%\.venv\Scripts\python.exe

IF NOT EXIST "%PYTHON%" (
    echo Virtual environment not found. Create it with: python -m venv .venv
    pause
    exit /b 1
)

REM Configure capacity worker interval (seconds) and thread for alerts
SET CAPACITY_CHECK_INTERVAL=3600
SET CAPACITY_THREAD_ID=1241493648080764988

echo Starting MetrixBot...
start "MetrixBot" "%PYTHON%" "%SCRIPT_DIR%metrixbot_verifiedWorking.py" --daemon --presence
echo MetrixBot start command issued.
exit /b 0
