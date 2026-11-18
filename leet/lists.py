"""Question lists: bundled ones in leet/data, your own in ~/.leet/lists.

A list is a text file with one URL or slug per line. `#` starts a comment;
comments containing `──` are treated as section headings (see neetcode150.txt).
"""
from __future__ import annotations

from pathlib import Path

from . import config as cfg
from .util import slug_from_url

BUNDLED_DIR = Path(__file__).parent / "data"


def available() -> dict[str, Path]:
    """All list names → files. Your own lists override bundled ones of the same name."""
    found: dict[str, Path] = {}
    for d in (BUNDLED_DIR, cfg.lists_dir()):
        if d.is_dir():
            for f in sorted(d.glob("*.txt")):
                found[f.stem] = f
    return found


def resolve(name_or_path: str) -> Path:
    p = Path(name_or_path).expanduser()
    if p.is_file():
        return p
    for cand in (
        cfg.lists_dir() / name_or_path,
        cfg.lists_dir() / f"{name_or_path}.txt",
        BUNDLED_DIR / name_or_path,
        BUNDLED_DIR / f"{name_or_path}.txt",
    ):
        if cand.is_file():
            return cand
    names = ", ".join(available()) or "none"
    raise FileNotFoundError(f"No list named '{name_or_path}'. Available: {names}")


def load_sections(path: Path) -> list[tuple[str | None, str]]:
    """(section heading or None, slug) for each problem, de-duplicated, in file order."""
    seen: set[str] = set()
    out: list[tuple[str | None, str]] = []
    section: str | None = None
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if "──" in line:
                section = line.strip("#─ ").strip() or None
            continue
        slug = slug_from_url(line)
        if slug and slug not in seen:
            seen.add(slug)
            out.append((section, slug))
    return out


def load(path: Path) -> list[str]:
    return [slug for _, slug in load_sections(path)]


def is_bundled(path: Path) -> bool:
    return Path(path).resolve().parent == BUNDLED_DIR.resolve()


def add(name: str, slug: str) -> tuple[Path, bool]:
    """Append a problem to a list. Returns (file written, whether it was added).

    Bundled lists are copied to ~/.leet/lists first, so the package stays untouched.
    Unknown names create a new list in ~/.leet/lists.
    """
    try:
        path = resolve(name)
    except FileNotFoundError:
        if "/" in name:
            path = Path(name).expanduser()
        else:
            path = cfg.lists_dir() / (name if name.endswith(".txt") else f"{name}.txt")

    if path.exists() and slug in load(path):
        return path, False

    if is_bundled(path):
        user_copy = cfg.lists_dir() / path.name
        user_copy.parent.mkdir(parents=True, exist_ok=True)
        user_copy.write_text(path.read_text())
        path = user_copy

    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text() if path.exists() else ""
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text + f"https://leetcode.com/problems/{slug}/\n")
    return path, True
