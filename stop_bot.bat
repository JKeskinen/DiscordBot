@echo off
REM Stop any running MetrixBot instances that were started from this project.
echo Stopping MetrixBot processes...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -match 'metrixbot_verifiedWorking.py' } | ForEach-Object { Try { Stop-Process -Id $_.ProcessId -Force } Catch { } }"
echo Done.
exit /b 0
