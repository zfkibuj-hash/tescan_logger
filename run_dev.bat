@echo off
REM TESCAN Log Analyzer — Development runner

echo === TESCAN Log Analyzer (Dev Mode) ===

REM Create venv if not exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate venv
call venv\Scripts\activate.bat

REM Install deps
pip install -r requirements.txt -q

REM Run
python main.py %*

pause
