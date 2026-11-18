"""Solution file templates, custom test blocks and test-case grouping."""
from __future__ import annotations

import html
import json
import re
import textwrap

from .languages import Lang

TESTS_START = "@tests"
TESTS_END = "@end"


def html_to_text(content: str | None) -> str:
    """Problem HTML → plain text for the comment header of a solution file."""
    s = content or ""
    s = re.sub(r"<sup>(.*?)</sup>", r"^\1", s)
    s = re.sub(r"</li>\s*", "\n", s)  # keep list items on consecutive lines
    s = re.sub(r"<br\s*/?>|</p>|</pre>", "\n", s)
    s = re.sub(r"<li[^>]*>", "- ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = "\n".join(line.strip() for line in s.splitlines())
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def starter_code(q: dict, lang: Lang) -> str | None:
    for snippet in q.get("codeSnippets") or []:
        if snippet.get("langSlug") == lang.slug:
            return snippet["code"]
    return None


def build_template(q: dict, code: str, lang: Lang) -> str:
    c = lang.comment
    out = [
        f"{c} {q['questionFrontendId']}. {q['title']}",
        f"{c} Difficulty: {q['difficulty']}",
        f"{c} https://leetcode.com/problems/{q['slug']}/",
        c,
    ]
    for para in html_to_text(q.get("content")).split("\n"):
        if not para.strip():
            out.append(c)
            continue
        for line in textwrap.wrap(para, 77, break_long_words=False, break_on_hyphens=False):
            out.append(f"{c} {line}")
    out += [
        c,
        f"{c} {TESTS_START} — extra inputs for `lc run`: one parameter per line, as in LeetCode's testcase box",
        f"{c} {TESTS_END}",
        "",
        code.rstrip() + "\n",
    ]
    return "\n".join(out)


def parse_custom_tests(source: str, lang: Lang) -> list[str]:
    """Return the input lines between `@tests` and `@end` comment lines."""
    lines: list[str] = []
    inside = False
    for raw in source.splitlines():
        s = raw.strip()
        if not s.startswith(lang.comment):
            if inside:
                break
            continue
        body = s[len(lang.comment):].strip()
        if not inside:
            inside = body.startswith(TESTS_START)
            continue
        if body.startswith(TESTS_END):
            break
        if body:
            lines.append(body)
    return lines


def params_per_case(q: dict) -> int:
    """How many input lines make up one test case."""
    try:
        meta = json.loads(q.get("metaData") or "{}")
    except (TypeError, ValueError):
        meta = {}
    if meta.get("systemdesign") or meta.get("classname"):
        return 2  # design problems: list of method calls + list of arguments
    return max(len(meta.get("params") or []), 1)


def group_cases(lines: list[str], per: int) -> tuple[list[str], list[str]]:
    """Split input lines into cases of `per` lines. Returns (cases, leftover lines)."""
    n = len(lines) - len(lines) % per
    cases = ["\n".join(lines[i:i + per]) for i in range(0, n, per)]
    return cases, lines[n:]


def example_cases(q: dict) -> list[str]:
    cases = list(q.get("exampleTestcaseList") or [])
    if not cases and q.get("sampleTestCase"):
        cases = [q["sampleTestCase"]]
    return cases
