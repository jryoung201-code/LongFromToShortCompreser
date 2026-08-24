# Reel Cutter Desktop App

This is the native desktop version of Reel Cutter. It uses Python and native FFmpeg, so video files stay on the user's computer.

## Run locally

The downloadable Windows EXE includes `ffmpeg.exe` and `ffprobe.exe`. For running the Python source directly, install FFmpeg and make sure both `ffmpeg` and `ffprobe` are on PATH. Then run:

```bash
python desktop_app/app.py
```

The app can compress one video to 480p, 720p, or 1080p. Files over 3.9 GiB are automatically split into two valid MP4 parts without re-encoding first, then each part is compressed separately with H.264 video and AAC audio.

## Build the Windows EXE

On Windows, run:

```bat
desktop_app\build_windows.bat
```

This creates `dist\ReelCutter.exe` with FFmpeg bundled by the GitHub Actions build. The target computer does not need a separate FFmpeg installation.
