# Teams Status Monitor Script
# Monitors a specific user's Teams presence status throughout the day
# Requires: Microsoft Graph PowerShell SDK installed (Install-Module Microsoft.Graph)

param(
    [Parameter(Mandatory=$true)]
    [string]$UserEmail,
    
    [Parameter(Mandatory=$false)]
    [int]$CheckIntervalMinutes = 15,
    
    [Parameter(Mandatory=$false)]
    [string]$LogPath = ".\TeamsMonitoring",
    
    [Parameter(Mandatory=$false)]
    [string]$StartTime = "09:00",
    
    [Parameter(Mandatory=$false)]
    [string]$EndTime = "17:00"
)

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
        $user = Get-MgUser -Filter "mail eq '$Email' or userPrincipalName eq '$Email'"
        if (!$user) {
            Write-Warning "User not found: $Email"
            return $null
        }
        
        # Get presence information
        $presence = Get-MgUserPresence -UserId $user.Id
        
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
        Add-Content -Path $LogFile -Value $logEntry
    }
}

# Function to generate daily summary
function Generate-DailySummary {
    param($LogFile, $SummaryFile)
    
    if (!(Test-Path $LogFile)) {
        Write-Warning "Log file not found: $LogFile"
        return
    }
    
    $logs = Import-Csv $LogFile -Header "Timestamp","Email","DisplayName","Availability","Activity"
    
    if ($logs.Count -eq 0) {
        return
    }
    
    # Calculate statistics
    $totalChecks = $logs.Count
    $availableCount = ($logs | Where-Object { $_.Availability -eq "Available" }).Count
    $awayCount = ($logs | Where-Object { $_.Availability -eq "Away" }).Count
    $offlineCount = ($logs | Where-Object { $_.Availability -eq "Offline" }).Count
    $busyCount = ($logs | Where-Object { $_.Availability -eq "Busy" }).Count
    
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
- Offline: $offlineCount checks ($([math]::Round(($offlineCount/$totalChecks)*100,1))%)

Detailed Timeline:
"@
    
    foreach ($log in $logs) {
        $time = [DateTime]::Parse($log.Timestamp).ToString('HH:mm')
        $summary += "`n$time - $($log.Availability) ($($log.Activity))"
    }
    
    $summary | Out-File -FilePath $SummaryFile -Encoding UTF8
    Write-Host "Daily summary generated: $SummaryFile" -ForegroundColor Green
}

# Main monitoring function
function Start-Monitoring {
    $today = Get-Date -Format "yyyy-MM-dd"
    $logFile = Join-Path $LogPath "teams_status_$($UserEmail.Replace('@','_').Replace('.','_'))_$today.csv"
    $summaryFile = Join-Path $LogPath "summary_$($UserEmail.Replace('@','_').Replace('.','_'))_$today.txt"
    
    Write-Host "Starting Teams status monitoring for: $UserEmail" -ForegroundColor Cyan
    Write-Host "Log file: $logFile"
    Write-Host "Check interval: Every $CheckIntervalMinutes minutes"
    Write-Host "Monitoring hours: $StartTime - $EndTime"
    Write-Host "Press Ctrl+C to stop monitoring`n"
    
    # Create log file header
    if (!(Test-Path $logFile)) {
        "Timestamp,Email,DisplayName,Availability,Activity" | Out-File -FilePath $logFile -Encoding UTF8
    }
    
    while ($true) {
        $currentTime = Get-Date
        $startHour = [DateTime]::Parse($StartTime).TimeOfDay
        $endHour = [DateTime]::Parse($EndTime).TimeOfDay
        
        # Check if we're within monitoring hours
        if ($currentTime.TimeOfDay -ge $startHour -and $currentTime.TimeOfDay -le $endHour) {
            Write-Host "$($currentTime.ToString('HH:mm:ss')) - Checking status..." -ForegroundColor Yellow
            
            $status = Get-UserPresence -Email $UserEmail
            if ($status) {
                Write-StatusLog -Status $status -LogFile $logFile
                Write-Host "Status: $($status.Availability) - $($status.Activity)" -ForegroundColor White
            }
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
    $today = Get-Date -Format "yyyy-MM-dd"
    $logFile = Join-Path $LogPath "teams_status_$($UserEmail.Replace('@','_').Replace('.','_'))_$today.csv"
    $summaryFile = Join-Path $LogPath "summary_$($UserEmail.Replace('@','_').Replace('.','_'))_$today.txt"
    
    Write-Host "`nGenerating end-of-day summary..." -ForegroundColor Cyan
    Generate-DailySummary -LogFile $logFile -SummaryFile $summaryFile
    
    Write-Host "Monitoring completed for $today" -ForegroundColor Green
    Write-Host "Files created:"
    Write-Host "- Raw log: $logFile"
    Write-Host "- Summary: $summaryFile"
}

# Main execution
try {
    # Connect to Microsoft Graph
    if (!(Connect-ToGraph)) {
        exit 1
    }
    
    # Handle Ctrl+C gracefully
    $null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
        Complete-DayMonitoring
    }
    
    # Start monitoring
    Start-Monitoring
}
catch {
    Write-Error "An error occurred: $($_.Exception.Message)"
}
finally {
    Complete-DayMonitoring
    Disconnect-MgGraph -ErrorAction SilentlyContinue
}
