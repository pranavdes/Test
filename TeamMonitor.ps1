# Enhanced Teams Status Monitor Script
# Monitors multiple users' Teams presence status with instance checking
# Requires: Microsoft Graph PowerShell SDK installed (Install-Module Microsoft.Graph)

param(
    [Parameter(Mandatory=$false)]
    [string[]]$UserEmails = @(),
    
    [Parameter(Mandatory=$false)]
    [string]$UserListFile = "",
    
    [Parameter(Mandatory=$false)]
    [int]$CheckIntervalMinutes = 15,
    
    [Parameter(Mandatory=$false)]
    [string]$LogPath = ".\TeamsMonitoring",
    
    [Parameter(Mandatory=$false)]
    [string]$StartTime = "00:00",  # Use 00:00 for continuous monitoring
    
    [Parameter(Mandatory=$false)]
    [string]$EndTime = "23:59",    # Use 23:59 for continuous monitoring
    
    [Parameter(Mandatory=$false)]
    [switch]$ContinuousMode = $false
)

# Script instance management
$ScriptName = "TeamsStatusMonitor"
$MutexName = "Global\$ScriptName"

# Function to check if another instance is running
function Test-ScriptInstance {
    try {
        $mutex = [System.Threading.Mutex]::new($false, $MutexName)
        $acquired = $mutex.WaitOne(0)
        
        if (-not $acquired) {
            Write-Host "Another instance of $ScriptName is already running. Exiting..." -ForegroundColor Red
            exit 1
        }
        
        Write-Host "Script instance check passed. Proceeding..." -ForegroundColor Green
        return $mutex
    }
    catch {
        Write-Error "Error checking script instance: $($_.Exception.Message)"
        exit 1
    }
}

# Function to load user emails from file
function Get-UserEmailList {
    param($FilePath)
    
    if (Test-Path $FilePath) {
        try {
            $emails = Get-Content $FilePath | Where-Object { $_ -match '\S' -and $_ -notmatch '^#' }
            Write-Host "Loaded $($emails.Count) user emails from file: $FilePath" -ForegroundColor Green
            return $emails
        }
        catch {
            Write-Error "Error reading user list file: $($_.Exception.Message)"
            return @()
        }
    }
    else {
        Write-Warning "User list file not found: $FilePath"
        return @()
    }
}

# Import required modules
try {
    Import-Module Microsoft.Graph.Users -ErrorAction Stop
    Import-Module Microsoft.Graph.CloudCommunications -ErrorAction Stop
}
catch {
    Write-Error "Microsoft Graph modules not found. Please install with: Install-Module Microsoft.Graph"
    exit 1
}

# Create log directory if it doesn't exist
if (!(Test-Path $LogPath)) {
    New-Item -ItemType Directory -Path $LogPath -Force
}

# Function to connect to Microsoft Graph
function Connect-ToGraph {
    try {
        # Check if already connected
        $context = Get-MgContext -ErrorAction SilentlyContinue
        if ($context) {
            Write-Host "Already connected to Microsoft Graph" -ForegroundColor Green
            return $true
        }
        
        # Connect with user authentication (delegated permissions)
        Connect-MgGraph -Scopes "Presence.Read", "User.Read.All" -NoWelcome
        Write-Host "Connected to Microsoft Graph successfully" -ForegroundColor Green
        return $true
    }
    catch {
        Write-Error "Failed to connect to Microsoft Graph: $($_.Exception.Message)"
        return $false
    }
}

# Function to get user's presence status
function Get-UserPresence {
    param([string]$Email)
    
    try {
        # Get user ID from email
        $user = Get-MgUser -Filter "mail eq '$Email' or userPrincipalName eq '$Email'" -ErrorAction Stop
        if (!$user) {
            Write-Warning "User not found: $Email"
            return $null
        }
        
        # Get presence information
        $presence = Get-MgUserPresence -UserId $user.Id -ErrorAction Stop
        
        return @{
            Timestamp = Get-Date
            UserId = $user.Id
            DisplayName = $user.DisplayName
            Email = $Email
            Availability = $presence.Availability
            Activity = $presence.Activity
        }
    }
    catch {
        Write-Warning "Error getting presence for $Email : $($_.Exception.Message)"
        return $null
    }
}

# Function to log status to file
function Write-StatusLog {
    param($Status, $LogFile)
    
    if ($Status) {
        $logEntry = "$($Status.Timestamp.ToString('yyyy-MM-dd HH:mm:ss')),$($Status.Email),$($Status.DisplayName),$($Status.Availability),$($Status.Activity)"
        Add-Content -Path $LogFile -Value $logEntry -ErrorAction SilentlyContinue
    }
}

# Function to generate daily summary for a user
function Generate-UserDailySummary {
    param($Email, $LogFile, $SummaryFile)
    
    if (!(Test-Path $LogFile)) {
        Write-Warning "Log file not found: $LogFile"
        return
    }
    
    $logs = Import-Csv $LogFile -Header "Timestamp","Email","DisplayName","Availability","Activity" | 
            Where-Object { $_.Email -eq $Email }
    
    if ($logs.Count -eq 0) {
        return
    }
    
    # Calculate statistics
    $totalChecks = $logs.Count
    $availableCount = ($logs | Where-Object { $_.Availability -eq "Available" }).Count
    $awayCount = ($logs | Where-Object { $_.Availability -eq "Away" }).Count
    $offlineCount = ($logs | Where-Object { $_.Availability -eq "Offline" }).Count
    $busyCount = ($logs | Where-Object { $_.Availability -eq "Busy" }).Count
    $doNotDisturbCount = ($logs | Where-Object { $_.Availability -eq "DoNotDisturb" }).Count
    
    $firstCheck = [DateTime]::Parse($logs[0].Timestamp)
    $lastCheck = [DateTime]::Parse($logs[-1].Timestamp)
    
    # Generate summary
    $summary = @"
Daily Teams Status Summary - $(Get-Date -Format 'yyyy-MM-dd')
================================================================
Employee: $($logs[0].DisplayName) ($($logs[0].Email))
Monitoring Period: $($firstCheck.ToString('HH:mm')) - $($lastCheck.ToString('HH:mm'))
Total Status Checks: $totalChecks
Check Interval: Every $CheckIntervalMinutes minutes

Status Breakdown:
- Available: $availableCount checks ($([math]::Round(($availableCount/$totalChecks)*100,1))%)
- Away: $awayCount checks ($([math]::Round(($awayCount/$totalChecks)*100,1))%)
- Busy: $busyCount checks ($([math]::Round(($busyCount/$totalChecks)*100,1))%)
- Do Not Disturb: $doNotDisturbCount checks ($([math]::Round(($doNotDisturbCount/$totalChecks)*100,1))%)
- Offline: $offlineCount checks ($([math]::Round(($offlineCount/$totalChecks)*100,1))%)

Activity Summary:
- First Activity: $($firstCheck.ToString('yyyy-MM-dd HH:mm:ss'))
- Last Activity: $($lastCheck.ToString('yyyy-MM-dd HH:mm:ss'))
- Total Monitoring Duration: $([math]::Round(($lastCheck - $firstCheck).TotalHours, 2)) hours

Recent Timeline (Last 20 entries):
"@
    
    $recentLogs = $logs | Select-Object -Last 20
    foreach ($log in $recentLogs) {
        $time = [DateTime]::Parse($log.Timestamp).ToString('HH:mm')
        $summary += "`n$time - $($log.Availability) ($($log.Activity))"
    }
    
    $summary | Out-File -FilePath $SummaryFile -Encoding UTF8
    Write-Host "Daily summary generated for $Email : $SummaryFile" -ForegroundColor Green
}

# Function to create/initialize log files for users
function Initialize-UserLogFiles {
    param([string[]]$Emails)
    
    $today = Get-Date -Format "yyyy-MM-dd"
    $logFiles = @{}
    
    foreach ($email in $Emails) {
        $safeEmail = $email.Replace('@','_').Replace('.','_')
        $logFile = Join-Path $LogPath "teams_status_${safeEmail}_$today.csv"
        
        # Create log file header if it doesn't exist
        if (!(Test-Path $logFile)) {
            "Timestamp,Email,DisplayName,Availability,Activity" | Out-File -FilePath $logFile -Encoding UTF8
        }
        
        $logFiles[$email] = $logFile
    }
    
    return $logFiles
}

# Main monitoring function
function Start-Monitoring {
    param([string[]]$Emails)
    
    if ($Emails.Count -eq 0) {
        Write-Error "No user emails provided for monitoring"
        return
    }
    
    $logFiles = Initialize-UserLogFiles -Emails $Emails
    
    Write-Host "Starting Teams status monitoring for $($Emails.Count) users:" -ForegroundColor Cyan
    foreach ($email in $Emails) {
        Write-Host "  - $email" -ForegroundColor White
    }
    Write-Host "Log directory: $LogPath"
    Write-Host "Check interval: Every $CheckIntervalMinutes minutes"
    if ($ContinuousMode) {
        Write-Host "Mode: Continuous (24/7 monitoring)" -ForegroundColor Yellow
    } else {
        Write-Host "Monitoring hours: $StartTime - $EndTime"
    }
    Write-Host "Press Ctrl+C to stop monitoring`n"
    
    $checkCount = 0
    
    while ($true) {
        $currentTime = Get-Date
        $startHour = [DateTime]::Parse($StartTime).TimeOfDay
        $endHour = [DateTime]::Parse($EndTime).TimeOfDay
        
        # Check if we're within monitoring hours (or continuous mode)
        if ($ContinuousMode -or ($currentTime.TimeOfDay -ge $startHour -and $currentTime.TimeOfDay -le $endHour)) {
            $checkCount++
            Write-Host "$($currentTime.ToString('yyyy-MM-dd HH:mm:ss')) - Check #$checkCount" -ForegroundColor Yellow
            
            foreach ($email in $Emails) {
                try {
                    $status = Get-UserPresence -Email $email
                    if ($status) {
                        Write-StatusLog -Status $status -LogFile $logFiles[$email]
                        Write-Host "  $email : $($status.Availability) - $($status.Activity)" -ForegroundColor White
                    } else {
                        Write-Host "  $email : Failed to get status" -ForegroundColor Red
                    }
                }
                catch {
                    Write-Warning "Error monitoring $email : $($_.Exception.Message)"
                }
            }
            Write-Host ""
        }
        else {
            Write-Host "$($currentTime.ToString('HH:mm:ss')) - Outside monitoring hours, sleeping..." -ForegroundColor Gray
        }
        
        # Sleep for specified interval
        Start-Sleep -Seconds ($CheckIntervalMinutes * 60)
    }
}

# Cleanup function for end of day
function Complete-DayMonitoring {
    param([string[]]$Emails)
    
    Write-Host "`nGenerating end-of-day summaries..." -ForegroundColor Cyan
    
    $today = Get-Date -Format "yyyy-MM-dd"
    
    foreach ($email in $Emails) {
        $safeEmail = $email.Replace('@','_').Replace('.','_')
        $logFile = Join-Path $LogPath "teams_status_${safeEmail}_$today.csv"
        $summaryFile = Join-Path $LogPath "summary_${safeEmail}_$today.txt"
        
        if (Test-Path $logFile) {
            Generate-UserDailySummary -Email $email -LogFile $logFile -SummaryFile $summaryFile
        }
    }
    
    Write-Host "`nMonitoring completed for $today" -ForegroundColor Green
    Write-Host "Log files location: $LogPath"
}

# Main execution
try {
    # Check for running instances
    $mutex = Test-ScriptInstance
    
    # Determine user list
    $monitoringEmails = @()
    
    if ($UserListFile -and (Test-Path $UserListFile)) {
        $monitoringEmails = Get-UserEmailList -FilePath $UserListFile
    }
    
    if ($UserEmails.Count -gt 0) {
        $monitoringEmails += $UserEmails
    }
    
    # Remove duplicates
    $monitoringEmails = $monitoringEmails | Select-Object -Unique
    
    if ($monitoringEmails.Count -eq 0) {
        Write-Error "No user emails provided. Use -UserEmails parameter or -UserListFile parameter."
        Write-Host "`nExample usage:"
        Write-Host "  .\script.ps1 -UserEmails 'user1@company.com','user2@company.com'"
        Write-Host "  .\script.ps1 -UserListFile 'users.txt' -ContinuousMode"
        exit 1
    }
    
    # Connect to Microsoft Graph
    if (!(Connect-ToGraph)) {
        exit 1
    }
    
    # Handle Ctrl+C gracefully
    $null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
        Complete-DayMonitoring -Emails $monitoringEmails
        if ($mutex) { $mutex.ReleaseMutex() }
    }
    
    # Start monitoring
    Start-Monitoring -Emails $monitoringEmails
}
catch {
    Write-Error "An error occurred: $($_.Exception.Message)"
}
finally {
    Complete-DayMonitoring -Emails $monitoringEmails
    if ($mutex) { 
        $mutex.ReleaseMutex()
        $mutex.Dispose()
    }
    Disconnect-MgGraph -ErrorAction SilentlyContinue
}
