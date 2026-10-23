@echo off
chcp 65001 >nul
echo ========================================================
echo       ZeroLink - Register Windows Explorer Context Menu
echo ========================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "EXE_PATH=%SCRIPT_DIR%dist\ZeroLink.exe"

if exist "%EXE_PATH%" (
    set "TARGET_CMD=\"%EXE_PATH%\" --send \"%%1\""
    set "ICON_PATH=\"%EXE_PATH%\""
) else (
    set "PY_SCRIPT=%SCRIPT_DIR%main.py"
    set "TARGET_CMD=pythonw \"%SCRIPT_DIR%main.py\" --send \"%%1\""
    set "ICON_PATH=shell32.dll,138"
)

echo Registering context menu: "Send to Phone via ZeroLink"...
reg add "HKCU\Software\Classes\*\shell\ZeroLinkSend" /ve /d "Send to Phone via ZeroLink" /f >nul
reg add "HKCU\Software\Classes\*\shell\ZeroLinkSend" /v "Icon" /d "%ICON_PATH%" /f >nul
reg add "HKCU\Software\Classes\*\shell\ZeroLinkSend\command" /ve /d "%TARGET_CMD%" /f >nul

if %ERRORLEVEL% equ 0 (
    echo.
    echo [SUCCESS] "Send to Phone via ZeroLink" has been added to your right-click context menu!
    echo Right-click any file in Windows Explorer to send directly to your phone.
) else (
    echo.
    echo [ERROR] Failed to register context menu entry.
)

echo.
pause
