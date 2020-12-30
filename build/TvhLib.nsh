Var Dialog
Var lblLabel
Var lblUsername
Var lblPassword
Var txtUsername
Var pwdPassword
Var pwdConfirmPassword
Var hwnd
Var user
Var pwd
Var pwd2
Var subfolder
Var cmd
Var pythoninstall
Var pythonpath

!include "CharToASCII.nsh"
!include "Base64.nsh"





Function ConfigPage
    nsDialogs::Create /NOUNLOAD 1018
    Pop $Dialog

    ${If} $Dialog == error
        Abort
    ${EndIf}

    ${NSD_CreateLabel} 0 0 100% 24u "Please specify Locast Username and Password."
    Pop $lblLabel

    ${NSD_CreateLabel} 0 30u 60u 12u "Username:"
    Pop $lblUsername

    ${NSD_CreateText} 65u 30u 50% 12u ""
    Pop $txtUsername

    ${NSD_CreateLabel} 0 45u 60u 12u "Password:"
    Pop $lblPassword

    ${NSD_CreatePassword} 65u 45u 50% 12u ""
    Pop $pwdPassword


    ${NSD_CreateLabel} 0 60u 60u 12u "Confirm Password:"
    Pop $lblPassword

    ${NSD_CreatePassword} 65u 60u 50% 12u ""
    Pop $pwdConfirmPassword

    ${NSD_CreateCheckbox} 65u 75u 50% 12u "Show password"
    Pop $hwnd
    ${NSD_OnClick} $hwnd ShowPassword

    nsDialogs::Show
FunctionEnd

Function ConfigPageLeave
    ${NSD_GetText} $txtUsername $user
    ${NSD_GetText} $pwdPassword $pwd
    ${NSD_GetText} $pwdConfirmPassword $pwd2
    ${If} $user == ""
    ${OrIf} $pwd == ""
    ${OrIf} $pwd2 == ""
        MessageBox MB_OK "All entries are required"
        Abort
    ${EndIf}

    ${If} $pwd != $pwd2
        MessageBox MB_OK "passwords do not match, try again"
        Abort
    ${EndIf}
    ${Base64_Encode} $pwd
    Pop $0
    StrCpy $pwd $0
FunctionEnd

Function ShowPassword
    Pop $hwnd
    ${NSD_GetState} $hwnd $0
    ShowWindow $pwdPassword ${SW_HIDE}
    ShowWindow $pwdConfirmPassword ${SW_HIDE}
    ${If} $0 == 1
        SendMessage $pwdPassword ${EM_SETPASSWORDCHAR} 0 0
        SendMessage $pwdConfirmPassword ${EM_SETPASSWORDCHAR} 0 0
    ${Else}
        SendMessage $pwdPassword ${EM_SETPASSWORDCHAR} 42 0
        SendMessage $pwdConfirmPassword ${EM_SETPASSWORDCHAR} 42 0
    ${EndIf}
    ShowWindow $pwdPassword ${SW_SHOW}
    ShowWindow $pwdConfirmPassword ${SW_SHOW}
FunctionEnd

Function TestPython
    nsExec::ExecToStack '"where" python.exe'
    Pop $0 ;return value
    Pop $1 ;return value
    IntCmp $0 0 PythonFound
        MessageBox MB_OK "Python 3.x not found, Make sure to install python$\r$\n\
            for all users if a Windows Service is needed or single user$\r$\n\
            without admin access"
        StrCpy $pythonpath ""
        Goto PythonMissing
    PythonFound:
    Push $1
    Call Trim
    Pop $pythonpath
    ;StrCpy $pythonpath $1
    PythonMissing:
FunctionEnd


Function TestPythonSilent
    nsExec::ExecToStack '"where" python.exe'
    Pop $0 ;return value
    Pop $1 ;return value
    IntCmp $0 0 PythonFound
        StrCpy $pythonpath ""
        Goto PythonMissing
    PythonFound:
    Push $1
    Call Trim
    Pop $pythonpath
    ;StrCpy $pythonpath $1
    PythonMissing:
FunctionEnd


Function UpdateConfig
    SetOutPath "E:\Chad\Development\git\tvheadend-locast\"
    StrCpy $cmd 'python -m build.UpdateConfig --username "$user" --password "$pwd" --installdir "$INSTDIR"'
    nsExec::ExecToStack '$cmd'
    Pop $0 ;return value
    Pop $1 ; status text
    IntCmp $0 0 PythonDone
        MessageBox MB_OK "Unable to update Config file. Edit the file manually."
    PythonDone:
FunctionEnd



Function AddFiles
    !define SOURCEPATH ".."
    SetOutPath "$INSTDIR"
    File "${SOURCEPATH}\tvh_main.py"
    File "${SOURCEPATH}\LICENSE"
    File "${SOURCEPATH}\CHANGELOG.md"
    File "${SOURCEPATH}\.dockerignore"
    File "${SOURCEPATH}\docker-compose.yml"
    File "${SOURCEPATH}\Dockerfile"
    File "${SOURCEPATH}\Dockerfile_tvh"
    File "${SOURCEPATH}\README.md"
    Rename "$INSTDIR\README.md" "$INSTDIR\README.txt"

    SetOutPath "$INSTDIR\lib"
    File "${SOURCEPATH}\lib\*.py"

    SetOutPath "$INSTDIR\lib\m3u8"
    File "${SOURCEPATH}\lib\m3u8\*.*"
    File "${SOURCEPATH}\lib\m3u8\LICENSE"

    SetOutPath "$INSTDIR\lib\m3u8\iso8601"
    File "${SOURCEPATH}\lib\m3u8\iso8601\*.*"
    File "${SOURCEPATH}\lib\m3u8\iso8601\LICENSE"

    SetOutPath "$INSTDIR\lib\tvheadend"
    File "${SOURCEPATH}\lib\tvheadend\config_example.ini"
    File "${SOURCEPATH}\lib\tvheadend\*.py"

    SetOutPath "$INSTDIR\lib\tvheadend\service\Unix"
    File "${SOURCEPATH}\lib\tvheadend\service\Unix\locast.service"

    SetOutPath "$INSTDIR\lib\tvheadend\service\Windows"
    File "${SOURCEPATH}\lib\tvheadend\service\Windows\nssm*.*"

    SetOutPath "$INSTDIR\cache\stations"
    File "${SOURCEPATH}\cache\stations\README.txt"

FunctionEnd

; arg: $subfolder
; return: $subfolder
Function GetSubfolder
    FindFirst $0 $1 "$subfolder"
    StrCmp $1 "" empty
    ${If} ${FileExists} "$subfolder"
        StrCpy $subfolder $1
    ${EndIf}
    Goto done

    empty:
    StrCpy $subfolder ""

    done:
    FindClose $0
FunctionEnd


Function InstallService

    Call TestPythonSilent
    StrCmp "$pythonpath" "" 0 found
        MessageBox MB_OK "Unable to detect python install, aborting $pythonpath"
        Abort
    found:

    SetOutPath "E:\Chad\Development\git\tvheadend-locast\"
    StrCpy $cmd '"$INSTDIR\lib\tvheadend\service\Windows\nssm.exe" install TVHeadend-Locast \
        "$pythonpath" "\""$INSTDIR\tvh_main.py\"""'
    nsExec::ExecToStack '$cmd'
    Pop $0 ;return value
    Pop $1 ; status text
    IntCmp $0 5 ServiceAlreadyInstalled
    IntCmp $0 0 ServiceDone
        MessageBox MB_OK "Service not installed. status:$0 $1"
    ServiceDone:

    StrCpy $cmd '$INSTDIR\lib\tvheadend\service\Windows\nssm.exe set TVHeadend-Locast AppDirectory "$INSTDIR"'
    nsExec::ExecToStack '$cmd'
    Pop $0 ;return value
    Pop $1 ; status text
    IntCmp $0 0 Service2Done
        MessageBox MB_OK "Service update AppDirectory failed.  status:$0 $1"
    Service2Done:

    StrCpy $cmd '$INSTDIR\lib\tvheadend\service\Windows\nssm.exe set TVHeadend-Locast AppStdout "$TEMP\tvheadend-locast\out.log"'
    nsExec::ExecToStack '$cmd'
    Pop $0 ;return value
    Pop $1 ; status text
    IntCmp $0 0 Service3Done
        MessageBox MB_OK "Service update AppDirectory failed.  status:$0 $1"
    Service3Done:

    StrCpy $cmd '$INSTDIR\lib\tvheadend\service\Windows\nssm.exe set TVHeadend-Locast AppStderr "$TEMP\tvheadend-locast\error.log"'
    nsExec::ExecToStack '$cmd'
    Pop $0 ;return value
    Pop $1 ; status text
    IntCmp $0 0 Service4Done
        MessageBox MB_OK "Service update AppDirectory failed.  status:$0 $1"
    Goto Service4Done

    ServiceAlreadyInstalled:
    MessageBox MB_OK "Service already installed"


    Service4Done:

FunctionEnd


Function un.installService

    StrCpy $cmd '"$INSTDIR\lib\tvheadend\service\Windows\nssm.exe" stop TVHeadend-Locast'
    nsExec::ExecToStack '$cmd'
    Pop $0 ;return value
    Pop $1 ; status text

    SetOutPath "E:\Chad\Development\git\tvheadend-locast\"
    StrCpy $cmd '"$INSTDIR\lib\tvheadend\service\Windows\nssm.exe" remove TVHeadend-Locast confirm'
    nsExec::ExecToStack '$cmd'
    Pop $0 ;return value
    Pop $1 ; status text
    IntCmp $0 0 ServiceDone
        MessageBox MB_OK "Service not uninstalled. status:$0 $1"
    ServiceDone:

FunctionEnd


; Trim
;   Removes leading & trailing whitespace from a string
; Usage:
;   Push
;   Call Trim
;   Pop
Function Trim
	Exch $R1 ; Original string
	Push $R2

Loop:
	StrCpy $R2 "$R1" 1
	StrCmp "$R2" " " TrimLeft
	StrCmp "$R2" "$\r" TrimLeft
	StrCmp "$R2" "$\n" TrimLeft
	StrCmp "$R2" "$\t" TrimLeft
	GoTo Loop2
TrimLeft:
	StrCpy $R1 "$R1" "" 1
	Goto Loop

Loop2:
	StrCpy $R2 "$R1" 1 -1
	StrCmp "$R2" " " TrimRight
	StrCmp "$R2" "$\r" TrimRight
	StrCmp "$R2" "$\n" TrimRight
	StrCmp "$R2" "$\t" TrimRight
	GoTo Done
TrimRight:
	StrCpy $R1 "$R1" -1
	Goto Loop2

Done:
	Pop $R2
	Exch $R1
FunctionEnd

; https://stackoverflow.com/questions/38245621/nsis-refresh-environment-during-setup
!include LogicLib.nsh
!include WinCore.nsh
!ifndef NSIS_CHAR_SIZE
    !define NSIS_CHAR_SIZE 1
    !define SYSTYP_PTR i
!else
    !define SYSTYP_PTR p
!endif
!ifndef ERROR_MORE_DATA
    !define ERROR_MORE_DATA 234
!endif
/*!ifndef KEY_READ
    !define KEY_READ 0x20019
!endif*/

Function RegReadExpandStringAlloc
    System::Store S
    Pop $R2 ; reg value
    Pop $R3 ; reg path
    Pop $R4 ; reg hkey
    System::Alloc 1 ; mem
    StrCpy $3 0 ; size

    loop:
        System::Call 'SHLWAPI::SHGetValue(${SYSTYP_PTR}R4,tR3,tR2,i0,${SYSTYP_PTR}sr2,*ir3r3)i.r0' ; NOTE: Requires SHLWAPI 4.70 (IE 3.01+ / Win95OSR2+)
        ${If} $0 = 0
            Push $2
            Push $0
        ${Else}
            System::Free $2
            ${If} $0 = ${ERROR_MORE_DATA}
                IntOp $3 $3 + ${NSIS_CHAR_SIZE} ; Make sure there is room for SHGetValue to \0 terminate
                System::Alloc $3
                Goto loop
            ${Else}
                Push $0
            ${EndIf}
        ${EndIf}
    System::Store L
FunctionEnd

Function RefreshProcessEnvironmentPath
    System::Store S
    Push ${HKEY_CURRENT_USER}
    Push "Environment"
    Push "Path"
    Call RegReadExpandStringAlloc
    Pop $0

    ${IfThen} $0 <> 0 ${|} System::Call *(i0)${SYSTYP_PTR}.s ${|}
    Pop $1
    Push ${HKEY_LOCAL_MACHINE}
    Push "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
    Push "Path"
    Call RegReadExpandStringAlloc
    Pop $0

    ${IfThen} $0 <> 0 ${|} System::Call *(i0)${SYSTYP_PTR}.s ${|}
    Pop $2
    System::Call 'KERNEL32::lstrlen(t)(${SYSTYP_PTR}r1)i.R1'
    System::Call 'KERNEL32::lstrlen(t)(${SYSTYP_PTR}r2)i.R2'
    System::Call '*(&t$R2 "",&t$R1 "",i)${SYSTYP_PTR}.r0' ; The i is 4 bytes, enough for a ';' separator and a '\0' terminator (Unicode)
    StrCpy $3 ""

    ${If} $R1 <> 0
    ${AndIf} $R2 <> 0
        StrCpy $3 ";"
    ${EndIf}

    System::Call 'USER32::wsprintf(${SYSTYP_PTR}r0,t"%s%s%s",${SYSTYP_PTR}r2,tr3,${SYSTYP_PTR}r1)?c'
    System::Free $1
    System::Free $2
    System::Call 'KERNEL32::SetEnvironmentVariable(t"PATH",${SYSTYP_PTR}r0)'
    System::Free $0
    System::Store L
FunctionEnd
