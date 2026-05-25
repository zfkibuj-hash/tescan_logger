@echo off
REM TESCAN VEGA3 Log Analyzer - Development runner

echo === TESCAN VEGA3 Log Analyzer (dev) ===
echo.

REM Create venv if not exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate venv
call venv\Scripts\activate.bat

REM Install requirements
pip install -r requirements.txt -q

REM Run application
python main.py %*
