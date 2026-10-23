@echo off
:: ZeroLink 1-Click Trust Certificate Setup
:: Run this once to register ZeroLink as a Trusted Publisher on this PC
title ZeroLink - Security Trust Setup
color 0A

echo ================================================================
echo           ZeroLink - Trusted Publisher Setup
echo   Eliminates Windows Defender SmartScreen "Unknown Publisher"
echo ================================================================
echo.

:: Check for administrator permissions
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting Administrator permission to register certificate...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

echo [1/3] Installing ZeroLink Certificate into Trusted Publishers...
certutil -addstore -f "TrustedPublisher" "%~dp0ZeroLink-Certificate.cer" >nul 2>&1

echo [2/3] Installing ZeroLink Certificate into Trusted Root Certification Authorities...
certutil -addstore -f "Root" "%~dp0ZeroLink-Certificate.cer" >nul 2>&1

echo [3/3] Unblocking executable files (removing Internet Mark-of-the-Web)...
powershell -Command "Get-ChildItem -Path '%~dp0' -Recurse -Include *.exe,*.dll | Unblock-File -ErrorAction SilentlyContinue" >nul 2>&1

echo.
echo ================================================================
echo  [OK] ZeroLink is now recognized as a Trusted Publisher!
echo  You can now run ZeroLink.exe without any security warnings.
echo ================================================================
echo.
timeout /t 3 >nul
