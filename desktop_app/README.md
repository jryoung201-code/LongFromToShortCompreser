# Reel Cutter Desktop App

This is the native desktop version of Reel Cutter. It opens the same HTML interface as the website inside a native window and keeps video processing on the user's computer.

The EXE starts a private localhost FFmpeg service automatically. The HTML compression control sends the video to that local service instead of loading the entire file into browser WebAssembly memory. The desktop copy hides the website download link, browser warning, and split control.

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

This creates `dist\ReelCutter.exe` with the website HTML, vendor FFmpeg, native FFmpeg, and ffprobe bundled. The target computer does not need a separate FFmpeg installation.
