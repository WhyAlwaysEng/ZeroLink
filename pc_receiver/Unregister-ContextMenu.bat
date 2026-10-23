@echo off
chcp 65001 >nul
echo ==========================================================
echo       ZeroLink - Unregister Windows Explorer Context Menu
echo ==========================================================
echo.

echo Removing context menu: "Send to Phone via ZeroLink"...
reg delete "HKCU\Software\Classes\*\shell\ZeroLinkSend" /f >nul 2>&1

if %ERRORLEVEL% equ 0 (
    echo.
    echo [SUCCESS] "Send to Phone via ZeroLink" context menu has been removed!
) else (
    echo.
    echo [INFO] Context menu was not found or already removed.
)

echo.
pause
