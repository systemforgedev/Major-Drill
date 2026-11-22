"""Speaks calls out loud on its own thread so the live loop never waits on audio."""
from __future__ import annotations

import queue
import threading


class Voice:
    def __init__(self, enabled: bool = True, rate: int = 190):
        self.enabled = enabled
        self.rate = rate
        self.q: queue.Queue[str | None] = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        engine = None
        if self.enabled:
            try:
                import pyttsx3

                engine = pyttsx3.init()  # created on this thread, as pyttsx3 requires
                engine.setProperty("rate", self.rate)
            except Exception as e:  # no audio device, missing package...
                print(f"[voice] text-to-speech unavailable ({e}); printing calls instead")
        while (text := self.q.get()) is not None:
            print(f"[teammate] {text}")
            if engine:
                engine.say(text)
                engine.runAndWait()

    def say(self, text: str):
        # Drop stale calls: if something is still queued, the new call replaces it.
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass
        self.q.put(text)

    def close(self):
        self.q.put(None)
