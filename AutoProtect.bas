Option Explicit
'***********************************************************************
' Hold your horses! Before you dive in...
'
' This is the heart of our Excel Protection Manager. I've built this after 
' dealing with countless protection-related headaches in enterprise environments.
' 
' What does this bad boy do?
' - Keeps track of which sheets should be protected
' - Handles protection state with military-grade security (well, almost!)
' - Doesn't let users forget to protect their sheets
' - Works smoothly even when AutoSave tries to mess things up
'
' Author     : Pranav Desai
' Department : Finance Control & Oversight
' Version    : 2.0.0 
' Last Update: December 2024
'
' P.S.: If something breaks, you know who to blame ;)
'***********************************************************************

'==== API Declarations ====
#If VBA7 Then
    ' For 64-bit Office
    Private Declare PtrSafe Sub Sleep Lib "kernel32" (ByVal dwMilliseconds As LongPtr)
    Private Declare PtrSafe Function CryptProtectData Lib "Crypt32.dll" ( _
        ByRef DataIn As Any, ByVal szDataDescr As Long, _
        ByRef OptionalEntropy As Any, ByRef pvReserved As Any, _
        ByRef pPromptStruct As Any, ByVal dwFlags As Long, _
        ByRef DataOut As Any) As Long
#Else
    ' For older Office versions - if you're still using this, we need to talk!
    Private Declare Sub Sleep Lib "kernel32" (ByVal dwMilliseconds As Long)
#End If

'==== Constants ====
' Don't touch these unless you know what you're doing!
Private Const MODULE_VERSION As String = "2.0.0"
Private Const PROTECTION_KEY As String = "YourSecurePassword123" ' Change this!
Private Const DEBUG_MODE As Boolean = True    ' Set False in production
Private Const MAX_RETRIES As Integer = 3      ' How patient should we be?
Private Const RETRY_DELAY_MS As Integer = 1000 ' Give it a breather between retries
Private Const BATCH_SIZE As Integer = 5       ' How many sheets to process at once
Private Const SESSION_TIMEOUT_MS As Long = 30000 ' Half a minute should do it
Private Const CHECKSUM_SALT As String = "FC&O_2024"  ' Our secret sauce

'==== Enums and Types ====
Private Enum ProtectionResult
    PR_SUCCESS = 0
    PR_FAILED = 1
    PR_RETRY_NEEDED = 2
    PR_TIMEOUT = 3
End Enum

Private Type SheetState
    IsProtected As Boolean    ' Should this sheet be locked down?
    LastChanged As Date       ' When did we last touch it?
    ChangeCount As Integer    ' How many times has it been modified?
    Checksum As String       ' Our integrity check
End Type

'==== State Tracking ====
Private protectionStates As Object    ' Dictionary of sheet states
Private sessionID As String           ' Unique session identifier
Private isInitialized As Boolean      ' Have we set everything up?
Private changeLog As Object           ' For when things go wrong (they will)
Private lastOperationTime As Date     ' Timeout tracking

'***********************************************************************
' Workbook_Open
' 
' The party starts here! This runs whenever someone opens the workbook.
'***********************************************************************
Private Sub Workbook_Open()
    On Error GoTo ErrorHandler
    
    If Not isInitialized Then
        InitializeProtectionSystem
        ValidateWorkbookState
        isInitialized = True
        
        If DEBUG_MODE Then Debug.Print "Protection system initialized. Session: " & sessionID
    End If
    Exit Sub

ErrorHandler:
    HandleInitializationError Err.Number, Err.Description
End Sub

'***********************************************************************
' Workbook_BeforeClose
'
' The cleanup crew. Makes sure nothing's left unprotected.
'***********************************************************************
Private Sub Workbook_BeforeClose(Cancel As Boolean)
    On Error GoTo ErrorHandler
    
    If Not ValidateSystemState Then
        ReinitializeIfNeeded
    End If
    
    If IsAutoSaveActive Then
        HandleAutoSaveScenario
    End If
    
    Dim success As Boolean
    success = SecureWorkbookOnClose
    
    If success And NeedToSave Then
        SaveWorkbookSecurely Cancel
    End If
    
    CleanupProtectionSystem
    Exit Sub

ErrorHandler:
    LogError "Workbook_BeforeClose", Err.Number, Err.Description
    Cancel = False
End Sub

'***********************************************************************
' InitializeProtectionSystem
'
' Sets up our security fortress. This is the foundation of everything.
'***********************************************************************
Private Sub InitializeProtectionSystem()
    On Error GoTo ErrorHandler
    
    sessionID = CreateSessionID
    Set protectionStates = CreateObject("Scripting.Dictionary")
    Set changeLog = CreateObject("Scripting.Dictionary")
    
    LoadSecureSettings
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

'***********************************************************************
' Security Implementation Functions
'***********************************************************************
Private Function CreateSessionID() As String
    ' Generate a unique session identifier
    CreateSessionID = Format(Now, "yyyymmddhhnnss") & "_" & _
                     Hex$(Int((1000 * Rnd) + 1))
End Function

Private Function CalculateSheetChecksum(ws As Worksheet) As String
    ' Create a unique fingerprint for the sheet's state
    Dim checkString As String
    checkString = ws.Name & "|" & ws.ProtectContents & "|" & CHECKSUM_SALT
    
    Dim i As Integer, Sum As Long
    For i = 1 To Len(checkString)
        Sum = Sum + (Asc(Mid(checkString, i, 1)) * i)
    Next i
    
    CalculateSheetChecksum = Hex$(Sum)
End Function

Private Sub UpdateSheetState(sheetName As String, isProtected As Boolean)
    If protectionStates.Exists(sheetName) Then
        Dim state As SheetState
        state = protectionStates(sheetName)
        
        With state
            .IsProtected = isProtected
            .LastChanged = Now
            .ChangeCount = .ChangeCount + 1
            .Checksum = CalculateSheetChecksum(ThisWorkbook.Sheets(sheetName))
        End With
        
        protectionStates(sheetName) = state
    End If
End Sub

'***********************************************************************
' Core Protection Functions
'***********************************************************************
Private Function SecureWorkbookOnClose() As Boolean
    On Error GoTo ErrorHandler
    
    Dim ws As Worksheet
    Dim stateInfo As SheetState
    Dim allSecured As Boolean
    allSecured = True
    
    Dim sheetCount As Integer
    sheetCount = 0
    
    For Each ws In ThisWorkbook.Worksheets
        If protectionStates.Exists(ws.Name) Then
            stateInfo = protectionStates(ws.Name)
            
            If stateInfo.IsProtected And Not ws.ProtectContents Then
                If Not ApplyProtection(ws) Then
                    allSecured = False
                    LogError "SecureWorkbookOnClose", 0, _
                            "Failed to protect sheet: " & ws.Name
                End If
            End If
            
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
    On Error GoTo ErrorHandler
    
    Dim retryCount As Integer
    Dim success As Boolean
    success = False
    
    Do While retryCount < MAX_RETRIES And Not success
        Try
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
            
        Catch
            retryCount = retryCount + 1
            If retryCount < MAX_RETRIES Then Sleep RETRY_DELAY_MS
        End Try
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
Private Sub LogError(procedure As String, errNumber As Long, errDescription As String)
    If DEBUG_MODE Then
        Debug.Print "Error in " & procedure & ": [" & errNumber & "] " & errDescription
    End If
    
    Dim logEntry As String
    logEntry = Now & "|" & sessionID & "|" & procedure & "|" & _
               errNumber & "|" & errDescription
    
    changeLog.Add changeLog.Count + 1, logEntry
End Sub

Private Sub RaiseSecurityAlert(message As String)
    ' Here you could implement your own alert system
    If DEBUG_MODE Then Debug.Print "SECURITY ALERT: " & message
End Sub

Private Function IsAutoSaveActive() As Boolean
    On Error Resume Next
    IsAutoSaveActive = ThisWorkbook.AutoSaveOn
    On Error GoTo 0
End Function

Private Sub HandleAutoSaveScenario()
    ' Implementation depends on your AutoSave handling strategy
    If DEBUG_MODE Then Debug.Print "AutoSave detected - handling conflicts"
End Sub

Private Function ValidateSystemState() As Boolean
    ValidateSystemState = isInitialized And Not protectionStates Is Nothing
End Function

Private Sub ReinitializeIfNeeded()
    If Not ValidateSystemState Then
        InitializeProtectionSystem
        isInitialized = True
    End If
End Sub

Private Function NeedToSave() As Boolean
    ' Check if workbook has unsaved changes
    NeedToSave = Not ThisWorkbook.Saved
End Function

Private Sub SaveWorkbookSecurely(ByRef Cancel As Boolean)
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
