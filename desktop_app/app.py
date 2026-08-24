import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

SPLIT_LIMIT_BYTES = int(3.9 * 1024 * 1024 * 1024)
HEIGHTS = {"480p": (480, 28), "720p": (720, 26), "1080p": (1080, 23)}


class ReelCutterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Reel Cutter - Local FFmpeg")
        self.root.geometry("780x560")
        self.root.minsize(680, 480)
        self.events = queue.Queue()
        self.video_path = None
        self.busy = False
        self._build_ui()
        self._poll_events()

    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        root_frame = ttk.Frame(self.root, padding=22)
        root_frame.pack(fill="both", expand=True)
        root_frame.columnconfigure(0, weight=1)
        root_frame.rowconfigure(3, weight=1)

        ttk.Label(root_frame, text="REEL CUTTER", font=("Segoe UI", 24, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            root_frame,
            text="Local video compression and large-file splitting powered by native FFmpeg",
        ).grid(row=1, column=0, sticky="w", pady=(2, 18))

        file_frame = ttk.LabelFrame(root_frame, text="Source video", padding=14)
        file_frame.grid(row=2, column=0, sticky="ew")
        file_frame.columnconfigure(1, weight=1)
        ttk.Button(file_frame, text="Choose video", command=self.choose_video).grid(row=0, column=0, padx=(0, 10))
        self.file_label = ttk.Label(file_frame, text="No video selected", anchor="w")
        self.file_label.grid(row=0, column=1, sticky="ew")
        self.info_label = ttk.Label(file_frame, text="", foreground="#666")
        self.info_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))

        work_frame = ttk.LabelFrame(root_frame, text="Compression", padding=14)
        work_frame.grid(row=3, column=0, sticky="nsew", pady=(16, 0))
        work_frame.columnconfigure(1, weight=1)
        work_frame.rowconfigure(4, weight=1)

        ttk.Label(work_frame, text="Output size").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.height_var = tk.StringVar(value="720p")
        self.height_menu = ttk.Combobox(work_frame, textvariable=self.height_var, values=list(HEIGHTS), state="readonly", width=14)
        self.height_menu.grid(row=0, column=1, sticky="w")

        self.split_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            work_frame,
            text="Automatically split files over 3.9 GiB before compressing",
            variable=self.split_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 0))

        button_frame = ttk.Frame(work_frame)
        button_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(16, 8))
        self.compress_button = ttk.Button(button_frame, text="Compress video", command=self.start_compress)
        self.compress_button.pack(side="left", padx=(0, 8))
        self.split_button = ttk.Button(button_frame, text="Split into two parts", command=self.start_split)
        self.split_button.pack(side="left")

        self.progress = ttk.Progressbar(work_frame, mode="determinate", maximum=100)
        self.progress.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 8))
        self.status_label = ttk.Label(work_frame, text="Ready")
        self.status_label.grid(row=4, column=0, columnspan=2, sticky="nw")

        self.output_text = tk.Text(work_frame, height=8, state="disabled", wrap="word", background="#f5f5f5")
        self.output_text.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(12, 0))

        ttk.Label(
            root_frame,
            text="Everything runs on this computer. Files are never uploaded by this app.",
            foreground="#666",
        ).grid(row=4, column=0, sticky="w", pady=(14, 0))

    def choose_video(self):
        selected = filedialog.askopenfilename(
            title="Choose a video",
            filetypes=[
                ("Video files", "*.mp4 *.mov *.mkv *.webm *.avi *.m4v"),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            return
        self.video_path = Path(selected)
        self.file_label.configure(text=self.video_path.name)
        size = self.video_path.stat().st_size
        self.info_label.configure(text=f"{self._format_bytes(size)} - native FFmpeg processing")
        self._set_status("Ready")

    def start_compress(self):
        if not self._require_video():
            return
        if self.busy:
            return
        self._set_busy(True)
        threading.Thread(target=self._compress_worker, daemon=True).start()

    def start_split(self):
        if not self._require_video():
            return
        if self.busy:
            return
        self._set_busy(True)
        threading.Thread(target=self._split_worker, daemon=True).start()

    def _compress_worker(self):
        try:
            height, crf = HEIGHTS[self.height_var.get()]
            size = self.video_path.stat().st_size
            if size > SPLIT_LIMIT_BYTES and self.split_var.get():
                self._event("status", f"Large file detected ({self._format_bytes(size)}). Splitting before compression...")
                parts = self._split_file(self.video_path)
                outputs = []
                for index, part in enumerate(parts, 1):
                    self._event("status", f"Compressing part {index} of {len(parts)}...")
                    outputs.append(self._compress_file(part, height, crf, index, len(parts)))
                self._event("done", outputs)
            else:
                self._event("status", "Compressing locally with native FFmpeg...")
                output = self._compress_file(self.video_path, height, crf, 1, 1)
                self._event("done", [output])
        except Exception as error:
            self._event("error", str(error))

    def _split_worker(self):
        try:
            self._event("status", "Splitting without re-encoding...")
            parts = self._split_file(self.video_path)
            self._event("done", parts)
        except Exception as error:
            self._event("error", str(error))

    def _split_file(self, source):
        duration = self._probe_duration(source)
        midpoint = duration / 2
        output_base = source.with_name(source.stem + "_parts")
        part_one = output_base.with_name(output_base.name + "_1.mp4")
        part_two = output_base.with_name(output_base.name + "_2.mp4")
        commands = [
            (0, midpoint, part_one),
            (midpoint, duration - midpoint, part_two),
        ]
        for index, (start, length, output) in enumerate(commands, 1):
            self._run_ffmpeg(
                [
                    "-ss", str(start), "-i", str(source), "-t", str(length),
                    "-map", "0", "-c", "copy", "-avoid_negative_ts", "make_zero", "-y", str(output),
                ],
                duration=length,
                progress_offset=(index - 1) * 50,
                progress_scale=50,
            )
        return [part_one, part_two]

    def _compress_file(self, source, height, crf, index, total):
        output = source.with_name(source.stem + f"_{height}p_compressed.mp4")
        duration = self._probe_duration(source)
        self._run_ffmpeg(
            [
                "-i", str(source), "-vf", f"scale=-2:{height}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-y", str(output),
            ],
            duration=duration,
            progress_offset=(index - 1) * (100 / total),
            progress_scale=100 / total,
        )
        return output

    def _run_ffmpeg(self, arguments, duration, progress_offset, progress_scale):
        ffmpeg = self._find_binary("ffmpeg")
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats"] + arguments
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=flags)
        stderr_lines = []
        while True:
            line = process.stdout.readline()
            if line:
                if line.startswith("out_time_us="):
                    try:
                        seconds = int(line.split("=", 1)[1]) / 1_000_000
                        percent = min(100, max(0, seconds / duration * 100)) if duration else 0
                        self._event("progress", progress_offset + percent / 100 * progress_scale)
                    except ValueError:
                        pass
            elif process.poll() is not None:
                break
        stderr = process.stderr.read().strip()
        return_code = process.wait()
        if return_code:
            raise RuntimeError(stderr or f"FFmpeg failed with exit code {return_code}")
        self._event("progress", progress_offset + progress_scale)

    def _probe_duration(self, source):
        ffprobe = self._find_binary("ffprobe")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(source)],
            capture_output=True, text=True, check=True, creationflags=flags,
        )
        return float(result.stdout.strip())

    def _find_binary(self, name):
        binary = shutil.which(name)
        if binary:
            return binary
        bundled = Path(__file__).resolve().parent / "bin" / (name + (".exe" if os.name == "nt" else ""))
        if bundled.exists():
            return str(bundled)
        raise RuntimeError(f"Could not find {name}. Install FFmpeg and add it to PATH, or place it in desktop_app/bin/.")

    def _require_video(self):
        if not self.video_path:
            messagebox.showwarning("Choose a video", "Choose a source video first.")
            return False
        if not self.video_path.exists():
            messagebox.showerror("File missing", "The selected video no longer exists.")
            return False
        return True

    def _set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.compress_button.configure(state=state)
        self.split_button.configure(state=state)

    def _set_status(self, text):
        self.status_label.configure(text=text)

    def _event(self, event_type, value):
        self.events.put((event_type, value))

    def _poll_events(self):
        try:
            while True:
                event_type, value = self.events.get_nowait()
                if event_type == "status":
                    self._set_status(value)
                elif event_type == "progress":
                    self.progress.configure(value=value)
                elif event_type == "done":
                    self._set_busy(False)
                    self.progress.configure(value=100)
                    paths = [Path(item) for item in value]
                    self._set_status("Finished")
                    self._write_outputs(paths)
                elif event_type == "error":
                    self._set_busy(False)
                    self._set_status("Failed")
                    messagebox.showerror("FFmpeg error", value)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _write_outputs(self, paths):
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("end", "Created locally:\n\n")
        for path in paths:
            self.output_text.insert("end", f"{path}\n")
        self.output_text.configure(state="disabled")

    @staticmethod
    def _format_bytes(value):
        units = ("B", "KiB", "MiB", "GiB", "TiB")
        amount = float(value)
        for unit in units:
            if amount < 1024 or unit == units[-1]:
                return f"{amount:.1f} {unit}"
            amount /= 1024
        return f"{amount:.1f} TiB"


def main():
    root = tk.Tk()
    ReelCutterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
