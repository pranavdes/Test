@echo off
REM Daily Teams Monitor Batch Script
REM Set up your parameters here

REM Configuration
set USER_EMAIL=employee@company.com
set CHECK_INTERVAL=15
set START_TIME=09:00
set END_TIME=17:00
set LOG_PATH=C:\TeamsMonitoring

REM Create log directory
if not exist "%LOG_PATH%" mkdir "%LOG_PATH%"

REM Run the PowerShell monitoring script
echo Starting daily Teams monitoring for %USER_EMAIL%
echo Monitoring from %START_TIME% to %END_TIME%
echo Check interval: Every %CHECK_INTERVAL% minutes
echo.

powershell.exe -ExecutionPolicy Bypass -File "TeamsMonitor.ps1" -UserEmail "%USER_EMAIL%" -CheckIntervalMinutes %CHECK_INTERVAL% -StartTime "%START_TIME%" -EndTime "%END_TIME%" -LogPath "%LOG_PATH%"

echo.
echo Monitoring session completed.
pause
