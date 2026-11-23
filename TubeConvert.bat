@echo off
rem Avvia TubeConvert con il Python portatile incluso nella cartella "runtime".
cd /d "%~dp0"
if not exist "runtime\pythonw.exe" (
    echo Runtime Python non trovato nella cartella "runtime".
    pause
    exit /b 1
)
start "" "runtime\pythonw.exe" -s -E main.py
