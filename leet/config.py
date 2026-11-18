"""Settings and on-disk locations.

Everything lives under ~/.leet (override with the LEET_HOME environment variable):

  config.json   cookies + preferences (chmod 600)
  history.json  attempts, solved problems, review schedule
  cache/        fetched problems, one JSON file per slug
  lists/        your own question lists (these shadow the bundled ones)
  solutions/    default solutions folder (change with `lc config --solutions-dir`)
"""
from __future__ import annotations

import json
import os
import shlex
import tempfile
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "lang": "python3",
    "default_list": "questions",
    "solutions_dir": None,
    "editor": None,
}


def home() -> Path:
    return Path(os.environ.get("LEET_HOME") or Path.home() / ".leet").expanduser()


def config_file() -> Path:
    return home() / "config.json"


def history_file() -> Path:
    return home() / "history.json"


def cache_dir() -> Path:
    return home() / "cache"


def lists_dir() -> Path:
    return home() / "lists"


# ─── JSON helpers ─────────────────────────────────────────────────────────────

def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def write_json(path: Path, data: Any, private: bool = False) -> None:
    """Write atomically, so a crash never leaves a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.chmod(tmp, 0o600 if private else 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# ─── Config ───────────────────────────────────────────────────────────────────

def load() -> dict:
    data = read_json(config_file(), {})
    return data if isinstance(data, dict) else {}


def save(data: dict) -> None:
    write_json(config_file(), data, private=True)  # contains session token


def get(key: str, default: Any = None) -> Any:
    value = load().get(key)
    if value is not None:
        return value
    return default if default is not None else DEFAULTS.get(key)


def update(**values: Any) -> None:
    data = load()
    data.update(values)
    save(data)


def has_auth() -> bool:
    return bool(get("session") and get("csrf"))


def solutions_dir() -> Path:
    custom = get("solutions_dir")
    return Path(custom).expanduser() if custom else home() / "solutions"


def editor_command() -> list[str]:
    raw = get("editor") or os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vim"
    return shlex.split(raw)
