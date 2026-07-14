; ── ADELE — NSIS include (electron-builder nsis.include, prepended before installer.nsi) ──
; Must NOT be named installer.nsh: that shadows app-builder-lib's include/installer.nsh when
; installSection does !include "installer.nsh".
; Docs: https://www.electron.build/nsis
;
; Cursor-style "Select additional tasks" page: optional desktop shortcut, Explorer context
; menus, and user PATH. Start menu shortcut still comes from electron-builder defaults.

!include "LogicLib.nsh"
!include "WinMessages.nsh"
!include "WordFunc.nsh"

!ifndef BUILD_UNINSTALLER
!ifndef ONE_CLICK
!define MUI_WELCOMEPAGE_TITLE "Welcome to the ADELE Setup Wizard"
!define MUI_WELCOMEPAGE_TEXT "The Setup Wizard will install ADELE on your computer.$\r$\n$\r$\nClick Next to continue or Cancel to exit the Setup Wizard."
!endif
!endif

!ifndef BUILD_UNINSTALLER
Var ADELE_TASK_DESKTOP
Var ADELE_TASK_FILECTX
Var ADELE_TASK_DIRCTX
Var ADELE_TASK_PATH
Var ADELE_HWND_DSK
Var ADELE_HWND_FILE
Var ADELE_HWND_DIR
Var ADELE_HWND_PATH
Var ADELE_TASKS_DLG
!endif

; MUI_INSTFILESPAGE_* must be defined before installer.nsi includes assistedInstaller.nsh
; (which inserts MUI_PAGE_INSTFILES).
!ifndef BUILD_UNINSTALLER
!ifndef ONE_CLICK
!define MUI_INSTFILESPAGE_HEADER_TITLE "Installing ADELE"
!define MUI_INSTFILESPAGE_HEADER_SUBTITLE "Follow status in the list below. Expand Show details if the detailed log is hidden. A numeric percentage is not available while files are unpacked from the archive."
!endif
!endif

!ifdef BUILD_UNINSTALLER
!define MUI_UNINSTFILESPAGE_HEADER_SUBTITLE "Removal progress is listed under Show details if the detailed log is hidden."
!endif

!macro preInit
  !ifndef BUILD_UNINSTALLER
    ; Silent installs skip the custom tasks page — match assisted defaults (PATH on, rest off).
    StrCpy $ADELE_TASK_DESKTOP "0"
    StrCpy $ADELE_TASK_FILECTX "0"
    StrCpy $ADELE_TASK_DIRCTX "0"
    StrCpy $ADELE_TASK_PATH "1"
  !endif
!macroend

!ifndef BUILD_UNINSTALLER
!ifndef ONE_CLICK
!include "nsDialogs.nsh"

Function ADELE_ShowSetupSteps
  nsDialogs::Create 1018
  Pop $ADELE_TASKS_DLG
  ${NSD_CreateLabel} 5u 2u 100% 12u "What happens during setup"
  Pop $0
  ${NSD_CreateLabel} 5u 16u 100% 120u "This installer runs in four stages. On the next screen, choose optional Windows integration (desktop shortcut, Explorer menus, PATH). Then expand Show details on the install page for Step 1–4 messages in the log.$\r$\n$\r$\n1 - Safety: confirms ADELE is not running; replaces a previous install when upgrading.$\r$\n$\r$\n2 - Files: extracts the desktop app (Electron UI, Python/backend bundle, bundled Chrome extension assets) into your chosen folder.$\r$\n$\r$\n3 - Registration: uninstall information, Start Menu shortcut, and any extra tasks you select.$\r$\n$\r$\n4 - Finish: optionally launch ADELE from the last wizard page.$\r$\n$\r$\nClick Next to continue. Extraction can take a minute on slower disks."
  Pop $0
  nsDialogs::Show
FunctionEnd

Function ADELE_LeaveSetupSteps
FunctionEnd

Function ADELE_ShowAdditionalTasks
  ${If} ${Silent}
    Abort
  ${EndIf}
  nsDialogs::Create 1018
  Pop $ADELE_TASKS_DLG

  ${NSD_CreateLabel} 5u 2u 100% 12u "Select additional tasks"
  Pop $0
  ${NSD_CreateLabel} 5u 16u 100% 24u "Choose how ADELE integrates with Windows (you can change these later by reinstalling)."
  Pop $0

  ${NSD_CreateLabel} 5u 44u 100% 12u "Optional shortcuts and integration"
  Pop $0

  ${NSD_CreateCheckbox} 5u 62u 280u 12u "Create a desktop icon"
  Pop $ADELE_HWND_DSK
  SendMessage $ADELE_HWND_DSK ${BM_SETCHECK} ${BST_UNCHECKED} 0

  ${NSD_CreateCheckbox} 5u 80u 280u 12u "Add $\'Open with ADELE$\' to the file context menu in Windows Explorer"
  Pop $ADELE_HWND_FILE
  SendMessage $ADELE_HWND_FILE ${BM_SETCHECK} ${BST_UNCHECKED} 0

  ${NSD_CreateCheckbox} 5u 98u 280u 12u "Add $\'Open with ADELE$\' to the folder context menu in Windows Explorer"
  Pop $ADELE_HWND_DIR
  SendMessage $ADELE_HWND_DIR ${BM_SETCHECK} ${BST_UNCHECKED} 0

  ${NSD_CreateCheckbox} 5u 116u 280u 24u "Add ADELE to your user PATH (for terminals and scripts; restart terminals after install)"
  Pop $ADELE_HWND_PATH
  SendMessage $ADELE_HWND_PATH ${BM_SETCHECK} ${BST_CHECKED} 0

  nsDialogs::Show
FunctionEnd

Function ADELE_LeaveAdditionalTasks
  ${NSD_GetState} $ADELE_HWND_DSK $ADELE_TASK_DESKTOP
  ${NSD_GetState} $ADELE_HWND_FILE $ADELE_TASK_FILECTX
  ${NSD_GetState} $ADELE_HWND_DIR $ADELE_TASK_DIRCTX
  ${NSD_GetState} $ADELE_HWND_PATH $ADELE_TASK_PATH
FunctionEnd

!macro customPageAfterChangeDir
  Page custom ADELE_ShowSetupSteps ADELE_LeaveSetupSteps
  Page custom ADELE_ShowAdditionalTasks ADELE_LeaveAdditionalTasks
!macroend
!endif
!endif

!macro customHeader
  ; Last ShowInstDetails / ShowUninstDetails wins (overrides common.nsh nevershow).
  ShowInstDetails show
  !ifdef BUILD_UNINSTALLER
    ShowUninstDetails show
  !endif
!macroend

; ── Apply / remove optional integration (installer defines DO_NOT_CREATE_DESKTOP_SHORTCUT) ──
!macro customInstall
  ${If} $ADELE_TASK_DESKTOP == 1
    DetailPrint "ADELE tasks: creating desktop shortcut..."
    CreateShortCut "$DESKTOP\${SHORTCUT_NAME}.lnk" "$INSTDIR\${APP_EXECUTABLE_FILENAME}" "" "$INSTDIR\${APP_EXECUTABLE_FILENAME}" 0
    WinShell::SetLnkAUMI "$DESKTOP\${SHORTCUT_NAME}.lnk" "${APP_ID}"
  ${EndIf}

  ${If} $ADELE_TASK_FILECTX == 1
    DetailPrint "ADELE tasks: file context menu..."
    WriteRegStr HKCU "Software\Classes\*\shell\ADELE" "" "Open with ADELE"
    WriteRegStr HKCU "Software\Classes\*\shell\ADELE\command" "" '"$INSTDIR\${APP_EXECUTABLE_FILENAME}" "%1"'
  ${EndIf}

  ${If} $ADELE_TASK_DIRCTX == 1
    DetailPrint "ADELE tasks: folder context menus..."
    WriteRegStr HKCU "Software\Classes\Directory\shell\ADELE" "" "Open with ADELE"
    WriteRegStr HKCU "Software\Classes\Directory\shell\ADELE\command" "" '"$INSTDIR\${APP_EXECUTABLE_FILENAME}" "%1"'
    WriteRegStr HKCU "Software\Classes\Directory\Background\shell\ADELE" "" "Open with ADELE here"
    WriteRegStr HKCU "Software\Classes\Directory\Background\shell\ADELE\command" "" '"$INSTDIR\${APP_EXECUTABLE_FILENAME}" "%V"'
  ${EndIf}

  ${If} $ADELE_TASK_PATH == 1
    DetailPrint "ADELE tasks: updating user PATH..."
    ReadRegStr $R0 HKCU "Environment" "Path"
    StrLen $R2 $INSTDIR
    StrLen $R3 $R0
    ; If PATH is empty or shorter than INSTDIR, it cannot already contain INSTDIR.
    StrCmp $R0 "" adelePathAppend
    IntCmp $R3 $R2 adelePathScanStart adelePathAppend adelePathScanStart
    adelePathScanStart:
      IntOp $R4 $R3 - $R2
      StrCpy $R5 0
    adelePathScan:
      IntCmp $R5 $R4 adelePathAppend 0 adelePathAppend
      StrCpy $R6 $R0 $R2 $R5
      StrCmp $R6 $INSTDIR adelePathBlockEnd 0
      IntOp $R5 $R5 + 1
      Goto adelePathScan
    adelePathAppend:
      StrCmp $R0 "" adelePathEmpty adelePathNonEmpty
    adelePathEmpty:
      WriteRegStr HKCU "Environment" "Path" $INSTDIR
      Goto adelePathBroadcast
    adelePathNonEmpty:
      WriteRegStr HKCU "Environment" "Path" "$R0;$INSTDIR"
    adelePathBroadcast:
      SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=2000
    adelePathBlockEnd:
  ${EndIf}
!macroend

!macro customUnInstall
  DetailPrint "ADELE tasks: removing optional Explorer menus and PATH entry..."
  DeleteRegKey HKCU "Software\Classes\*\shell\ADELE"
  DeleteRegKey HKCU "Software\Classes\Directory\shell\ADELE"
  DeleteRegKey HKCU "Software\Classes\Directory\Background\shell\ADELE"

  ReadRegStr $R0 HKCU "Environment" "Path"
  StrCmp $R0 "" adeleUnPathDone 0
  ${WordReplace} "$R0" ";$INSTDIR" "" "+S" $R0
  ${WordReplace} "$R0" "$INSTDIR;" "" "+S" $R0
  ${WordReplace} "$R0" "$INSTDIR" "" "" $R0
  StrCmp $R0 "" adeleUnPathDelete adeleUnPathWrite
  adeleUnPathDelete:
    DeleteRegValue HKCU "Environment" "Path"
    Goto adeleUnPathBroadcast
  adeleUnPathWrite:
    WriteRegStr HKCU "Environment" "Path" $R0
  adeleUnPathBroadcast:
    SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=2000
  adeleUnPathDone:

  Delete "$DESKTOP\${SHORTCUT_NAME}.lnk"
!macroend
