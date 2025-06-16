@echo off
REM Enhanced Daily Teams Monitor Batch Script
REM Supports multiple users and continuous monitoring

REM Configuration
set CHECK_INTERVAL=15
set "LOG_PATH=C:\Teams Monitoring Logs"
set "USER_LIST_FILE=%LOG_PATH%\users.txt"

REM For continuous monitoring (24/7), use these settings:
set START_TIME=00:00
set END_TIME=23:59
set CONTINUOUS_MODE=-ContinuousMode

REM For time-based monitoring, comment out CONTINUOUS_MODE and set specific times:
REM set START_TIME=09:00
REM set END_TIME=17:00
REM set CONTINUOUS_MODE=

REM Create log directory
if not exist "%LOG_PATH%" mkdir "%LOG_PATH%"

REM Create sample users.txt file if it doesn't exist
if not exist "%USER_LIST_FILE%" (
    echo # Teams Monitoring User List > "%USER_LIST_FILE%"
    echo # Add one email per line, lines starting with # are ignored >> "%USER_LIST_FILE%"
    echo # employee1@company.com >> "%USER_LIST_FILE%"
    echo # employee2@company.com >> "%USER_LIST_FILE%"
    echo. >> "%USER_LIST_FILE%"
    echo Please edit "%USER_LIST_FILE%" and add the email addresses to monitor
    pause
    exit /b
)

echo ================================================================
echo Enhanced Teams Status Monitor
echo ================================================================
echo User List File: "%USER_LIST_FILE%"
echo Check Interval: Every %CHECK_INTERVAL% minutes
echo Monitoring Hours: %START_TIME% to %END_TIME%
if defined CONTINUOUS_MODE echo Mode: Continuous (24/7)
echo Log Directory: "%LOG_PATH%"
echo.
echo Starting monitoring...
echo.

REM Run the PowerShell monitoring script
powershell.exe -ExecutionPolicy Bypass -File "TeamsMonitor.ps1" -UserListFile "%USER_LIST_FILE%" -CheckIntervalMinutes %CHECK_INTERVAL% -StartTime "%START_TIME%" -EndTime "%END_TIME%" -LogPath "%LOG_PATH%" %CONTINUOUS_MODE%

echo.
echo Monitoring session completed.
pause
