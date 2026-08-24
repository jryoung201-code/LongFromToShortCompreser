@echo off
setlocal
python -m pip install --upgrade pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name ReelCutter desktop_app\app.py
 echo.
echo Built dist\ReelCutter.exe
