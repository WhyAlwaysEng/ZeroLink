@echo off
title ZeroLink Process Cleaner
echo ====================================================
echo  ZeroLink Process Killer
echo  Terminating any hanging ZeroLink / Stream processes...
echo ====================================================
echo.
taskkill /f /im ZeroLink.exe /t >nul 2>&1
echo [OK] ZeroLink background processes stopped.
echo You can now launch the new version cleanly!
echo.
timeout /t 3
