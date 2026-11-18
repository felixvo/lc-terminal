"""Solve timer with an optional timebox that fires a desktop notification."""
from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time


def notify(title: str, message: str) -> None:
    """Best-effort desktop notification; works while your editor owns the terminal."""
    try:
        if sys.platform == "darwin":
            script = f'display notification "{message}" with title "{title}" sound name "Glass"'
            subprocess.run(["osascript", "-e", script], check=False, capture_output=True, timeout=5)
        elif shutil.which("notify-send"):
            subprocess.run(["notify-send", title, message], check=False, capture_output=True, timeout=5)
    except Exception:
        pass


class Timer:
    def __init__(self, timebox_minutes: float | None = None):
        self.timebox = timebox_minutes
        self._start = time.monotonic()
        self._alarm: threading.Timer | None = None

    def start(self) -> None:
        self._start = time.monotonic()
        if self.timebox:
            self._alarm = threading.Timer(self.timebox * 60, self._ring)
            self._alarm.daemon = True
            self._alarm.start()

    def _ring(self) -> None:
        notify("leet", f"⏰ Your {self.timebox:g}-minute timebox is up")

    def cancel(self) -> None:
        if self._alarm:
            self._alarm.cancel()

    def elapsed(self) -> float:
        return time.monotonic() - self._start

    @property
    def over(self) -> float:
        """Seconds past the timebox (0 if within it, or no timebox)."""
        if not self.timebox:
            return 0.0
        return max(0.0, self.elapsed() - self.timebox * 60)
