"""progress.py - show encoding progress when the user presses Enter.

Usage from encode.py:
    from progress import ProgressTracker
    tracker = ProgressTracker()          # one per run (create it in VideoEncoder.__init__)

    # instead of  .run(overwrite_output=True, cmd=FFMPEG_BIN, quiet=True):
    _, err = tracker.run(
        ffmpeg.input(source).output(output_path, **params),
        cmd=FFMPEG_BIN, name=display_name, duration=duration,
    )

    # for prompts that can appear while jobs are running:
    answer = tracker.ask("... (y/n): ")

tracker.run() behaves like .run(quiet=True): it returns (stdout, stderr) bytes and
raises ffmpeg.Error (with .stderr filled in) when ffmpeg fails.
"""
import os
import select
import sys
import threading
import time

import ffmpeg

BAR_WIDTH = 24


def _fmt_time(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


def _bar(fraction: float) -> str:
    fraction = min(1.0, max(0.0, fraction))
    filled = int(round(fraction * BAR_WIDTH))
    return "█" * filled + "░" * (BAR_WIDTH - filled)


class ProgressTracker:
    def __init__(self, stdin=None, require_tty=True):
        self._stdin = stdin or sys.stdin
        self._require_tty = require_tty
        self._jobs = {}                      
        self._jobs_lock = threading.Lock()
        self._prompting = threading.Event()  
        self._listener = None
        self._listener_lock = threading.Lock()
        self.finished = 0
        self.total = 0

    def set_total(self, total: int) -> None:
        self.total = total

    def ask(self, prompt: str) -> str:
        """input() that the Enter listener won't steal the answer from."""
        self._prompting.set()
        try:
            return input(prompt)
        finally:
            self._prompting.clear()

    def run(self, stream, cmd="ffmpeg", name="", duration=0.0):
        """Run an ffmpeg-python stream, tracking progress under `name`."""
        self._start_listener()
        job = {"pct": None, "out_time": 0.0, "fps": "", "start": time.monotonic(),
               "duration": float(duration or 0)}
        with self._jobs_lock:
            self._jobs[name] = job

        proc = stream.global_args("-progress", "pipe:1", "-nostats", "-nostdin").run_async(
            cmd=cmd, pipe_stdout=True, pipe_stderr=True, overwrite_output=True
        )
        err_chunks = []
        drain = threading.Thread(target=lambda: err_chunks.append(proc.stderr.read()), daemon=True)
        drain.start()
        out_lines = []
        try:
            for raw in proc.stdout:
                key, _, val = raw.decode("utf-8", "replace").strip().partition("=")
                if key in ("out_time_us", "out_time_ms"):
                    try:
                        job["out_time"] = max(0, int(val)) / 1_000_000
                    except ValueError:
                        continue
                    if job["duration"]:
                        job["pct"] = job["out_time"] / job["duration"]
                elif key == "fps":
                    job["fps"] = val
                out_lines.append(raw)
            proc.wait()
            drain.join()
        finally:
            if proc.poll() is None:
                proc.kill()
            with self._jobs_lock:
                self._jobs.pop(name, None)

        stderr = b"".join(err_chunks)
        if proc.returncode != 0:
            raise ffmpeg.Error("ffmpeg", b"".join(out_lines), stderr)
        self.finished += 1
        return b"".join(out_lines), stderr

    def snapshot(self) -> str:
        with self._jobs_lock:
            jobs = list(self._jobs.items())
        head = f"Progress: {self.finished}/{self.total} finished" if self.total else "Progress:"
        if not jobs:
            return f"{head} - nothing encoding right now."
        lines = [head]
        now = time.monotonic()
        for name, j in jobs:
            elapsed = now - j["start"]
            if j["pct"] is not None and j["out_time"] > 0 and elapsed > 0:
                speed = j["out_time"] / elapsed
                eta = _fmt_time((j["duration"] - j["out_time"]) / speed)
                lines.append(
                    f"  {name}\n    [{_bar(j['pct'])}] {j['pct'] * 100:5.1f}%  "
                    f"{speed:.2f}x  ETA {eta}  elapsed {_fmt_time(elapsed)}"
                )
            else:
                lines.append(f"  {name}\n    starting... elapsed {_fmt_time(elapsed)}")
        return "\n".join(lines)

    def _start_listener(self) -> None:
        with self._listener_lock:
            if self._listener is not None:
                return
            if self._require_tty and not self._stdin.isatty():
                self._listener = False
                return
            self._listener = threading.Thread(target=self._listen, daemon=True)
            self._listener.start()

    def _listen(self) -> None:
        while True:
            if self._prompting.is_set():
                time.sleep(0.1)
                continue
            try:
                ready, _, _ = select.select([self._stdin], [], [], 0.3)
                if not ready or self._prompting.is_set():
                    continue
                if os.read(self._stdin.fileno(), 4096) == b"":
                    return
            except (ValueError, OSError):
                return
            print("\n" + self.snapshot(), flush=True)
