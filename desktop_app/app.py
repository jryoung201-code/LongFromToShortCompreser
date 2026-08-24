import json
import cgi
import http.server
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

SPLIT_LIMIT_BYTES = int(3.9 * 1024 * 1024 * 1024)
HEIGHTS = {"480p": (480, 28), "720p": (720, 26), "1080p": (1080, 23)}
DEFAULT_TEMPLATE = json.dumps([{
    "start": "00:00:05", "end": "00:00:18", "title": "Short title",
    "hook": "Scroll stopping hook", "captions": ["Caption line 1", "Caption line 2"],
    "aspectRatio": "9:16", "effects": ["zoom-in"]
}], indent=2)


def find_ffmpeg_binary(name):
    binary_name = name + (".exe" if os.name == "nt" else "")
    if shutil.which(name):
        return shutil.which(name)
    roots = [Path(__file__).resolve().parent / "bin"]
    if getattr(sys, "frozen", False):
        roots.insert(0, Path(sys._MEIPASS) / "bin")
    for root in roots:
        candidate = root / binary_name
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(f"Could not find bundled {binary_name}.")


class CompressionHandler(http.server.BaseHTTPRequestHandler):
    server_version = "ReelCutterLocalFFmpeg/1.0"

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path != "/compress":
            self.send_error(404)
            return
        input_path = None
        output_path = None
        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")},
            )
            if "video" not in form:
                self._json_error(400, "Attach a video using the video field.")
                return
            height = int(form.getfirst("height", "720"))
            if height not in (480, 720, 1080):
                self._json_error(400, "height must be 480, 720, or 1080.")
                return
            with tempfile.NamedTemporaryFile(prefix="reel-cutter-", suffix=".input", delete=False) as source:
                input_path = source.name
                field = form["video"]
                while True:
                    chunk = field.file.read(1024 * 1024)
                    if not chunk:
                        break
                    source.write(chunk)
            output_path = tempfile.mktemp(prefix="reel-cutter-", suffix=".mp4")
            subprocess.run([
                find_ffmpeg_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-i", input_path,
                "-vf", f"scale=-2:{height}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-y", output_path,
            ], check=True, capture_output=True, text=True)
            data = Path(output_path).read_bytes()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", 'attachment; filename="compressed.mp4"')
            self.end_headers()
            self.wfile.write(data)
        except (ValueError, KeyError):
            self._json_error(400, "Invalid compression request.")
        except subprocess.CalledProcessError as error:
            self._json_error(500, error.stderr.strip() or "FFmpeg compression failed.")
        except Exception as error:
            self._json_error(500, str(error))
        finally:
            for path in (input_path, output_path):
                if path:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

    def _json_error(self, status, message):
        body = json.dumps({"error": message}).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


class ReelCutterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Reel Cutter - Local FFmpeg")
        self.root.geometry("860x920")
        self.root.minsize(700, 650)
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
        self.colors = {
            "bg": "#14161a", "surface": "#1c1f24", "surface2": "#23272e",
            "line": "#33383f", "text": "#eceef0", "dim": "#9aa1ab",
            "accent": "#00d9b8", "coral": "#ff4d6d"
        }
        self.root.configure(background=self.colors["bg"])
        style.configure("TFrame", background=self.colors["bg"])
        style.configure("TLabel", background=self.colors["bg"], foreground=self.colors["text"], font=("Segoe UI", 10))
        style.configure("TLabelframe", background=self.colors["bg"], foreground=self.colors["accent"], bordercolor=self.colors["line"])
        style.configure("TLabelframe.Label", background=self.colors["bg"], foreground=self.colors["accent"], font=("Segoe UI", 10, "bold"))
        style.configure("TButton", background=self.colors["surface2"], foreground=self.colors["text"], bordercolor=self.colors["line"], padding=(12, 8))
        style.map("TButton", background=[("active", self.colors["line"])])
        style.configure("TCombobox", fieldbackground="#101215", background=self.colors["surface2"], foreground=self.colors["text"])
        style.configure("Horizontal.TProgressbar", troughcolor=self.colors["surface"], background=self.colors["accent"])

        root_frame = ttk.Frame(self.root, padding=(32, 18, 32, 24))
        root_frame.pack(fill="both", expand=True)
        root_frame.columnconfigure(0, weight=1)
        root_frame.rowconfigure(5, weight=1)
        root_frame.rowconfigure(6, weight=1)

        tk.Frame(root_frame, height=12, bg="#000000").grid(row=0, column=0, sticky="ew", pady=(0, 28))
        tk.Label(root_frame, text="●  LOCAL & IN-BROWSER · NATIVE DESKTOP POWER", bg=self.colors["bg"], fg=self.colors["accent"], font=("Consolas", 9, "bold")).grid(row=1, column=0, sticky="w")
        tk.Label(root_frame, text="Cut the boring parts.\nKeep the hook.", bg=self.colors["bg"], fg=self.colors["text"], justify="left", font=("Arial", 31, "bold")).grid(row=2, column=0, sticky="w", pady=(8, 4))
        tk.Label(root_frame, text="Upload a long-form video, generate an AI editing plan, and render real vertical shorts locally with native FFmpeg.", bg=self.colors["bg"], fg=self.colors["dim"], wraplength=760, justify="left", font=("Segoe UI", 11)).grid(row=3, column=0, sticky="w", pady=(0, 22))

        file_frame = ttk.LabelFrame(root_frame, text="01  UPLOAD", padding=14)
        file_frame.grid(row=4, column=0, sticky="ew")
        file_frame.columnconfigure(1, weight=1)
        ttk.Button(file_frame, text="Choose video", command=self.choose_video).grid(row=0, column=0, padx=(0, 10))
        self.file_label = ttk.Label(file_frame, text="No video selected", anchor="w")
        self.file_label.grid(row=0, column=1, sticky="ew")
        self.info_label = ttk.Label(file_frame, text="", foreground="#666")
        self.info_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))

        work_frame = ttk.LabelFrame(root_frame, text="02  SHRINK", padding=14)
        work_frame.grid(row=5, column=0, sticky="nsew", pady=(16, 0))
        work_frame.columnconfigure(1, weight=1)
        work_frame.rowconfigure(5, weight=1)

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

        ai_frame = ttk.LabelFrame(root_frame, text="03  TARGET AI / TEMPLATE / PROMPT / RESPONSE / RENDER", padding=14)
        ai_frame.grid(row=6, column=0, sticky="nsew", pady=(16, 0))
        ai_frame.columnconfigure(1, weight=1)
        ai_frame.rowconfigure(4, weight=1)
        ttk.Label(ai_frame, text="AI model").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.model_var = tk.StringVar(value="ChatGPT")
        ttk.Combobox(ai_frame, textvariable=self.model_var, values=["ChatGPT", "Claude", "Gemini", "Grok", "Other model"], state="readonly", width=18).grid(row=0, column=1, sticky="w")
        ttk.Button(ai_frame, text="Generate prompt", command=self.generate_prompt).grid(row=0, column=2, padx=(10, 0))

        ttk.Label(ai_frame, text="Editing-output JSON template").grid(row=1, column=0, columnspan=3, sticky="w", pady=(12, 4))
        self.template_text = tk.Text(ai_frame, height=8, wrap="word")
        self.template_text.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.template_text.insert("1.0", DEFAULT_TEMPLATE)

        ttk.Label(ai_frame, text="Generated prompt").grid(row=3, column=0, columnspan=3, sticky="w", pady=(12, 4))
        self.prompt_text = tk.Text(ai_frame, height=7, wrap="word")
        self.prompt_text.grid(row=4, column=0, columnspan=3, sticky="ew")
        ttk.Label(ai_frame, text="Paste the AI response containing <Code> JSON").grid(row=5, column=0, columnspan=3, sticky="w", pady=(12, 4))
        self.response_text = tk.Text(ai_frame, height=7, wrap="word")
        self.response_text.grid(row=6, column=0, columnspan=3, sticky="ew")
        ttk.Button(ai_frame, text="Parse plan and render shorts", command=self.parse_and_render).grid(row=7, column=0, columnspan=3, sticky="w", pady=(10, 0))

        ttk.Label(
            root_frame,
            text="Everything runs on this computer. Files are never uploaded by this app.",
            foreground=self.colors["dim"],
        ).grid(row=7, column=0, sticky="w", pady=(14, 0))

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

    def generate_prompt(self):
        if not self._require_video():
            return
        try:
            json.loads(self.template_text.get("1.0", "end"))
        except json.JSONDecodeError as error:
            messagebox.showerror("Invalid template", str(error))
            return
        prompt = (
            f"Analyze the attached video '{self.video_path.name}' for TikTok, YouTube Shorts, and Instagram Reels.\n\n"
            "First confirm the exact duration. Then identify strong moments with exact start/end timestamps, titles, hooks, captions, aspect ratios, and effects.\n\n"
            "Return the final editing plan only as JSON inside <Code> tags, matching this template exactly:\n\n"
            f"<Code>\n{self.template_text.get('1.0', 'end').strip()}\n</Code>"
        )
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", prompt)

    def parse_and_render(self):
        if not self._require_video() or self.busy:
            return
        raw = self.response_text.get("1.0", "end").strip()
        if "<Code>" in raw:
            raw = raw.split("<Code>", 1)[1].split("</Code>", 1)[0]
        raw = raw.replace("```json", "").replace("```", "").strip()
        try:
            clips = json.loads(raw)
            if not isinstance(clips, list):
                clips = [clips]
            if not clips:
                raise ValueError("The plan contains no clips.")
            for clip in clips:
                if self._timecode(clip["end"]) <= self._timecode(clip["start"]):
                    raise ValueError("Every clip end must be after its start.")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            messagebox.showerror("Invalid editing plan", str(error))
            return
        self._set_busy(True)
        threading.Thread(target=self._render_worker, args=(clips,), daemon=True).start()

    def _render_worker(self, clips):
        try:
            outputs = []
            for index, clip in enumerate(clips, 1):
                start = self._timecode(clip["start"])
                end = self._timecode(clip["end"])
                output = self.video_path.with_name(f"{self.video_path.stem}_short_{index}.mp4")
                self._event("status", f"Rendering short {index} of {len(clips)} with audio...")
                self._run_ffmpeg([
                    "-ss", str(start), "-i", str(self.video_path), "-t", str(end - start),
                    "-vf", "scale=-2:1080", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-y", str(output)
                ], end - start, (index - 1) * (100 / len(clips)), 100 / len(clips))
                outputs.append(output)
            self._event("done", outputs)
        except Exception as error:
            self._event("error", str(error))

    @staticmethod
    def _timecode(value):
        if isinstance(value, (int, float)):
            return float(value)
        parts = [float(part) for part in str(value).split(":")]
        seconds = 0.0
        for part in parts:
            seconds = seconds * 60 + part
        return seconds

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
        binary_name = name + (".exe" if os.name == "nt" else "")
        search_dirs = [Path(__file__).resolve().parent / "bin"]
        if getattr(sys, "frozen", False):
            search_dirs.insert(0, Path(sys._MEIPASS) / "bin")
        for directory in search_dirs:
            bundled = directory / binary_name
            if bundled.exists():
                return str(bundled)
        raise RuntimeError(f"Could not find {name}. The app needs bundled FFmpeg or an FFmpeg installation on PATH.")

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
    try:
        import webview
    except ImportError as error:
        raise SystemExit("The desktop app requires pywebview. Rebuild it with the provided Windows build workflow.") from error

    if getattr(sys, "frozen", False):
        project_root = Path(sys._MEIPASS)
    else:
        project_root = Path(__file__).resolve().parents[1]
    html_path = project_root / "index.html"
    if not html_path.exists():
        raise SystemExit(f"Could not find the bundled website UI at {html_path}.")

    html = html_path.read_text(encoding="utf-8")
    local_server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), CompressionHandler)
    threading.Thread(target=local_server.serve_forever, daemon=True).start()
    local_compress_url = f"http://127.0.0.1:{local_server.server_port}/compress"
    html = html.replace(
        '        <button class="btn-ghost" id="splitBtn" type="button" disabled>Split into 2 chunks</button>\n',
        "",
    )
    html = html.replace("      el('splitBtn').disabled = false;\n", "")
    split_start = html.find("  el('splitBtn').addEventListener('click'")
    if split_start >= 0:
        split_end = html.find("  function renderCompressRuler", split_start)
        html = html[:split_start] + html[split_end:]
    html = html.replace(
        "    banner(cBanner, 'ok', 'Loading the ffmpeg engine (first run only)…');",
        "    banner(cBanner, 'ok', 'Compressing with local FFmpeg…');",
    )
    html = html.replace(
        "    compressVideo(state.file, targetHeight, function(pct){",
        "    compressWithLocalServer(state.file, targetHeight, function(pct){",
        1,
    )
    marker = "  function compressVideo(file, targetHeight, onProgress){"
    helper = """  function compressWithLocalServer(file, targetHeight, onProgress){
    onProgress(0);
    var form = new FormData();
    form.append('video', file, file.name);
    form.append('height', String(targetHeight));
    return fetch(compressionUrl, { method: 'POST', body: form }).then(function(res){
      if (!res.ok) return res.text().then(function(text){ throw new Error(text || 'Local FFmpeg compression failed.'); });
      onProgress(1);
      return res.blob();
    });
  }

"""
    html = html.replace(marker, "  var compressionUrl = '" + local_compress_url + "';\n\n" + helper + marker, 1)
    html = html.replace(
        '<p><a class="btn-primary" href="https://github.com/jryoung201-code/LongFromToShortCompreser/releases/latest/download/ReelCutter.exe">Download the Windows app</a></p>',
        "",
    )
    html = html.replace(
        '<p class="desc"><strong>Browser limit: 3.5 GB per video.</strong> To work with files larger than 3.5 GB, install the full Reel Cutter app.</p>',
        "",
    )
    html = html.replace("<head>", f'<head><base href="{html_path.parent.as_uri()}/">', 1)
    webview.create_window("Reel Cutter", html=html, width=1120, height=900, min_size=(760, 600))
    webview.start()


if __name__ == "__main__":
    main()
