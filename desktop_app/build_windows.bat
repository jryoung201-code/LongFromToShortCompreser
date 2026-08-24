@echo off
setlocal
python -m pip install --upgrade pyinstaller pywebview
pyinstaller --noconfirm --clean --onefile --windowed --name ReelCutter --add-data "index.html;." --add-data "ffmpeg;ffmpeg" --add-binary "desktop_app/bin/ffmpeg.exe;bin" --add-binary "desktop_app/bin/ffprobe.exe;bin" desktop_app\app.py
echo.
echo Built dist\ReelCutter.exe
