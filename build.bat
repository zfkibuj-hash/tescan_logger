@echo off
REM TESCAN VEGA3 Log Analyzer - Build script
REM Produces: dist/tescan_logger/ (one-dir bundle)

echo === TESCAN VEGA3 Log Analyzer - Build ===
echo.

REM Activate venv if exists
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Install requirements
pip install -r requirements.txt

REM Build with PyInstaller
pyinstaller --onedir --windowed --name tescan_logger ^
    --add-data "config;config" ^
    --add-data "sample_logs;sample_logs" ^
    main.py

echo.
echo === Build complete ===
echo Output: dist\tescan_logger\
pause
