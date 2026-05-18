@echo off
setlocal
cd /d "%~dp0"
echo Setup TubeMP3...
if not exist .venv (
    py -3 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Setup completato. Avvia con TubeMP3.vbs (doppio click).
pause
