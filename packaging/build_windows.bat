@echo off
setlocal

REM Build VirtualLab for Windows (onedir layout, more reliable with Qt).
REM Run from the packaging\ directory inside a venv that has the cockpit extra + pyinstaller.

echo Building VirtualLab for Windows...
pyinstaller --clean --noconfirm --windowed --name VirtualLab ^
  --paths .. ^
  --hidden-import virtual_lab ^
  --hidden-import virtual_lab.gui.shell.main_window ^
  launch.py

echo.
echo Done: dist\VirtualLab\VirtualLab.exe
echo.
echo Distribute the entire dist\VirtualLab folder (zip it for users).
echo First launch: SmartScreen may warn; click "More info" then "Run anyway".
