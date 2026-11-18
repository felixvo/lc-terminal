"""Progress tracking and spaced-repetition review schedule (~/.leet/history.json)."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config as cfg

# Days until the next review after each successful review.
INTERVALS = [1, 3, 7, 14, 30, 60]


def now() -> datetime:
    return datetime.now().astimezone()


def _stamp(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


class History:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else cfg.history_file()
        data = cfg.read_json(self.path, {})
        self.problems: dict[str, dict] = data.get("problems", {}) if isinstance(data, dict) else {}

    def save(self) -> None:
        cfg.write_json(self.path, {"version": 1, "problems": self.problems})

    # ── lookups ───────────────────────────────────────────────────────────────

    def get(self, slug: str) -> dict | None:
        return self.problems.get(slug)

    def is_solved(self, slug: str) -> bool:
        e = self.problems.get(slug)
        return bool(e and e.get("solved"))

    def solved_slugs(self) -> set[str]:
        return {s for s, e in self.problems.items() if e.get("solved")}

    def due(self, today: date | None = None) -> list[tuple[str, dict]]:
        today = today or now().date()
        items = [
            (s, e) for s, e in self.problems.items()
            if e.get("review") and date.fromisoformat(e["review"]["due"]) <= today
        ]
        return sorted(items, key=lambda it: it[1]["review"]["due"])

    def upcoming(self) -> tuple[str, dict] | None:
        items = [(s, e) for s, e in self.problems.items() if e.get("review")]
        return min(items, key=lambda it: it[1]["review"]["due"], default=None)

    # ── updates ───────────────────────────────────────────────────────────────

    def entry(self, slug: str, q: dict | None = None) -> dict:
        e = self.problems.setdefault(slug, {
            "title": slug, "id": None, "difficulty": None, "tags": [],
            "solved": False, "first_solved": None, "last_solved": None,
            "review": None, "attempts": [],
        })
        if q:
            e["title"] = q.get("title") or e["title"]
            e["id"] = q.get("questionFrontendId") or e.get("id")
            e["difficulty"] = q.get("difficulty") or e["difficulty"]
            e["tags"] = [t["name"] for t in q.get("topicTags") or []] or e["tags"]
        return e

    def record(self, slug: str, q: dict | None, mode: str, result: dict, lang: str,
               elapsed: float | None = None, at: datetime | None = None) -> dict:
        """Log a run or submit. An accepted submit marks the problem solved and reschedules review."""
        at = at or now()
        e = self.entry(slug, q)
        status = result.get("status_msg") or "Unknown"
        attempt = {
            "at": _stamp(at), "mode": mode, "status": status, "lang": lang,
            "passed": result.get("total_correct"), "total": result.get("total_testcases"),
        }
        if mode == "submit":
            attempt["runtime"] = result.get("status_runtime")
            attempt["memory"] = result.get("status_memory")
        if elapsed is not None:
            attempt["elapsed"] = round(elapsed)

        clean = self._no_failed_submit_since_accept(e)
        e["attempts"].append(attempt)
        if mode == "submit" and status == "Accepted":
            self._on_accepted(e, at, clean)
        return e

    def mark(self, slug: str, q: dict | None, solved: bool = True, at: datetime | None = None) -> dict:
        """Manually mark a problem solved (e.g. solved outside this tool) or unsolved."""
        at = at or now()
        e = self.entry(slug, q)
        if solved:
            e["solved"] = True
            e["first_solved"] = e["first_solved"] or _stamp(at)
            e["last_solved"] = e["last_solved"] or _stamp(at)
            if not e.get("review"):
                e["review"] = {"level": 0, "due": (at.date() + timedelta(days=INTERVALS[0])).isoformat()}
        else:
            e["solved"] = False
            e["review"] = None
        return e

    @staticmethod
    def _no_failed_submit_since_accept(e: dict) -> bool:
        for a in reversed(e["attempts"]):
            if a["mode"] == "submit":
                return a["status"] == "Accepted"
        return True

    @staticmethod
    def _on_accepted(e: dict, at: datetime, clean: bool) -> None:
        today = at.date()
        first = not e["solved"]
        e["solved"] = True
        e["first_solved"] = e["first_solved"] or _stamp(at)
        e["last_solved"] = _stamp(at)

        review = e.get("review")
        if first or not review or not clean:
            level = 0  # new, or you struggled: start the ladder again
        elif date.fromisoformat(review["due"]) > today:
            return  # solved again before it was due: keep the schedule
        else:
            level = min(review["level"] + 1, len(INTERVALS) - 1)
        e["review"] = {"level": level, "due": (today + timedelta(days=INTERVALS[level])).isoformat()}

    # ── stats ─────────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        solved = [e for e in self.problems.values() if e.get("solved")]
        submits = [a for e in self.problems.values() for a in e["attempts"] if a["mode"] == "submit"]
        times: dict[str, list[int]] = defaultdict(list)
        for e in solved:
            for a in e["attempts"]:
                if a["mode"] == "submit" and a["status"] == "Accepted" and a.get("elapsed"):
                    times[e.get("difficulty") or "?"].append(a["elapsed"])
        return {
            "solved": len(solved),
            "by_difficulty": Counter(e.get("difficulty") or "?" for e in solved),
            "tags": Counter(t for e in solved for t in e.get("tags", [])),
            "submits": len(submits),
            "accepted": sum(a["status"] == "Accepted" for a in submits),
            "avg_time": {d: sum(v) / len(v) for d, v in times.items()},
        }

    def streak(self, today: date | None = None) -> int:
        """Consecutive days (ending today, or yesterday) with at least one accepted submit."""
        today = today or now().date()
        days = {
            datetime.fromisoformat(a["at"]).date()
            for e in self.problems.values() for a in e["attempts"]
            if a["mode"] == "submit" and a["status"] == "Accepted"
        }
        day = today if today in days else today - timedelta(days=1)
        count = 0
        while day in days:
            count += 1
            day -= timedelta(days=1)
        return count
