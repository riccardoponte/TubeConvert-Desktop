@echo off
rem Avvia TubeConvert mostrando la console (utile per vedere eventuali errori).
cd /d "%~dp0"
"runtime\python.exe" -s -E main.py
pause
