# Reel Cutter Desktop App

This is the native desktop version of Reel Cutter. It uses Python and the system FFmpeg executable, so video files stay on the user's computer.

## Run locally

Install FFmpeg and make sure both `ffmpeg` and `ffprobe` are on PATH. Then run:

```bash
python desktop_app/app.py
```

The app can compress one video to 480p, 720p, or 1080p. Files over 3.9 GiB are automatically split into two valid MP4 parts without re-encoding first, then each part is compressed separately with H.264 video and AAC audio.

## Build the Windows EXE

On Windows, run:

```bat
desktop_app\build_windows.bat
```

This creates `dist\ReelCutter.exe`. The target computer must have FFmpeg installed and available on PATH, unless `ffmpeg.exe` and `ffprobe.exe` are placed in `desktop_app\bin\` before building.
