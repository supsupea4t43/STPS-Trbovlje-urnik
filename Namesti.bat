@echo off
rem Namesti Urnik STPS - dvoklik na to datoteko je dovolj.
rem Batch se zazene ne glede na pravila za skripte PowerShell.
title Namestitev - Urnik STPS
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
