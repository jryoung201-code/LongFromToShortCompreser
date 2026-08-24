# LongFromToShortCompreser

The repository contains the GitHub Pages/Jekyll web app and a native desktop app.

## Desktop app

The native app is in `desktop_app/`. It uses FFmpeg on the user's computer, so it can handle files larger than the browser WebAssembly limit. Files over 3.9 GiB can be split into two valid MP4 parts without re-encoding first, then each part is compressed to H.264/AAC MP4.

Run it locally with:

```bash
python desktop_app/app.py
```

On Windows, run `desktop_app\\build_windows.bat` to build `dist\\ReelCutter.exe`. GitHub Actions can also build the Windows executable from the **Build Reel Cutter Windows EXE** workflow.