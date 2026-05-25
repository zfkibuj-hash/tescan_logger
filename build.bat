@echo off
REM TESCAN Log Analyzer — Build EXE (PyInstaller --onedir)
REM Output: dist\tescan_logger\tescan_logger.exe

echo === Building TESCAN Log Analyzer ===

REM Activate venv if exists
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Install dependencies
pip install -r requirements.txt

REM Build
pyinstaller --onedir --windowed ^
    --name "TESCAN_Logger" ^
    --add-data "config;config" ^
    --add-data "docs;docs" ^
    --hidden-import "models" ^
    --hidden-import "database" ^
    --hidden-import "parser" ^
    --hidden-import "services" ^
    --hidden-import "repositories" ^
    --hidden-import "analytics" ^
    --hidden-import "exporters" ^
    --hidden-import "utils" ^
    main.py

echo.
echo === Build complete ===
echo Output: dist\TESCAN_Logger\TESCAN_Logger.exe
echo Zip the dist\TESCAN_Logger folder to distribute.
pause
