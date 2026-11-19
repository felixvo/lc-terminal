"""Local test runs for Python solutions (no LeetCode, no login).

Cases: the problem's examples (expected output parsed from the statement) plus your
`@tests` (optionally with `=> expected`). Each run happens in a child process with
a timeout; see local_runner.py.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import templates
from .languages import Lang

RUNNER = Path(__file__).with_name("local_runner.py")


class LocalRunError(RuntimeError):
    pass


@dataclass
class LocalCase:
    input: str
    expected: str | None
    source: str  # "example" | "custom" | "input"


@dataclass
class LocalResult:
    case: LocalCase
    output: str | None
    stdout: str
    error: str | None
    ms: float | None
    verdict: str  # pass | order | fail | none | error | timeout | skipped


@dataclass
class LocalReport:
    results: list[LocalResult] = field(default_factory=list)
    load_error: str | None = None
    timed_out: bool = False
    timeout: float = 10.0

    @property
    def checked(self) -> list[LocalResult]:
        return [r for r in self.results if r.case.expected is not None or r.verdict in ("error", "timeout")]

    @property
    def all_passed(self) -> bool:
        if self.load_error or self.timed_out or not self.results:
            return False
        if any(r.verdict in ("fail", "error", "timeout", "skipped") for r in self.results):
            return False
        return any(r.verdict in ("pass", "order") for r in self.results)


# ─── Cases ────────────────────────────────────────────────────────────────────

def build_cases(q: dict, code: str, lang: Lang, custom_input: str | None = None) -> tuple[list[LocalCase], list[str]]:
    """Returns (cases, leftover @tests lines that didn't make a full case)."""
    if custom_input is not None:
        return [LocalCase(custom_input.replace("\\n", "\n"), None, "input")], []
    examples = templates.example_cases(q)
    outputs = templates.example_outputs(q) or [None] * len(examples)
    cases = [LocalCase(inp, out, "example") for inp, out in zip(examples, outputs)]
    custom, leftover = templates.custom_cases(templates.parse_custom_tests(code, lang), templates.params_per_case(q))
    cases += [LocalCase(inp, exp, "custom") for inp, exp in custom]
    return cases, leftover


# ─── Comparing ────────────────────────────────────────────────────────────────

_BAD = object()


def _parse(text: str):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return _BAD


def _equal(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b  # 1 must not equal true
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-5, abs_tol=1e-5)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    return a == b


def _canonical(v):
    """Deep-sorted form, for "return the answer in any order" problems."""
    if isinstance(v, list):
        return sorted((_canonical(x) for x in v), key=lambda x: json.dumps(x, sort_keys=True))
    return v


def compare(output: str | None, expected: str | None) -> str:
    if expected is None:
        return "none"
    if output is None:
        return "fail"
    a, b = _parse(output), _parse(expected)
    if a is _BAD or b is _BAD:
        return "pass" if output.strip() == expected.strip() else "fail"
    if _equal(a, b):
        return "pass"
    if isinstance(a, list) and isinstance(b, list) and _equal(_canonical(a), _canonical(b)):
        return "order"
    return "fail"


# ─── Running ──────────────────────────────────────────────────────────────────

def run(q: dict, path: Path, cases: list[LocalCase], timeout: float = 10.0,
        python: str | None = None) -> LocalReport:
    try:
        meta = json.loads(q.get("metaData") or "{}")
    except ValueError:
        meta = {}
    if not meta.get("name") and not meta.get("classname"):
        raise LocalRunError("This problem has no function signature info, so it can't be tested locally.")

    with tempfile.TemporaryDirectory(prefix="leet-") as tmp:
        spec, res = Path(tmp) / "spec.json", Path(tmp) / "results.json"
        spec.write_text(json.dumps({
            "code_path": str(Path(path).resolve()),
            "meta": meta,
            "cases": [c.input for c in cases],
        }))
        proc, timed_out = None, False
        try:
            proc = subprocess.run([python or sys.executable, str(RUNNER), str(spec), str(res)],
                                  capture_output=True, text=True, timeout=timeout, cwd=Path(path).parent)
        except subprocess.TimeoutExpired:
            timed_out = True
        raw = json.loads(res.read_text()) if res.exists() else []

    if proc is not None and proc.returncode != 0 and not raw:
        raise LocalRunError((proc.stderr or "local runner crashed").strip()[-2000:])
    if raw and raw[0].get("load"):
        return LocalReport(load_error=raw[0]["error"], timeout=timeout)

    report = LocalReport(timed_out=timed_out, timeout=timeout)
    for i, case in enumerate(cases):
        if i < len(raw):
            r = raw[i]
            verdict = "error" if r["error"] else compare(r["output"], case.expected)
            report.results.append(LocalResult(case, r["output"], r["stdout"], r["error"], r["ms"], verdict))
        else:
            verdict = "timeout" if timed_out and i == len(raw) else "skipped"
            report.results.append(LocalResult(case, None, "", None, None, verdict))
    return report
