"""Screen capture for live mode: still frames for the fast tier, and a
recording of the whole match via ffmpeg. Read-only: nothing touches the game."""
from __future__ import annotations

import io
import subprocess
import sys


class FrameGrabber:
    def __init__(self, monitor: int = 1, max_width: int = 1280, quality: int = 75):
        import mss  # noqa: F401  (fail early with a clear message if missing)

        self.monitor, self.max_width, self.quality = monitor, max_width, quality
        self._sct = None

    def grab_jpeg(self) -> bytes:
        import mss
        from PIL import Image

        if self._sct is None:  # mss objects must be used on the thread that made them
            self._sct = mss.mss()
        shot = self._sct.grab(self._sct.monitors[self.monitor])
        img = Image.frombytes("RGB", shot.size, shot.rgb)
        if img.width > self.max_width:
            img = img.resize((self.max_width, round(img.height * self.max_width / img.width)))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=self.quality)
        return buf.getvalue()


class Recorder:
    """Records the desktop to an mp4 with ffmpeg. Stop cleanly with stop()."""

    def __init__(self, ffmpeg: str, out_path, fps: int = 30):
        if sys.platform == "win32":
            src = ["-f", "gdigrab", "-framerate", str(fps), "-i", "desktop"]
        elif sys.platform == "darwin":
            src = ["-f", "avfoundation", "-framerate", str(fps), "-i", "1:none"]
        else:
            src = ["-f", "x11grab", "-framerate", str(fps), "-i", ":0.0"]
        self.cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *src,
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26", "-pix_fmt", "yuv420p", str(out_path)]
        self.proc = None

    def start(self):
        self.proc = subprocess.Popen(self.cmd, stdin=subprocess.PIPE)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.communicate(b"q", timeout=10)  # ffmpeg finishes the file on 'q'
            except subprocess.TimeoutExpired:
                self.proc.kill()
