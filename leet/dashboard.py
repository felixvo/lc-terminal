"""Full-screen dashboard: browse a list with your progress, pick a problem to solve.

Keys: ^N/^P ↑/↓ j/k move · PgUp/PgDn page · g/G top/bottom · enter solve ·
o open in browser · f status filter · d difficulty filter · / search · r random · q quit
"""
from __future__ import annotations

import random
import sys
import threading
import time
import webbrowser
from datetime import date
from pathlib import Path

from rich import box
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import lists
from .api import LeetCodeClient
from .display import DIFFICULTY_COLORS, bar, console
from .history import History, now

try:
    import termios
    import tty
except ImportError:  # pragma: no cover
    termios = tty = None  # type: ignore[assignment]

FILTERS = ["all", "unsolved", "solved", "due"]
DIFFICULTIES = ["all", "Easy", "Medium", "Hard"]


def pretty_slug(slug: str) -> str:
    return slug.replace("-", " ").title()


def _meta(q: dict) -> dict:
    return {"title": q.get("title"), "difficulty": q.get("difficulty"), "id": q.get("questionFrontendId")}


class DashboardState:
    """Everything the dashboard shows, plus key handling. No terminal I/O here."""

    def __init__(self, name: str, items: list[tuple[str | None, str]], history: History,
                 meta: dict[str, dict], today: date | None = None):
        self.name = name
        self.items = items
        self.history = history
        self.meta = meta
        self.today = today or now().date()
        self.filter = 0
        self.difficulty = 0
        self.query = ""
        self.searching = False
        self.cursor = 0   # index into visible()
        self.top = 0      # first table row on screen
        self.message = ""

    # ── data ──────────────────────────────────────────────────────────────────

    def info(self, slug: str) -> dict:
        e = self.history.get(slug) or {}
        m = self.meta.get(slug) or {}
        title = m.get("title") or (e.get("title") if e.get("title") != slug else None)
        review = e.get("review")
        return {
            "slug": slug,
            "title": title or pretty_slug(slug),
            "known": bool(title),
            "id": m.get("id") or e.get("id"),
            "difficulty": m.get("difficulty") or e.get("difficulty"),
            "solved": bool(e.get("solved")),
            "submits": sum(a["mode"] == "submit" for a in e.get("attempts", [])),
            "attempted": bool(e.get("attempts")),
            "review_due": review["due"] if review else None,
            "due": bool(review and date.fromisoformat(review["due"]) <= self.today),
        }

    def _matches(self, slug: str) -> bool:
        i = self.info(slug)
        status = FILTERS[self.filter]
        if status == "unsolved" and i["solved"]:
            return False
        if status == "solved" and not i["solved"]:
            return False
        if status == "due" and not i["due"]:
            return False
        if self.difficulty and i["difficulty"] != DIFFICULTIES[self.difficulty]:
            return False
        q = self.query.lower().strip()
        return not q or q in i["title"].lower() or q in slug

    def visible(self) -> list[tuple[str | None, str]]:
        return [(section, slug) for section, slug in self.items if self._matches(slug)]

    def rows(self) -> list[tuple[str, str | None]]:
        """Table rows: ("section", name) headings and ("problem", slug) entries."""
        out: list[tuple[str, str | None]] = []
        current = object()
        for section, slug in self.visible():
            if section != current and section:
                out.append(("section", section))
            current = section
            out.append(("problem", slug))
        return out

    def selected(self) -> str | None:
        vis = self.visible()
        return vis[self.cursor][1] if vis else None

    def totals(self) -> dict:
        infos = [self.info(slug) for _, slug in self.items]
        by_diff = {d: [0, 0] for d in DIFFICULTIES[1:]}
        for i in infos:
            if i["difficulty"] in by_diff:
                by_diff[i["difficulty"]][1] += 1
                by_diff[i["difficulty"]][0] += i["solved"]
        return {
            "total": len(infos),
            "solved": sum(i["solved"] for i in infos),
            "due": sum(i["due"] for i in infos),
            "by_diff": by_diff,
        }

    # ── keys ──────────────────────────────────────────────────────────────────

    def _keep_selection(self, slug: str | None) -> None:
        vis = [s for _, s in self.visible()]
        self.cursor = vis.index(slug) if slug in vis else min(self.cursor, max(len(vis) - 1, 0))

    def handle(self, key: str, page: int = 10) -> tuple[str, str] | None:
        """Apply a key. Returns ("solve"|"open", slug), ("quit", ""), or None."""
        self.message = ""
        count = len(self.visible())
        before = self.selected()

        if key == "interrupt":
            raise KeyboardInterrupt
        if key in ("down", "up", "pgdn", "pgup"):
            step = {"down": 1, "up": -1, "pgdn": page, "pgup": -page}[key]
            if count:
                if key in ("down", "up"):
                    self.cursor = (self.cursor + step) % count  # wrap
                else:
                    self.cursor = max(0, min(count - 1, self.cursor + step))
            return None

        if self.searching:
            if key == "enter":
                self.searching = False
            elif key == "esc":
                self.searching, self.query = False, ""
            elif key == "backspace":
                self.query = self.query[:-1]
            elif len(key) == 1 and key.isprintable():
                self.query += key
            self._keep_selection(before)
            return None

        if key in ("j", "k"):
            return self.handle("down" if key == "j" else "up", page)
        if key in ("q", "cancel"):
            return ("quit", "")
        if key in ("g", "home"):
            self.cursor = 0
        elif key in ("G", "end"):
            self.cursor = max(count - 1, 0)
        elif key == "enter" and before:
            return ("solve", before)
        elif key == "o" and before:
            return ("open", before)
        elif key == "f":
            self.filter = (self.filter + 1) % len(FILTERS)
            self._keep_selection(before)
        elif key == "d":
            self.difficulty = (self.difficulty + 1) % len(DIFFICULTIES)
            self._keep_selection(before)
        elif key == "/":
            self.searching = True
        elif key == "esc" and self.query:
            self.query = ""
            self._keep_selection(before)
        elif key == "r":
            pool = [i for i, (_, s) in enumerate(self.visible()) if not self.info(s)["solved"]]
            if pool:
                self.cursor = random.choice(pool)
            else:
                self.message = "Nothing unsolved in this view."
        return None


# ─── Rendering ────────────────────────────────────────────────────────────────

def render(state: DashboardState, height: int, fetch: tuple[int, int] | None = None):
    t = state.totals()

    head = Text()
    head.append(state.name, style="bold")
    head.append(f"   {t['solved']}/{t['total']} solved  ")
    head.append_text(bar(t["solved"], t["total"], 30))
    pct = 100 * t["solved"] / t["total"] if t["total"] else 0
    head.append(f"  {pct:.0f}%\n", style="dim")
    for d, (done, total) in t["by_diff"].items():
        head.append(f"{d} {done}/{total}", style=DIFFICULTY_COLORS[d])
        head.append("   ")
    head.append(f"↻ {t['due']} due", style="magenta" if t["due"] else "dim")
    streak = state.history.streak(state.today)
    if streak:
        head.append(f"   🔥 {streak}-day streak", style="dim")
    if fetch and fetch[0] < fetch[1]:
        head.append(f"   fetching details {fetch[0]}/{fetch[1]}…", style="dim italic")
    header = Panel(head, box=box.ROUNDED, border_style="blue", padding=(0, 1))

    rows = state.rows()
    body_height = max(3, height - 4 - 2 - 2)  # header panel, table header, footer
    cursor_slug = state.selected()
    pos = next((i for i, (kind, v) in enumerate(rows) if kind == "problem" and v == cursor_slug), 0)
    want = pos - 1 if pos and rows[pos - 1][0] == "section" else pos  # keep heading in view
    if want < state.top:
        state.top = want
    elif pos >= state.top + body_height:
        state.top = pos - body_height + 1
    state.top = max(0, min(state.top, max(len(rows) - body_height, 0)))

    table = Table(box=box.SIMPLE_HEAD, expand=True, pad_edge=False, show_edge=False)
    table.add_column("", width=1, no_wrap=True)
    table.add_column("#", justify="right", width=5, style="dim", no_wrap=True)
    table.add_column("Problem", ratio=1, no_wrap=True, overflow="ellipsis")
    table.add_column("Difficulty", width=10, no_wrap=True)
    table.add_column("Submits", justify="right", width=7, style="dim", no_wrap=True)
    table.add_column("Review", width=12, no_wrap=True)

    section_counts: dict[str, list[int]] = {}
    for section, slug in state.items:
        if section:
            c = section_counts.setdefault(section, [0, 0])
            c[1] += 1
            c[0] += state.info(slug)["solved"]

    for kind, value in rows[state.top:state.top + body_height]:
        if kind == "section":
            done, total = section_counts.get(value, [0, 0])
            table.add_row("", "", Text(value, style="bold blue"), Text(f"{done}/{total}", style="dim"), "", "")
            continue
        i = state.info(value)
        if i["solved"]:
            mark = Text("✓", style="bright_green")
        elif i["attempted"]:
            mark = Text("◐", style="yellow")
        else:
            mark = Text("·", style="dim")
        title = Text(i["title"], style="" if i["known"] else "dim italic")
        diff = Text(i["difficulty"] or "", style=DIFFICULTY_COLORS.get(i["difficulty"] or "", "dim"))
        if i["due"]:
            review = Text("due now", style="magenta")
        else:
            review = Text(i["review_due"] or "", style="dim")
        table.add_row(mark, str(i["id"] or ""), title, diff, str(i["submits"] or ""), review,
                      style="reverse" if value == cursor_slug else None)

    if not rows:
        table.add_row("", "", Text("No problems match.", style="dim"), "", "", "")

    vis = len(state.visible())
    filters = Text()
    filters.append(f" {state.cursor + 1 if vis else 0}/{vis} ", style="bold")
    filters.append(f" {FILTERS[state.filter]}", style="cyan" if state.filter else "dim")
    level = DIFFICULTIES[state.difficulty] if state.difficulty else "any difficulty"
    filters.append(f" · {level} ", style="cyan" if state.difficulty else "dim")
    if state.searching:
        filters.append(f" /{state.query}▌", style="bold yellow")
        filters.append("  enter: done · esc: clear", style="dim")
    else:
        if state.query:
            filters.append(f" search: {state.query} ", style="yellow")
        filters.append("  ^N/^P move · ⏎ solve · o open · f filter · d diff · / search · r random · q quit",
                       style="dim")
    if state.message:
        filters.append(f"  {state.message}", style="yellow")
    filters.no_wrap = True
    filters.overflow = "ellipsis"
    return Group(header, table, filters)


# ─── Terminal loop ────────────────────────────────────────────────────────────

class Fetcher(threading.Thread):
    """Fetches problems missing from the cache so titles/difficulties fill in live."""

    def __init__(self, slugs: list[str], meta: dict[str, dict]):
        super().__init__(daemon=True)
        self.slugs, self.meta = slugs, meta
        self.done = 0
        self.stop_event = threading.Event()
        self.client = LeetCodeClient.from_config()  # its own HTTP session

    def run(self) -> None:
        for slug in self.slugs:
            if self.stop_event.is_set():
                return
            try:
                self.meta[slug] = _meta(self.client.get_question(slug))
            except Exception:
                pass
            self.done += 1
            time.sleep(0.05)


class Dashboard:
    def __init__(self, list_path: Path):
        self.path = list_path
        self.items = lists.load_sections(list_path)
        client = LeetCodeClient.from_config()
        self.meta: dict[str, dict] = {}
        missing = []
        for _, slug in self.items:
            q = client.cached_question(slug)
            if q:
                self.meta[slug] = _meta(q)
            else:
                missing.append(slug)
        self.fetcher = Fetcher(missing, self.meta) if missing else None
        if self.fetcher:
            self.fetcher.start()
        self.state = DashboardState(list_path.stem, self.items, History(), self.meta)

    def reload(self) -> None:
        """Pick up history changes (after solving), keeping cursor and filters."""
        self.state.history = History()
        self.state.today = now().date()
        self.state._keep_selection(self.state.selected())

    def stop(self) -> None:
        if self.fetcher:
            self.fetcher.stop_event.set()

    def _fetch_progress(self) -> tuple[int, int] | None:
        return (self.fetcher.done, len(self.fetcher.slugs)) if self.fetcher else None

    def run(self) -> str | None:
        """Show the dashboard until the user picks a problem (returns its slug) or quits."""
        from .menu import read_key

        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            with Live(console=console, screen=True, auto_refresh=False) as live:
                last = None
                while True:
                    size = console.size
                    snapshot = (size, self._fetch_progress())
                    if snapshot != last:
                        live.update(render(self.state, size.height, self._fetch_progress()), refresh=True)
                        last = snapshot
                    key = read_key(fd, timeout=0.3)
                    if key is None:
                        continue
                    action = self.state.handle(key, page=max(1, size.height - 10))
                    if action and action[0] == "open":
                        webbrowser.open(f"https://leetcode.com/problems/{action[1]}/")
                        self.state.message = "Opened in your browser."
                    elif action and action[0] == "solve":
                        return action[1]
                    elif action and action[0] == "quit":
                        return None
                    last = None  # redraw after any key
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
