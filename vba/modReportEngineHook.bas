Attribute VB_Name = "modReportEngineHook"
Option Explicit
' MacroName: modReportEngineHook
' Executable: True
' Version: 1.3.1
' Author: JT
' Created: 2026-09-04
' LastModified: 2026-10-02
' Description: HTTP invocation hook for report generation -- POSTs the
'              active Testing Request workbook's shared-drive path to
'              the Slim-LIMS report-generation API and reacts to the
'              result. Falls back to Blank_Report_Creator
'              (modReportCreator.bas) only on a timeout/connection
'              failure, never on any server response.
' DependsOn: clsLoggingSystem, modReportCreator, modConfig
' ChangeLog:
'   1.3.1 - 2026-10-02  - Server URL and API key moved to modConfig (REPORT_SERVER_URL / REPORT_API_KEY),
'                          so this module imports unchanged and holds no secret.
'   1.3.0 - 2026-09-29  - Success (200) now logs "the big gates the code
'                          successfully clears": customer/type/sample
'                          count and per-phase timing (parse/build/write),
'                          plus test_mode and the engine/domain versions
'                          that processed this report -- all newly echoed
'                          into the response by Slim-LIMS 0.6.11+/cli.py
'                          0.21.16+. Previously the local log only ever
'                          showed the final path; digging into what
'                          actually happened meant server log access.
'                          Degrades gracefully (skips the 3 new gate
'                          lines) against an older server that doesn't
'                          send these fields yet.
'   1.2.2 - 2026-09-29  - Removed the "Report written to: <path>" MsgBox
'                          on a normal success -- the new report workbook
'                          opening automatically (and the old one closing)
'                          is already the confirmation; the box was pure
'                          extra-click friction on the common path, same
'                          reasoning as the earlier "a browser window has
'                          opened" removal. Only case that still needs a
'                          box on success: the report generated fine but
'                          couldn't be auto-opened (file association/
'                          sharing violation) -- previously silent, now
'                          tells the technician it worked and where to
'                          find it, since nothing else would.
'   1.2.1 - 2026-09-29  - ExtractJsonString now unescapes \n/\r/\t, not
'                          just \" and \\ -- a 500 response's "detail" is
'                          a full Python traceback, which arrived as one
'                          garbled line of literal backslash-n's in the
'                          MsgBox instead of readable multi-line text.
'   1.2.0 - 2026-09-24  - WaitForResolution/HandleUnresolvedEntry now also
'                          recognize the server's "abandoned":true signal
'                          -- the resolve page's own new heartbeat lets the
'                          server detect a closed/backgrounded/crashed
'                          browser tab well before the full 10-minute
'                          MAX_WAIT_SECONDS would otherwise be the only
'                          signal, and show a specific "that page was
'                          closed" message immediately instead.
'   1.1.0 - 2026-09-24  - WaitForResolution/HandleUnresolvedEntry now
'                          recognize the server's "expired":true signal
'                          (already sent by /resolution-status for an
'                          unknown/garbled token, previously ignored here)
'                          and show an immediate "link expired" message
'                          instead of silently falling through to the
'                          generic 10-minute timeout wording.
'   1.0.0 - 2026-09-22  - HTTP POST to Slim-LIMS's /generate-report,
'                          replacing the never-deployed exe/WScript.Shell
'                          plan; browser-based resolution flow for
'                          unrecognized customer/chemical/report-folder
'                          with a resolved/cancelled/timeout three-way
'                          outcome (WaitForResolution's wasCancelled
'                          param); sends HOOK_VERSION with every request
'
' PROCESS DESCRIPTION:
'   The lab-technician-facing trigger for report generation stays a
'   familiar Excel button. This module owns NO content/formatting/
'   business logic -- it POSTs the workbook's path and reacts to the
'   result. Uses the same clsLoggingSystem as the rest of the codebase
'   (a fresh timestamped log file per invocation, in the usual shared
'   log folder) so a hung/slow/failed server call is visible the same
'   way any other macro's log is, not silent.
'
'   STATUS -- read before deploying: this supersedes an earlier draft
'   that shelled out to a PyInstaller exe via WScript.Shell.Run. That
'   exe-based plan was never actually deployed to the real Shared Macro
'   Workbook.xlsm -- the real, current production system is (and
'   remains, as the fallback below) the original VBA-only macro
'   Blank_Report_Creator in modReportCreator.bas. This module must be
'   imported into THAT SAME workbook (the one modLIMSPing already lives
'   in) so Blank_Report_Creator and its own dependencies (modConfig,
'   clsStalenessChecker, etc., which key off ThisWorkbook) keep working
'   correctly when called as a fallback from here.
'
'   WHY NO FILE UPLOAD: the Slim-LIMS server and every lab machine reach
'   the same network share, so this sends the workbook's PATH, not its
'   bytes -- a small JSON POST, no multipart handling needed in VBA.
'
'   FALLBACK BEHAVIOR (deliberate decision, not a shortcut): a timeout or
'   connection failure (server down, service crashed, network hiccup)
'   falls back to calling Blank_Report_Creator directly -- the real
'   production macro -- rather than to any exe, since no exe is actually
'   deployed. A recognized data error (HTTP 422), a rejected API key
'   (HTTP 401), or an unexpected server error (HTTP 500) does NOT
'   trigger this fallback -- the server responded, so masking its answer
'   by silently retrying against a different, un-synced data source (the
'   legacy macro reads the Access DB, not Postgres) would be the wrong
'   call. Those cases are shown to the technician directly instead.
'
'   UNRESOLVED CUSTOMER/CHEMICAL/REPORT-FOLDER (error_type on a 422): the
'   legacy macro popped up a UserForm right there in Excel to resolve an
'   unrecognized customer/chemical. That logic is deliberately NOT
'   rebuilt in VBA -- it would put real business logic back where it
'   can't be tested without opening Excel. Instead, this module's only
'   job is to launch a browser page (server-rendered, same already-
'   tested CustomerService/ChemicalService/ReportFolderService the rest
'   of this system uses) and wait: opens resolve_url in the technician's
'   own default browser, short-polls GET /resolution-status/{token}
'   every ~1.5s (not one long connection -- more robust, each poll stays
'   fast), and once resolved, automatically retries /generate-report --
'   no second button click. See HandleUnresolvedEntry/WaitForResolution
'   below. "unresolved_report_folder" means the server doesn't yet know
'   (or the previously-known one no longer exists) which Reports
'   folder this customer's reports belong in -- a one-time-per-customer
'   question; every later report for that customer saves there
'   automatically.
'
'   OUTPUT LOCATION AND THE WORKBOOK SWAP (HTTP 200): the server decides
'   where the report gets saved -- the customer's mapped Reports
'   folder, with a filename it derives from the input's own filename
'   (see slim_report_engine.report_filename) -- there is no VBA-side
'   Save As dialog for the common case, unlike the legacy macro. Once
'   the new report workbook opens successfully, the original Testing
'   Request workbook is closed (unsaved changes discarded is safe here:
'   EnsureSaved already forced it to be saved, unchanged, before it was
'   ever sent to the server) -- its content already lives on as the
'   report's last tab. Net effect for the technician: one Generate
'   Report click, and the report is what's left open, same as the
'   legacy Save-As flow's end state, reached a different way.
'
'   This module lives inside an .xlsm, not a plain .bas file tracked in
'   isolation -- once imported into the real Shared Macro Workbook,
'   whoever opens it there may never see this repo's CHANGELOG.md at
'   all. The ChangeLog tag above is kept current by hand for that
'   reason (same convention as modReportCreator.bas and the rest of the
'   JT module family) -- it is the authoritative history for this
'   specific file, not just a summary of it.
' ================================================================

' Real LAN IPv4 address (LAB-SERVER, per the current hosting decision), NOT
' the hostname and NOT "localhost". Confirmed the hostname itself was the
' problem: LAB-SERVER resolves an IPv6 link-local address first (Windows'
' normal dual-stack preference), but this server only binds IPv4
' (0.0.0.0) -- WinHTTP's failed/stalled IPv6 attempt before falling back
' to IPv4 measured as ~6s of dead time per request, unrelated to the
' server or actual network latency. Using the literal IPv4 address skips
' that entirely. Tradeoff: this is DHCP-assigned, not a static reservation
' -- confirm it still matches before deploying, and again if it ever
' silently stops connecting (the router may have reassigned it).
' **** now found in modConfig.REPORT_SERVER_URL ***


' This module has no package-metadata version the way the Python side
' does (slim-report-engine/slim-domain versions are already logged
' server-side, in cli.py's run()) -- a plain constant, bumped by hand
' alongside the Version/ChangeLog tags in this file's own header, is
' the equivalent here. Logged on every request (see
' AttemptGenerateReport below) so a technician's own log file can be
' tied back to which version of THIS hook sent it -- relevant because
' different lab machines could plausibly be running different deployed
' copies if one hasn't been updated yet.
Private Const HOOK_VERSION As String = "1.3.1"

' Milliseconds: resolve, connect, send, receive. Short enough that a
' genuinely unreachable server falls back to the legacy macro quickly
' rather than leaving the technician staring at a frozen Excel window.
Private Const TIMEOUT_MS As Long = 15000


' Re-entrancy guard for GenerateReport (below). WaitForResolution's
' DoEvents call -- needed so Excel stays responsive during a
' browser-resolution wait of up to several minutes -- also lets Excel
' process a second click of the same button while the first click's
' call is still on the stack. Confirmed a real risk, not theoretical:
' an impatient technician double-clicking would spawn two concurrent,
' unsynchronized attempts against the same workbook/input file, which
' (among other things) could race the server's own destination-file
' overwrite check. Module-level so it survives across the nested calls
' this guards; reset in every exit path of GenerateReport, including
' via the error handler, so an unexpected error can't leave it stuck
' True for the rest of the Excel session.
Private mIsGenerating As Boolean

Public Sub GenerateReport()

    Dim targetWorkbook As Workbook
    Dim inputPath As String
    Dim Logger As New clsLoggingSystem

    If mIsGenerating Then
        MsgBox "A report is already being generated for this workbook -- please wait for it to finish.", _
               vbInformation, "Report Generation In Progress"
        Exit Sub
    End If
    mIsGenerating = True
    On Error GoTo CleanFail

    ' Same convention as Blank_Report_Creator: a fresh timestamped log
    ' file per invocation, DebugMode gated on ThisWorkbook's real name so
    ' a scratch/test copy of this workbook doesn't write to the shared
    ' log folder.
    Call Logger.Initialize("GenerateReport", modConfig.DebugMode)

    Set targetWorkbook = ActiveWorkbook
    If targetWorkbook Is Nothing Then
        Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogError, "No workbook is open.")
        MsgBox "No workbook is open.", vbExclamation, "Report Generation Failed"
        mIsGenerating = False
        Exit Sub
    End If

    If Not EnsureSaved(targetWorkbook) Then
        Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogInfo, "User cancelled the save prompt -- aborting.")
        mIsGenerating = False
        Exit Sub  ' user cancelled the save prompt
    End If
    inputPath = targetWorkbook.FullName

    Call AttemptGenerateReport(targetWorkbook, inputPath, Logger, 0)

    mIsGenerating = False
    Exit Sub

CleanFail:
    mIsGenerating = False
    Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogError, _
        "Unexpected error " & Err.Number & ": " & Err.Description)
    MsgBox "Unexpected error -- contact support with the details below:" & vbCrLf & vbCrLf & _
           Err.Description, vbCritical, "Report Generation Failed"

End Sub


' Does one /generate-report call and reacts to the result. Recurses (via
' HandleUnresolvedEntry) after a technician resolves a missing customer/
' chemical, up to MAX_RESOLUTION_ATTEMPTS times per click -- a single
' submission can have more than one thing missing (e.g. an unresolved
' customer AND an unresolved chemical), so one retry isn't always enough.
'
' targetWorkbook is threaded through (not re-derived from ActiveWorkbook)
' so the eventual close-on-success below always closes the SAME workbook
' the technician actually clicked Generate Report on, even after this
' recurses through a browser-based resolution and ActiveWorkbook may have
' changed in the meantime.
Private Sub AttemptGenerateReport(ByVal targetWorkbook As Workbook, ByVal inputPath As String, ByRef Logger As clsLoggingSystem, ByVal resolutionAttempt As Long)

    Const MAX_RESOLUTION_ATTEMPTS As Long = 5

    Dim statusCode As Long
    Dim responseBody As String
    Dim requestSucceeded As Boolean
    Dim startTime As Single
    Dim elapsedSeconds As String

    Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogInfo, "Requesting report for " & inputPath & " from " & modConfig.REPORT_SERVER_URL & " (hook v" & HOOK_VERSION & ")")

    startTime = Timer
    requestSucceeded = CallReportServer(inputPath, statusCode, responseBody, Logger)
    elapsedSeconds = Format(Timer - startTime, "0.00")

    If requestSucceeded Then
        ' The server reports how long run() itself took, separate from
        ' this round-trip measurement -- the gap between the two is
        ' network/WinHTTP overhead, not guessed at.
        Dim serverSeconds As String
        Dim overheadSeconds As String
        serverSeconds = ExtractJsonNumber(responseBody, "duration_seconds")
        If Len(serverSeconds) > 0 Then
            overheadSeconds = Format(CDbl(elapsedSeconds) - CDbl(serverSeconds), "0.00")
            Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogDebug, _
                "Round trip " & elapsedSeconds & "s = server " & serverSeconds & "s + network/VBA overhead " & overheadSeconds & "s")
        Else
            Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogDebug, "Server round trip took " & elapsedSeconds & "s (no duration_seconds in response)")
        End If
    End If

    If Not requestSucceeded Then
        ' Server unreachable (timeout, connection refused, DNS failure,
        ' etc.) -- fall back to the real production macro rather than
        ' failing the technician's button click outright. The specific
        ' WinHTTP error was already logged inside CallReportServer.
        Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogWarning, _
            "Server unreachable after " & elapsedSeconds & "s (timeout " & TIMEOUT_MS & "ms) -- falling back to Blank_Report_Creator.")
        Call Blank_Report_Creator
        Exit Sub
    End If

    Select Case statusCode
        Case 200
            Dim outputPath As String
            Dim reportWorkbook As Workbook
            outputPath = ExtractJsonString(responseBody, "path")

            ' "The big gates the code successfully clears" (2026-09-29,
            ' direct user request): run()'s own customer/type/sample-count,
            ' sheet-count, and per-phase timings -- previously visible only
            ' in the SERVER's own log file -- are now echoed into this
            ' response (Slim-LIMS 0.6.11+, cli.py 0.21.16+) so the
            ' technician's own local log shows real INFO-level proof of
            ' what happened, without needing server access for anything
            ' beyond genuine DEBUG-level digging. Checked via a direct
            ' InStr presence test, NOT by seeing if ExtractJsonString
            ' returned something non-blank -- that function's own
            ' documented fallback for a truly missing key is to return the
            ' WHOLE raw response body, which is never blank, so that check
            ' would always pass even against an older server that doesn't
            ' send these fields at all.
            If InStr(responseBody, """customer_name""") > 0 Then
                Dim sampleCount As String, sheetCount As String
                Dim parseSeconds As String, buildSeconds As String, writeSeconds As String
                sampleCount = ExtractJsonNumber(responseBody, "sample_count")
                sheetCount = ExtractJsonNumber(responseBody, "sheet_count")
                parseSeconds = ExtractJsonNumber(responseBody, "parse_seconds")
                buildSeconds = ExtractJsonNumber(responseBody, "build_seconds")
                writeSeconds = ExtractJsonNumber(responseBody, "write_seconds")

                Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogInfo, _
                    "Parsed input: customer=" & ExtractJsonString(responseBody, "customer_name") & _
                    ", type=" & ExtractJsonString(responseBody, "request_type") & _
                    ", " & sampleCount & " sample(s) (" & parseSeconds & "s)")
                Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogInfo, _
                    "Report content built for " & sampleCount & " sample(s) (" & buildSeconds & "s)")
                Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogInfo, _
                    sheetCount & " sheet(s) written and saved (" & writeSeconds & "s)")
            End If

            ' test_mode already existed in this response (added for the
            ' resolve-page banner) but was never read here -- given how
            ' central test-mode is to this whole project's rollout safety
            ' story, it belongs in the technician's own log too, not just
            ' discoverable by checking .env.
            Dim testModeText As String
            If InStr(responseBody, """test_mode"":true") > 0 Then
                testModeText = "True"
            ElseIf InStr(responseBody, """test_mode"":false") > 0 Then
                testModeText = "False"
            Else
                testModeText = "unknown"
            End If
            Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogInfo, _
                "Report generated: " & outputPath & " (test_mode=" & testModeText & _
                ", engine v" & ExtractJsonString(responseBody, "engine_version") & _
                ", domain v" & ExtractJsonString(responseBody, "domain_version") & ")")

            Set reportWorkbook = OpenOutputFile(outputPath)
            If Not reportWorkbook Is Nothing Then
                ' Swap: the technician's original Testing Request workbook
                ' is now redundant -- its content lives on as the report's
                ' last tab (see slim_report_engine.cli.run(), which appends
                ' the form sheet itself) -- so close it and leave only the
                ' report open. Matches the legacy macro's outcome (one
                ' workbook, renamed via Save-As) even though this gets
                ' there differently (two separate files, one closed).
                ' EnsureSaved forced a save before the FIRST attempt, but
                ' on a resolution-wait retry (HandleUnresolvedEntry ->
                ' WaitForResolution) that can be up to 10 minutes earlier.
                ' WaitForResolution's poll loop calls DoEvents, which keeps
                ' Excel genuinely responsive during that wait -- confirmed
                ' real, not theoretical: a technician can click back into
                ' this same still-open workbook and type a note while
                ' waiting on the browser tab. Discarding unconditionally
                ' would silently lose that edit. The report itself was
                ' already generated from whatever was on disk at send
                ' time, so saving now only affects this workbook's own
                ' archived copy -- safe either way.
                If Not targetWorkbook.Saved Then
                    Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogInfo, "Saving edits made to the Testing Request workbook during the resolution wait before closing it.")
                    On Error Resume Next
                    targetWorkbook.Save
                    On Error GoTo 0
                End If
                Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogInfo, "Closing the original Testing Request workbook now that the report is open.")
                On Error Resume Next
                targetWorkbook.Close SaveChanges:=False
                On Error GoTo 0
            Else
                ' Confirmed real gap (2026-09-29), previously silent: the
                ' report WAS generated successfully (the server already
                ' wrote it to disk) but the auto-open step itself failed
                ' (file association issue, sharing violation, etc.) -- with
                ' no success MsgBox anymore (removed above, same reasoning
                ' as the "browser window has opened" removal) and no new
                ' window appearing, the technician would otherwise see
                ' NOTHING happen and have no way to tell success from
                ' failure. This is the one success-path case that still
                ' needs a box: it worked, here's where to find it.
                Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogWarning, "Could not open the generated report automatically -- leaving the Testing Request workbook open.")
                MsgBox "Report generated successfully, but it could not be opened automatically." & vbCrLf & vbCrLf & _
                       "You can find it here:" & vbCrLf & outputPath, vbExclamation, "Report Generated -- Open Manually"
            End If

        Case 422
            Dim errorType As String
            errorType = ExtractJsonString(responseBody, "error_type")

            If (errorType = "unresolved_customer" Or errorType = "unresolved_chemical" Or errorType = "unresolved_report_folder") _
                    And resolutionAttempt < MAX_RESOLUTION_ATTEMPTS Then
                Call HandleUnresolvedEntry(targetWorkbook, inputPath, responseBody, Logger, resolutionAttempt)
            Else
                Dim dataErrorMessage As String
                dataErrorMessage = ExtractJsonString(responseBody, "detail")
                Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogWarning, "Recognized data problem (422): " & dataErrorMessage)
                MsgBox dataErrorMessage, vbExclamation, "Report Generation Failed"
            End If

        Case 401
            ' A live server rejected the API key -- a configuration
            ' mismatch (this module's modConfig.REPORT_API_KEY vs. Slim-LIMS's .env), not
            ' a data or connectivity problem. Does NOT fall back to
            ' Blank_Report_Creator: the server IS reachable, retrying
            ' against a different data source wouldn't fix a bad key.
            Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogError, "Authentication rejected (401) -- modConfig.REPORT_API_KEY mismatch with the server.")
            MsgBox "The report server rejected this request's API key." & vbCrLf & _
                   "Contact IT/support -- this is a configuration issue, not a data problem.", _
                   vbCritical, "Report Generation Failed"
        Case Else
            Dim serverErrorMessage As String
            serverErrorMessage = ExtractJsonString(responseBody, "detail")
            Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogError, "Unexpected status " & statusCode & ": " & serverErrorMessage)
            MsgBox "Unexpected error -- contact support with the details below:" & vbCrLf & vbCrLf & _
                   serverErrorMessage, vbCritical, "Report Generation Failed"
    End Select

End Sub


' A customer/chemical wasn't found, or the customer's report-folder
' mapping is missing/stale. Opens the resolution page in the TECHNICIAN's
' own default browser (their machine, their screen -- this runs
' client-side, not on the server), waits for them to submit it, then
' automatically retries /generate-report -- no second button click.
' Deliberately does NOT fall back to Blank_Report_Creator: the server IS
' reachable and responded, this is a data-entry workflow, not a
' connectivity failure.
'
' No "a browser window has opened" MsgBox here on purpose (removed after
' real testing showed the browser reliably pops up in front of Excel,
' immediately covering it anyway) -- one fewer click of friction on every
' resolution. Only real downside: if the browser somehow opens off-screen
' (a different monitor, minimized, a failed URL handler) with nothing
' explaining why Excel looks stuck, that's what the log file is for.
Private Sub HandleUnresolvedEntry( _
    ByVal targetWorkbook As Workbook, _
    ByVal inputPath As String, _
    ByVal responseBody As String, _
    ByRef Logger As clsLoggingSystem, _
    ByVal resolutionAttempt As Long _
)

    Dim resolveUrl As String
    Dim token As String
    Dim errorType As String

    resolveUrl = ExtractJsonString(responseBody, "resolve_url")
    token = ExtractJsonString(responseBody, "token")
    errorType = ExtractJsonString(responseBody, "error_type")

    Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogWarning, _
        errorType & " -- opening " & resolveUrl & " for the technician to resolve.")

    ' Hands off to whatever's registered for http:// (the default
    ' browser) -- same WScript.Shell mechanism already used elsewhere in
    ' this codebase, just against a URL instead of a local file.
    On Error Resume Next
    CreateObject("WScript.Shell").Run resolveUrl
    On Error GoTo 0

    Dim wasCancelled As Boolean
    Dim wasExpired As Boolean
    Dim wasAbandoned As Boolean
    If WaitForResolution(token, Logger, wasCancelled, wasExpired, wasAbandoned) Then
        Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogInfo, "Resolved -- retrying report generation.")
        Call AttemptGenerateReport(targetWorkbook, inputPath, Logger, resolutionAttempt + 1)
    ElseIf wasCancelled Then
        ' Explicit "cannot resolve" path (2026-09-22) -- the technician
        ' recognized a problem with the Testing Request form itself (e.g.
        ' an ambiguous customer/chemical entry) and said so directly,
        ' rather than either guessing at a resolution or leaving this to
        ' time out after 10 minutes for the same eventual outcome. Does
        ' NOT retry -- the form needs a human correction first.
        Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogWarning, "Resolution was cancelled by the technician -- form needs correction.")
        MsgBox "Report generation was cancelled. Correct the Testing Request form and click Generate Report again when it's ready.", _
               vbInformation, "Report Generation Cancelled"
    ElseIf wasExpired Then
        ' Confirmed real gap (2026-09-24 code review): the server already
        ' distinguishes "this link/token is unknown or expired" from a
        ' plain still-waiting timeout ("expired":true, /resolution-status)
        ' -- e.g. a truncated/garbled response earlier turned resolveUrl or
        ' token into garbage, or the resolution page just genuinely aged
        ' out. Previously this fell through to the generic "wasn't
        ' completed in time" wording after the full 10-minute wait, which
        ' is both wrong (nothing was actually still pending) and slow to
        ' tell the technician. Show this immediately instead.
        Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogWarning, "Resolution link was invalid or expired.")
        MsgBox "That resolution link is no longer valid. Click Generate Report again to get a fresh one.", _
               vbExclamation, "Resolution Link Expired"
    ElseIf wasAbandoned Then
        ' 2026-09-24: the resolve page now sends a short heartbeat while
        ' it's open (see Slim-LIMS's _heartbeat_script) so the server can
        ' tell "still open" from "closed/backgrounded/crashed" well before
        ' this function's own 10-minute MAX_WAIT_SECONDS would otherwise
        ' be the only signal -- closing the browser, walking away with it
        ' backgrounded, a crash, and a dropped connection all look the
        ' same here: the pings just stopped. Same non-retrying treatment
        ' as cancelled/expired -- nothing was actually resolved, so
        ' there's nothing to retry yet.
        Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogWarning, "Resolution page appears to have closed or lost connection.")
        MsgBox "It looks like that page was closed (or lost its connection). Click Generate Report again to try once more.", _
               vbExclamation, "Resolution Page Closed"
    Else
        Call Logger.LogMessage("GenerateReport", LogLevelEnum.LogWarning, "Resolution timed out or was not completed.")
        MsgBox "The resolution wasn't completed in time. Click Generate Report again once it's done.", _
               vbExclamation, "Report Generation Not Completed"
    End If

End Sub


' Short-polls GET /resolution-status/{token} every ~1.5s -- deliberately
' NOT one long-held connection (more robust, and each individual call
' stays fast/cheap) -- until resolved, cancelled, or MAX_WAIT_SECONDS
' elapses. DoEvents between polls keeps Excel from looking fully hung,
' though a synchronous WinHTTP call still means it can't do real work
' meanwhile.
'
' wasCancelled (ByRef): set True only when the technician used the
' explicit "cannot resolve" button server-side -- distinct from a plain
' timeout, so the caller can show a clear "this needs correction, not
' just try again later" message instead of the generic timeout wording.
'
' wasExpired (ByRef, 2026-09-24): set True when the server reports the
' token itself as unknown/expired ("expired":true -- /resolution-status
' returns this for a token it doesn't recognize at all, distinct from one
' it recognizes but that's still pending). Confirmed real gap: this was
' already being sent by the server and silently ignored here, so a
' garbled token (e.g. from ExtractJsonString's raw-body fallback on a
' malformed response) meant a full 10-minute wait for the generic timeout
' message instead of an immediate, accurate one.
'
' wasAbandoned (ByRef, 2026-09-24): set True when the server reports
' "abandoned":true -- the resolve page's own short heartbeat (sent every
' ~15s while the page is open) has gone quiet for longer than the
' server's own abandonment threshold. Closing the tab, backgrounding it
' for a while, a crash, and a dropped connection all look identical here:
' the pings just stopped. Direct answer to a real question ("closed the
' browser -- is 10 minutes really the only way to find out?"): now it
' isn't -- this can fire well before MAX_WAIT_SECONDS below would
' otherwise be the only signal.
Private Function WaitForResolution(ByVal token As String, ByRef Logger As clsLoggingSystem, ByRef wasCancelled As Boolean, ByRef wasExpired As Boolean, ByRef wasAbandoned As Boolean) As Boolean

    Const MAX_WAIT_SECONDS As Long = 600        ' 10 minutes -- someone has to fill in a form
    Const POLL_INTERVAL_SECONDS As Single = 1.5

    Dim statusUrl As String
    Dim startTime As Single
    Dim lastPollTime As Single
    Dim http As Object
    Dim responseBody As String

    wasCancelled = False
    wasExpired = False
    wasAbandoned = False
    statusUrl = ServerBase() & "resolution-status/" & token
    startTime = Timer
    lastPollTime = -POLL_INTERVAL_SECONDS  ' poll immediately on the first loop iteration

    Do While Timer - startTime < MAX_WAIT_SECONDS
        DoEvents

        If Timer - lastPollTime >= POLL_INTERVAL_SECONDS Then
            lastPollTime = Timer

            On Error Resume Next
            Set http = Nothing
            Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
            If Not http Is Nothing Then
                http.SetTimeouts 5000, 5000, 5000, 5000
                http.SetProxy 1
                http.Open "GET", statusUrl, False
                http.Send
                If http.Status = 200 Then
                    responseBody = http.ResponseText
                    If InStr(responseBody, """expired"":true") > 0 Then
                        On Error GoTo 0
                        wasExpired = True
                        WaitForResolution = False
                        Exit Function
                    End If
                    If InStr(responseBody, """cancelled"":true") > 0 Then
                        On Error GoTo 0
                        wasCancelled = True
                        WaitForResolution = False
                        Exit Function
                    End If
                    If InStr(responseBody, """abandoned"":true") > 0 Then
                        On Error GoTo 0
                        wasAbandoned = True
                        WaitForResolution = False
                        Exit Function
                    End If
                    If InStr(responseBody, """resolved"":true") > 0 Then
                        On Error GoTo 0
                        WaitForResolution = True
                        Exit Function
                    End If
                End If
            End If
            On Error GoTo 0
        End If
    Loop

    WaitForResolution = False

End Function


' Derived from modConfig.REPORT_SERVER_URL (strips the "generate-report" endpoint name) so
' the status-poll URL always matches whatever host/port modConfig.REPORT_SERVER_URL points
' at -- one constant to keep in sync, not two.
Private Function ServerBase() As String
    ServerBase = Left$(modConfig.REPORT_SERVER_URL, Len(modConfig.REPORT_SERVER_URL) - Len("generate-report"))
End Function


' Prompts to save if the workbook has unsaved changes -- the server
' reads the workbook from DISK (by shared path), so an in-memory-only
' edit would otherwise silently generate a report from stale data with
' no warning.  Returns False if the user cancels.
Private Function EnsureSaved(ByVal wb As Workbook) As Boolean

    If Not wb.Saved Then
        Dim response As VbMsgBoxResult
        response = MsgBox("This workbook has unsaved changes. Save before generating the report?", _
                           vbYesNoCancel Or vbQuestion, "Save Required")
        Select Case response
            Case vbYes
                wb.Save
            Case vbNo
                ' Proceed anyway -- generating from an intentionally
                ' unsaved state (e.g. while testing) is the
                ' technician's call, not this macro's to block.
            Case vbCancel
                EnsureSaved = False
                Exit Function
        End Select
    End If

    EnsureSaved = True

End Function


' POSTs {"input_path": inputPath, "hook_version": HOOK_VERSION} to the
' Slim-LIMS report-generation API -- hook_version lets the server's own
' logs show which deployed copy of this hook made a given request, not
' just this hook's own local log file.
' Returns True if a response was actually received (regardless of ITS
' status code -- that's read back via the ByRef parameters). Returns
' False only on a connection-level failure (timeout, refused, DNS) --
' the caller treats that as "fall back to the legacy macro." Logs the
' specific WinHTTP error (Err.Number/Description) on that path so a
' timeout is distinguishable from a refused connection or DNS failure
' in the log file, not just "unreachable."
Private Function CallReportServer( _
    ByVal inputPath As String, _
    ByRef statusCode As Long, _
    ByRef responseBody As String, _
    ByRef Logger As clsLoggingSystem _
) As Boolean

    Dim http As Object
    Dim requestBody As String

    On Error GoTo ConnectionFailed

    ' Late-bound (no Tools > References entry needed) -- same pattern
    ' already proven live in modLIMSPing.
    Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
    http.SetTimeouts TIMEOUT_MS, TIMEOUT_MS, TIMEOUT_MS, TIMEOUT_MS

    ' Skip proxy auto-detection (WPAD) entirely -- WinHTTP's default
    ' otherwise tries to auto-detect a proxy on EVERY request, which can
    ' add real, multi-second latency if "Automatically detect settings"
    ' is on and there's no WPAD server to answer quickly (a very common
    ' Windows default, unrelated to this server or the network path).
    ' There's never a reason to go through a proxy for a same-LAN call
    ' to a known host, so go direct. 1 = HTTPREQUEST_PROXYSETTING_DIRECT.
    http.SetProxy 1

    requestBody = "{""input_path"": """ & EscapeJsonString(inputPath) & """, ""hook_version"": """ & EscapeJsonString(HOOK_VERSION) & """}"

    http.Open "POST", modConfig.REPORT_SERVER_URL, False
    http.SetRequestHeader "Content-Type", "application/json"
    http.SetRequestHeader "X-API-Key", modConfig.REPORT_API_KEY
    http.Send requestBody

    statusCode = http.Status
    responseBody = http.ResponseText
    CallReportServer = True
    Exit Function

ConnectionFailed:
    Call Logger.LogMessage("CallReportServer", LogLevelEnum.LogWarning, _
        "WinHTTP error " & Err.Number & ": " & Err.Description & " (URL: " & modConfig.REPORT_SERVER_URL & ")")
    CallReportServer = False

End Function


' Escapes backslashes and double quotes so a Windows path (which is full
' of backslashes) embeds safely in a hand-built JSON string. Not a
' general JSON escaper -- sufficient for file-system paths, which don't
' contain control characters.
Private Function EscapeJsonString(ByVal s As String) As String
    Dim result As String
    result = Replace(s, "\", "\\")
    result = Replace(result, """", "\""")
    EscapeJsonString = result
End Function


' Minimal hand-rolled extraction of a string value for "key": "value"
' from a small, known JSON response -- same approach already used by
' modLIMSPing's ExtractJsonString. Not a general JSON parser.
Private Function ExtractJsonString(ByVal json As String, ByVal key As String) As String

    Dim searchKey As String
    Dim startPos As Long
    Dim valueStart As Long
    Dim valueEnd As Long

    searchKey = """" & key & """"
    startPos = InStr(1, json, searchKey)
    If startPos = 0 Then
        ExtractJsonString = json  ' fall back to showing the raw body
        Exit Function
    End If

    valueStart = InStr(startPos, json, ":")
    valueStart = InStr(valueStart, json, """") + 1
    valueEnd = valueStart
    ' Advance past escaped quotes (\") so an embedded path or message
    ' containing an escaped character doesn't end the value early.
    Do While valueEnd <= Len(json)
        If Mid(json, valueEnd, 1) = "\" Then
            valueEnd = valueEnd + 2
        ElseIf Mid(json, valueEnd, 1) = """" Then
            Exit Do
        Else
            valueEnd = valueEnd + 1
        End If
    Loop

    Dim rawValue As String
    rawValue = Mid(json, valueStart, valueEnd - valueStart)
    ' Confirmed real gap (2026-09-29 failure-path audit): a 500 response's
    ' "detail" is a full Python traceback (json.dumps-encoded, so its real
    ' newlines arrive here as the literal 2-character sequence \n, not an
    ' actual line break) -- this only unescaped \" and \\, so a technician
    ' hitting Case Else in AttemptGenerateReport saw the whole traceback
    ' mashed onto one line with literal backslash-n's in the MsgBox,
    ' rather than readable multi-line text. \n -> a real line break, \r
    ' dropped (vbCrLf already supplies it), \t -> spaces (VBA MsgBox
    ' doesn't render tabs meaningfully).
    rawValue = Replace(rawValue, "\""", """")
    rawValue = Replace(rawValue, "\n", vbCrLf)
    rawValue = Replace(rawValue, "\r", "")
    rawValue = Replace(rawValue, "\t", "    ")
    rawValue = Replace(rawValue, "\\", "\")
    ExtractJsonString = rawValue

End Function


' Minimal hand-rolled extraction of a numeric value (integer or decimal)
' for "key": 1.23 from a small, known JSON response. Returns "" if the
' key isn't found, so callers can tell "missing" from "zero."
Private Function ExtractJsonNumber(ByVal json As String, ByVal key As String) As String

    Dim searchKey As String
    Dim startPos As Long
    Dim valueStart As Long
    Dim valueEnd As Long
    Dim ch As String

    searchKey = """" & key & """"
    startPos = InStr(1, json, searchKey)
    If startPos = 0 Then
        ExtractJsonNumber = ""
        Exit Function
    End If

    valueStart = InStr(startPos, json, ":") + 1
    Do While Mid(json, valueStart, 1) = " "
        valueStart = valueStart + 1
    Loop

    valueEnd = valueStart
    Do While valueEnd <= Len(json)
        ch = Mid(json, valueEnd, 1)
        If (ch < "0" Or ch > "9") And ch <> "." And ch <> "-" Then Exit Do
        valueEnd = valueEnd + 1
    Loop

    ExtractJsonNumber = Mid(json, valueStart, valueEnd - valueStart)

End Function


' Best-effort: open the generated report for immediate review, returning
' the opened Workbook (or Nothing on failure, e.g. a file-association or
' sharing-violation issue) so the caller can decide whether it's safe to
' close the original Testing Request workbook -- never blocks on this
' succeeding; AttemptGenerateReport's own Else branch (2026-09-29) shows
' the technician the path directly when this returns Nothing, since
' there's no success MsgBox anymore to have already told them.
Private Function OpenOutputFile(ByVal outputPath As String) As Workbook
    On Error Resume Next
    Set OpenOutputFile = Workbooks.Open(outputPath)
    On Error GoTo 0
End Function
