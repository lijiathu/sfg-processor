@echo off
echo Building SFG Processor (Flask + web frontend)...
pyinstaller --onefile --windowed --name "SFG_Processor" --clean --noconfirm ^
  --add-data "frontend;frontend" ^
  sfg_app.py
echo.
echo Done! Executable is in dist\SFG_Processor.exe
pause
