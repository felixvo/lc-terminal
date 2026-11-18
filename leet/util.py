"""Small pure helpers."""
from __future__ import annotations


def slug_from_url(url_or_slug: str) -> str:
    """Accept a full LeetCode URL (any sub-page, query string) or a bare slug."""
    s = url_or_slug.strip()
    if "/problems/" in s:
        s = s.split("/problems/", 1)[1]
    return s.split("/")[0].split("?")[0].split("#")[0].strip().lower()


def fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"
