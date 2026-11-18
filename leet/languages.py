"""Languages LeetCode accepts, with file extension, comment prefix and highlighter."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Lang:
    slug: str      # LeetCode's langSlug
    name: str
    ext: str
    comment: str
    lexer: str     # Pygments lexer name, for syntax highlighting


_ALL = [
    Lang("python3", "Python 3", ".py", "#", "python"),
    Lang("cpp", "C++", ".cpp", "//", "cpp"),
    Lang("java", "Java", ".java", "//", "java"),
    Lang("javascript", "JavaScript", ".js", "//", "javascript"),
    Lang("typescript", "TypeScript", ".ts", "//", "typescript"),
    Lang("golang", "Go", ".go", "//", "go"),
    Lang("rust", "Rust", ".rs", "//", "rust"),
    Lang("c", "C", ".c", "//", "c"),
    Lang("csharp", "C#", ".cs", "//", "csharp"),
    Lang("kotlin", "Kotlin", ".kt", "//", "kotlin"),
    Lang("swift", "Swift", ".swift", "//", "swift"),
    Lang("ruby", "Ruby", ".rb", "#", "ruby"),
    Lang("scala", "Scala", ".scala", "//", "scala"),
    Lang("php", "PHP", ".php", "//", "php"),
]

LANGS: dict[str, Lang] = {lang.slug: lang for lang in _ALL}
_BY_EXT: dict[str, Lang] = {lang.ext: lang for lang in _ALL}
_ALIASES = {
    "python": "python3", "py": "python3",
    "c++": "cpp", "go": "golang", "js": "javascript", "ts": "typescript",
    "rs": "rust", "cs": "csharp", "c#": "csharp", "kt": "kotlin", "rb": "ruby",
}


def resolve(name: str) -> Lang:
    key = name.strip().lower()
    key = _ALIASES.get(key, key)
    if key not in LANGS:
        raise ValueError(f"Unknown language '{name}'. Choose from: {', '.join(LANGS)}")
    return LANGS[key]


def from_path(path: str | Path) -> Lang | None:
    return _BY_EXT.get(Path(path).suffix.lower())
