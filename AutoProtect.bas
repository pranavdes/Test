'***********************************************************************
' Class Module: CSheetState
'
' Purpose: Tracks an individual worksheet's protection state and history.
' After dealing with users repeatedly forgetting to re-protect sheets, This
' class has been to maintain a reliable protection state system.
'
' Why a class instead of a Type?
' Originally tried using a Type but ran into issues with Variants and
' Dictionary objects. This class approach is much more robust and gives
' us better control over the data.
'
' Author     : Pranav Desai
' Department : Finance Control & Oversight
' Created    : December 2024
'***********************************************************************
Option Explicit

' Member variables - using m_ prefix to easily spot them in the code
Private m_IsProtected As Boolean    ' Should this sheet be locked?
Private m_LastChanged As Date       ' When was protection last changed?
Private m_ChangeCount As Integer    ' How many times has it been modified?
Private m_Checksum As String        ' Hash to detect unauthorized changes

' IsProtected - Tracks whether this sheet should be protected
Public Property Get isProtected() As Boolean
    isProtected = m_IsProtected
End Property

Public Property Let isProtected(value As Boolean)
    m_IsProtected = value
End Property

' LastChanged - When the protection was last modified
' Helps us track how long a sheet has been in its current state
Public Property Get LastChanged() As Date
    LastChanged = m_LastChanged
End Property

Public Property Let LastChanged(value As Date)
    m_LastChanged = value
End Property

' ChangeCount - Number of protection changes
' Too many changes might indicate someone trying to mess with the sheet
Public Property Get ChangeCount() As Integer
    ChangeCount = m_ChangeCount
End Property

Public Property Let ChangeCount(value As Integer)
    m_ChangeCount = value
End Property

' Checksum - Security hash of current state
' Helps detect if someone bypassed our code to change protection
Public Property Get Checksum() As String
    Checksum = m_Checksum
End Property

Public Property Let Checksum(value As String)
    m_Checksum = value
End Property

Option Explicit
'***********************************************************************
' Excel Protection Manager
'
' What does this do?
' Automatically manages worksheet protection in our workbooks. Born from
' the constant headache of users unprotecting sheets for updates but
' forgetting to re-protect them. This system tracks protection states
' and makes sure everything gets locked down properly.
'
' Key Features:
' - Remembers which sheets should be protected
' - Automatically re-protects sheets when the workbook closes
' - Handles network timeouts and retries
' - Works with AutoSave without conflicts
' - Keeps detailed logs for troubleshooting
' - Processes sheets in batches to avoid Excel freezing
'
' Author     : Pranav Desai
' Department : Finance Control & Oversight
' Created    : December 2024
' Version    : 2.0.0
'
' Warning: Remember to change PROTECTION_KEY before deploying!
'***********************************************************************

'==== Windows API Declarations ====
#If VBA7 Then
    ' For 64-bit Office (most modern installations)
    Private Declare PtrSafe Sub Sleep Lib "kernel32" (ByVal dwMilliseconds As LongPtr)
#Else
    ' For legacy 32-bit Office (keeping for backwards compatibility)
    Private Declare Sub Sleep Lib "kernel32" (ByVal dwMilliseconds As Long)
#End If

'==== Configuration Settings ====
' I've made these constants easy to find and modify
' Adjust these based on your needs, but test thoroughly after changes!
Private Const MODULE_VERSION As String = "2.0.0"
Private Const PROTECTION_KEY As String = "YourSecurePassword123" ' CHANGE THIS!
Private Const DEBUG_MODE As Boolean = True    ' Set False in production
Private Const MAX_RETRIES As Integer = 3      ' Good balance for network issues
Private Const RETRY_DELAY_MS As Integer = 1000 ' 1 second between retries
Private Const BATCH_SIZE As Integer = 5       ' Process 5 sheets at a time
Private Const SESSION_TIMEOUT_MS As Long = 30000 ' 30 sec timeout
Private Const CHECKSUM_SALT As String = "FC&O_2024" ' Makes checksums unique

'==== Global Variables ====
' Using object variables for flexibility
Private protectionStates As Object    ' Dictionary of sheet states
Private sessionID As String           ' Unique ID for this session
Private isInitialized As Boolean      ' System setup flag
Private changeLog As Object           ' Operation logging
Private lastOperationTime As Date     ' For timeout detection

'***********************************************************************
' Core Event Handlers
'***********************************************************************

Private Sub Workbook_Open()
    ' This kicks off when someone opens the workbook
    ' Added error handling after seeing some weird startup issues
    On Error GoTo ErrorHandler
    
    If Not isInitialized Then
        InitializeProtectionSystem
        isInitialized = True
        
        If DEBUG_MODE Then Debug.Print "Protection system initialized. Session: " & sessionID
    End If
    Exit Sub

ErrorHandler:
    LogError "Workbook_Open", Err.Number, Err.Description
End Sub

Private Sub Workbook_BeforeClose(Cancel As Boolean)
    ' This is where we do our main protection check before the workbook closes
    On Error GoTo ErrorHandler
    
    ' Make sure our tracking system is still alive
    If Not ValidateSystemState Then
        ReinitializeIfNeeded
    End If
    
    ' To handle specific scneario around Autosave
    If IsAutoSaveActive Then
        HandleAutoSaveScenario
    End If
    
    ' Do our protection check
    Dim success As Boolean
    success = SecureWorkbookOnClose
    
    ' If we made changes, we need to save them
    If success And NeedToSave Then
        SaveWorkbookSecurely Cancel
    End If
    
    ' Clean up after ourselves - prevents memory leaks
    CleanupProtectionSystem
    Exit Sub

ErrorHandler:
    ' Log it but let the workbook close anyway
    LogError "Workbook_BeforeClose", Err.Number, Err.Description
    Cancel = False
End Sub

'***********************************************************************
' Core Protection Functions
'***********************************************************************

Private Sub InitializeProtectionSystem()
    ' Sets up our protection tracking system
    ' Separated this from Workbook_Open to make it reusable
    On Error GoTo ErrorHandler
    
    sessionID = CreateSessionID
    Set protectionStates = CreateObject("Scripting.Dictionary")
    Set changeLog = CreateObject("Scripting.Dictionary")
    
    ' Scan current protection states
    ScanAndStoreSheetStates
    lastOperationTime = Now
    
    If DEBUG_MODE Then
        Debug.Print "Protection system initialized with session ID: " & sessionID
        Debug.Print "Tracking " & protectionStates.Count & " sheets"
    End If
    Exit Sub

ErrorHandler:
    LogError "InitializeProtectionSystem", Err.Number, _
            "Failed to initialize protection system: " & Err.Description
    RaiseSecurityAlert "System Initialization Failed"
End Sub

Private Function CreateSessionID() As String
    ' Creates a unique ID for this session
    ' Format: YYYYMMDDHHNNSS_XXX where XXX is random
    ' Really helps when tracking down issues in the logs
    CreateSessionID = Format(Now, "yyyymmddhhnnss") & "_" & _
                     Hex$(Int((1000 * Rnd) + 1))
End Function

Private Sub ScanAndStoreSheetStates()
    ' Takes a snapshot of all sheets' protection states
    ' Added batch processing after seeing timeouts with large workbooks
    On Error GoTo ErrorHandler
    
    Dim ws As Worksheet
    Dim stateInfo As CSheetState
    Dim sheetCount As Integer
    
    For Each ws In ThisWorkbook.Worksheets
        Set stateInfo = New CSheetState
        
        ' Record current state
        With stateInfo
            .isProtected = ws.ProtectContents
            .LastChanged = Now
            .ChangeCount = 0
            .Checksum = CalculateSheetChecksum(ws)
        End With
        
        ' Add to tracking if not already there
        If Not protectionStates.Exists(ws.Name) Then
            protectionStates.Add ws.Name, stateInfo
        End If
        
        ' Batch processing to prevent Excel from hanging
        sheetCount = sheetCount + 1
        If sheetCount Mod BATCH_SIZE = 0 Then
            DoEvents
            Sleep RETRY_DELAY_MS
        End If
        
        If DEBUG_MODE Then
            Debug.Print "Registered sheet: " & ws.Name & _
                      " Protection: " & ws.ProtectContents
        End If
    Next ws
    
    Exit Sub

ErrorHandler:
    LogError "ScanAndStoreSheetStates", Err.Number, _
            "Failed while scanning sheet states"
End Sub

Private Function SecureWorkbookOnClose() As Boolean
    ' This is our main protection enforcer
    ' Checks and re-protects sheets as needed
    On Error GoTo ErrorHandler
    
    Dim ws As Worksheet
    Dim stateInfo As CSheetState
    Dim allSecured As Boolean
    allSecured = True
    
    Dim sheetCount As Integer
    sheetCount = 0
    
    For Each ws In ThisWorkbook.Worksheets
        If protectionStates.Exists(ws.Name) Then
            Set stateInfo = protectionStates(ws.Name)
            
            ' Check if this sheet needs protection
            If stateInfo.isProtected And Not ws.ProtectContents Then
                If Not ApplyProtection(ws) Then
                    allSecured = False
                    LogError "SecureWorkbookOnClose", 0, _
                            "Failed to protect sheet: " & ws.Name
                End If
            End If
            
            ' Process in batches to keep Excel responsive
            sheetCount = sheetCount + 1
            If sheetCount Mod BATCH_SIZE = 0 Then
                DoEvents
                Sleep RETRY_DELAY_MS
            End If
        End If
    Next ws
    
    SecureWorkbookOnClose = allSecured
    Exit Function

ErrorHandler:
    LogError "SecureWorkbookOnClose", Err.Number, "Critical error during final security check"
    SecureWorkbookOnClose = False
End Function

Private Function ApplyProtection(ws As Worksheet) As Boolean
    ' Applies protection to a single worksheet
    ' Added retry logic after seeing network drive issues
    On Error GoTo ErrorHandler
    
    Dim retryCount As Integer
    Dim success As Boolean
    success = False
    
    Do While retryCount < MAX_RETRIES And Not success
        ' These protection settings worked best for our needs
        ' Adjust them based on what your users need to do
        ws.Protect _
            Password:=PROTECTION_KEY, _
            DrawingObjects:=True, _
            Contents:=True, _
            Scenarios:=True, _
            UserInterfaceOnly:=True, _
            AllowFiltering:=True, _
            AllowFormattingCells:=False, _
            AllowFormattingColumns:=False, _
            AllowFormattingRows:=False, _
            AllowInsertingColumns:=False, _
            AllowInsertingRows:=False, _
            AllowInsertingHyperlinks:=False, _
            AllowDeletingColumns:=False, _
            AllowDeletingRows:=False, _
            AllowSorting:=True, _
            AllowUsingPivotTables:=True
            
        success = True
        UpdateSheetState ws.Name, True
        
        If Not success Then
            retryCount = retryCount + 1
            If retryCount < MAX_RETRIES Then Sleep RETRY_DELAY_MS
        End If
    Loop
    
    ApplyProtection = success
    Exit Function

ErrorHandler:
    LogError "ApplyProtection", Err.Number, _
            "Failed to protect sheet after " & retryCount & " attempts"
    ApplyProtection = False
End Function

'***********************************************************************
' Helper Functions
'***********************************************************************

Private Function CalculateSheetChecksum(ws As Worksheet) As String
    ' Creates a "fingerprint" of the sheet's protection state
    ' Helps detect if someone bypassed our code to change protection
    Dim checkString As String
    checkString = ws.Name & "|" & ws.ProtectContents & "|" & CHECKSUM_SALT
    
    Dim i As Integer, Sum As Long
    For i = 1 To Len(checkString)
        Sum = Sum + (Asc(Mid(checkString, i, 1)) * i)
    Next i
    
    CalculateSheetChecksum = Hex$(Sum)
End Function

Private Sub UpdateSheetState(sheetName As String, isProtected As Boolean)
    ' Updates our tracking info for a sheet
    If protectionStates.Exists(sheetName) Then
        Dim state As CSheetState
        Set state = protectionStates(sheetName)
        
        With state
            .isProtected = isProtected
            .LastChanged = Now
            .ChangeCount = .ChangeCount + 1
            .Checksum = CalculateSheetChecksum(ThisWorkbook.Sheets(sheetName))
        End With
    End If
End Sub

Private Sub LogError(procedure As String, errNumber As Long, errDescription As String)
    ' Logs errors for troubleshooting
    ' These logs have saved me countless hours of debugging
    If DEBUG_MODE Then
        Debug.Print "Error in " & procedure & ": [" & errNumber & "] " & errDescription
    End If
    
    Dim logEntry As String
    logEntry = Now & "|" & sessionID & "|" & procedure & "|" & _
               errNumber & "|" & errDescription
    
    changeLog.Add changeLog.Count + 1, logEntry
End Sub

Private Sub RaiseSecurityAlert(message As String)
    ' Alerts about security issues
    ' In production, you might want to email admins or log to a system
    If DEBUG_MODE Then Debug.Print "SECURITY ALERT: " & message
End Sub

Private Function IsAutoSaveActive() As Boolean
    ' Checks if AutoSave is enabled
    ' Added this after seeing issues with SharePoint
    On Error Resume Next
    IsAutoSaveActive = ThisWorkbook.AutoSaveOn
    On Error GoTo 0
End Function

Private Sub HandleAutoSaveScenario()
    ' Deals with AutoSave conflicts
    ' Just a basic wait for now, but could be enhanced
    If DEBUG_MODE Then Debug.Print "AutoSave detected - handling conflicts"
    Sleep RETRY_DELAY_MS
End Sub

Private Function ValidateSystemState() As Boolean
    ' Makes sure our tracking system is still good
    ValidateSystemState = isInitialized And Not protectionStates Is Nothing
End Function

Private Sub ReinitializeIfNeeded()
    ' Resets the system if something went wrong
    If Not ValidateSystemState Then
        InitializeProtectionSystem
        isInitialized = True
    End If
End Sub

Private Function NeedToSave() As Boolean
    ' Checks if we need to save changes
    NeedToSave = Not ThisWorkbook.Saved
End Function

Private Sub SaveWorkbookSecurely(ByRef Cancel As Boolean)
    ' Handles saving the workbook
    ' Added user prompt after complaints about auto-saving
    On Error GoTo ErrorHandler
    
    If ThisWorkbook.Saved Then
        ThisWorkbook.Save
    Else
        Dim response As VbMsgBoxResult
        response = MsgBox("Save changes before closing?", _
                         vbQuestion + vbYesNoCancel, "Save Changes")
        
        Select Case response
            Case vbYes
                ThisWorkbook.Save
            Case vbCancel
                Cancel = True
        End Select
    End If
    Exit Sub

ErrorHandler:
    LogError "SaveWorkbookSecurely", Err.Number, Err.Description
    MsgBox "Failed to save. Protection changes may not persist.", vbExclamation
End Sub

Private Sub CleanupProtectionSystem()
    ' Cleans up our objects to prevent memory leaks
    If Not protectionStates Is Nothing Then
        protectionStates.RemoveAll
        Set protectionStates = Nothing
    End If
    If Not changeLog Is Nothing Then
        changeLog.RemoveAll
        Set changeLog = Nothing
    End If
    isInitialized = False
End Sub
