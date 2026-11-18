"""Inline selection menu: Ctrl+N/Ctrl+P (or ↑/↓, j/k) to move, Enter to pick.

Shortcuts: a digit picks that option directly; options can also have their own
key (e.g. `r` for run). Esc or `q` cancels (returns None), Ctrl+C interrupts.
Falls back to a typed prompt when stdin/stdout isn't a terminal.
"""
from __future__ import annotations

import os
import select as _select
import sys

from rich.markup import escape
from rich.prompt import IntPrompt, Prompt
from rich.text import Text

from .display import console

try:  # POSIX only; elsewhere we use the fallback prompt
    import termios
    import tty
except ImportError:  # pragma: no cover
    termios = tty = None  # type: ignore[assignment]

# Control keys get names; printable keys come through as themselves (so search can type "j").
KEYS = {
    b"\x0e": "down",   # Ctrl+N
    b"\x10": "up",     # Ctrl+P
    b"\r": "enter",
    b"\n": "enter",
    b"\x7f": "backspace",
    b"\x08": "backspace",
    b"\x03": "interrupt",  # Ctrl+C (in case ISIG is off)
    b"\x04": "cancel",     # Ctrl+D
}
ESCAPES = {
    b"[A": "up", b"[B": "down", b"OA": "up", b"OB": "down",
    b"[5~": "pgup", b"[6~": "pgdn",
    b"[H": "home", b"[F": "end", b"OH": "home", b"OF": "end", b"[1~": "home", b"[4~": "end",
}
VIM_MOVES = {"j": "down", "k": "up"}


class Menu:
    """Key handling, separate from the terminal so it can be tested."""

    def __init__(self, count: int, default: int = 0, keys: list[str] | None = None):
        self.count = count
        self.index = default if 0 <= default < count else 0
        self.keys = [k.lower() for k in keys] if keys else []

    def handle(self, key: str) -> tuple[bool, int | None]:
        """Returns (done, chosen index or None if cancelled)."""
        if key in VIM_MOVES and key not in self.keys:
            key = VIM_MOVES[key]
        if key == "down":
            self.index = (self.index + 1) % self.count
        elif key == "up":
            self.index = (self.index - 1) % self.count
        elif key == "enter":
            return True, self.index
        elif key in ("esc", "cancel") or (key == "q" and "q" not in self.keys):
            return True, None
        elif key == "interrupt":
            raise KeyboardInterrupt
        elif key.lower() in self.keys:
            self.index = self.keys.index(key.lower())
            return True, self.index
        elif key.isdigit() and 1 <= int(key) <= min(self.count, 9):
            self.index = int(key) - 1
            return True, self.index
        return False, None


def interactive() -> bool:
    return termios is not None and sys.stdin.isatty() and sys.stdout.isatty() and console.is_terminal

def read_key(fd: int, timeout: float | None = None) -> str | None:
    """Read one keypress (stdin must be in cbreak mode). None if `timeout` passes first."""
    ready, _, _ = _select.select([fd], [], [], timeout)
    if not ready:
        return None
    ch = os.read(fd, 1)
    if ch == b"\x1b":
        ready, _, _ = _select.select([fd], [], [], 0.05)
        if not ready:
            return "esc"
        return ESCAPES.get(os.read(fd, 8), "")
    return KEYS.get(ch, ch.decode(errors="ignore"))

def choose(title: str, labels: list[str], *, names: list[str] | None = None,
           default: int = 0, keys: list[str] | None = None) -> int | None:
    """Show a menu and return the chosen index, or None if cancelled.

    labels: Rich markup shown per option.  names: plain words for the typed
    fallback prompt (else it asks for a number).  keys: one shortcut per option.
    """
    if not labels:
        return None
    if not interactive():
        return _fallback(title, labels, names, default)

    menu = Menu(len(labels), default, keys)
    height = max(1, min(len(labels), console.height - 4))
    out = sys.stdout
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    console.print(f"[bold]{title}[/bold] [dim]^N/^P or ↑/↓ to move · enter to select · esc to cancel[/dim]",
                  no_wrap=True, overflow="ellipsis")  # must stay one line: we move the cursor over it
    rendered = 0
    try:
        tty.setcbreak(fd)
        out.write("\x1b[?25l")  # hide cursor
        while True:
            rendered = _render(out, labels, menu.index, height, rendered)
            done, chosen = menu.handle(read_key(fd) or "")
            if done:
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        # collapse the menu (and its title) into a single summary line
        out.write(f"\x1b[{rendered + 1}A\r\x1b[J\x1b[?25h")
        out.flush()

    picked = Text.from_markup(labels[chosen]).plain.split("  ")[0] if chosen is not None else "cancelled"
    console.print(f"[bold]{title}[/bold] [cyan]› {escape(picked)}[/cyan]")
    return chosen

def _render(out, labels: list[str], index: int, height: int, previous: int) -> int:
    if previous:
        out.write(f"\x1b[{previous}A")
    top = min(max(0, index - height + 1), len(labels) - height)
    top = max(0, min(top, index))
    lines = 0
    for i in range(top, top + height):
        out.write("\r\x1b[2K")
        out.flush()
        if i == index:
            console.print(Text("❯ ", style="bold cyan") + Text.from_markup(labels[i], style="bold"),
                          no_wrap=True, overflow="ellipsis")
        else:
            console.print(Text("  ") + Text.from_markup(labels[i]), no_wrap=True, overflow="ellipsis")
        lines += 1
    out.write("\r\x1b[2K")
    out.flush()
    more = f"{index + 1}/{len(labels)}" if len(labels) > height else ""
    console.print(f"[dim]{more}[/dim]")
    return lines + 1

def _fallback(title: str, labels: list[str], names: list[str] | None, default: int) -> int | None:
    if names:
        answer = Prompt.ask(title, choices=names, default=names[default])
        return names.index(answer)
    for i, label in enumerate(labels, 1):
        console.print(f"  [dim]{i}.[/dim] {label}")
    pick = IntPrompt.ask(title, default=default + 1)
    return pick - 1 if 1 <= pick <= len(labels) else None
