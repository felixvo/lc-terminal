"""Terminal rendering with Rich."""
from __future__ import annotations

import html
import re
import time
from contextlib import contextmanager
from typing import Iterator

from rich import box
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from .languages import Lang
from .util import fmt_duration

console = Console()

DIFFICULTY_COLORS = {"Easy": "bright_green", "Medium": "yellow", "Hard": "bright_red"}


def diff_text(difficulty: str | None) -> Text:
    return Text(difficulty or "", style=DIFFICULTY_COLORS.get(difficulty or "", "dim"))


# ─── HTML → Markdown ──────────────────────────────────────────────────────────

def html_to_md(content: str | None) -> str:
    """Best-effort LeetCode HTML → Markdown without extra dependencies."""
    if not content:
        return ""

    # Pull <pre> blocks out first so their inner tags become plain text, not markdown.
    blocks: list[str] = []

    def stash(m: re.Match) -> str:
        inner = re.sub(r"<[^>]+>", "", m.group(1))
        blocks.append(html.unescape(inner).strip("\n"))
        return f"\n\x00{len(blocks) - 1}\x00\n"

    attrs = r"(?:\s[^>]*)?"
    text = re.sub(r"<pre[^>]*>(.*?)</pre>", stash, content, flags=re.DOTALL)
    text = re.sub(r"<sup>(.*?)</sup>", r"^\1", text)
    # Headings like <p><strong class="example">Example 1:</strong></p> (before bold!)
    text = re.sub(rf"<p>\s*<strong{attrs}>([^<]*)</strong>\s*</p>", r"\n### \1\n", text)
    text = re.sub(rf"<code{attrs}>(.*?)</code>", r"`\1`", text, flags=re.DOTALL)
    text = re.sub(rf"<(strong|b){attrs}>(.*?)</\1>", r"**\2**", text, flags=re.DOTALL)
    text = re.sub(rf"<(em|i){attrs}>(.*?)</\1>", r"*\2*", text, flags=re.DOTALL)
    text = re.sub(r'<img[^>]*src="([^"]+)"[^>]*>', r"[image](\1)", text)
    text = re.sub(r"</?p[^>]*>", "\n", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(rf"<li{attrs}>(.*?)</li>", r"- \1", text, flags=re.DOTALL)
    text = re.sub(r"</?[uo]l[^>]*>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    # Source indentation (e.g. tab-indented <li>) would turn into Markdown code blocks.
    text = "\n".join(line.strip() for line in text.splitlines())
    text = re.sub(r"\x00(\d+)\x00", lambda m: "```\n" + blocks[int(m.group(1))] + "\n```", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ─── Problems ─────────────────────────────────────────────────────────────────

def show_question(q: dict, entry: dict | None = None) -> None:
    difficulty = q.get("difficulty", "?")
    color = DIFFICULTY_COLORS.get(difficulty, "white")
    tags = " · ".join(t["name"] for t in q.get("topicTags") or [])

    title = Text()
    title.append(f"#{q['questionFrontendId']}  ", style="bold dim")
    title.append(q["title"], style="bold white")
    title.append(f"  [{difficulty}]", style=f"bold {color}")
    if tags:
        title.append(f"\n{tags}", style="dim")
    if entry and entry.get("solved"):
        review = entry.get("review")
        title.append("\n✓ Solved", style="bright_green")
        if review:
            title.append(f" · next review {review['due']}", style="dim")
    elif entry and entry.get("attempts"):
        title.append(f"\n◐ Attempted {len(entry['attempts'])}×, not solved yet", style="yellow")

    console.print(Panel(title, border_style="blue", padding=(0, 1)))

    body = html_to_md(q.get("content"))
    if body:
        console.print(Markdown(body))
    else:
        console.print("[dim]Content not available (premium-only problem).[/dim]")

    hints = q.get("hints") or []
    if hints:
        console.print(f"\n[dim]💡 {len(hints)} hint(s) available — use --hints to show[/dim]")


def show_hints(q: dict) -> None:
    hints = q.get("hints") or []
    if not hints:
        console.print("[dim]No hints available.[/dim]")
        return
    for i, h in enumerate(hints, 1):
        console.print(Panel(Markdown(html_to_md(h)), title=f"Hint {i}", border_style="yellow"))


def show_code(code: str, lang: Lang, title: str = "Starter Code") -> None:
    console.print(Panel(Syntax(code, lang.lexer, theme="monokai"), title=title, border_style="dim"))


@contextmanager
def waiting(label: str) -> Iterator:
    """Spinner with elapsed seconds. Yields a tick(elapsed) callback for pollers."""
    with console.status(f"{label}…") as status:
        start = time.monotonic()

        def tick(elapsed: float | None = None) -> None:
            secs = elapsed if elapsed is not None else time.monotonic() - start
            status.update(f"{label}… [dim]{secs:.0f}s[/dim]")

        yield tick


# ─── Results ──────────────────────────────────────────────────────────────────

def _show_errors(result: dict) -> bool:
    compile_err = result.get("full_compile_error") or result.get("compile_error")
    if compile_err:
        console.print(Panel(compile_err, title="[red]Compile Error[/red]", border_style="red"))
        return True
    runtime_err = result.get("full_runtime_error") or result.get("runtime_error")
    if runtime_err:
        parts = [runtime_err]
        if result.get("last_testcase"):
            parts.append(f"\nLast input:\n{result['last_testcase']}")
        stdout = result.get("std_output") or "".join(result.get("std_output_list") or [])
        if stdout.strip():
            parts.append(f"\nStdout:\n{stdout.rstrip()}")
        console.print(Panel("\n".join(parts), title="[red]Runtime Error[/red]", border_style="red"))
        return True
    return False


def all_passed(result: dict) -> bool:
    total = result.get("total_testcases") or 0
    return bool(result.get("run_success")) and total > 0 and result.get("total_correct") == total


def show_run_result(result: dict, cases: list[str]) -> None:
    if _show_errors(result):
        return
    if not result.get("run_success"):
        status = result.get("status_msg") or "Run failed"
        detail = result.get("last_testcase")
        body = f"{status}\n\nLast input:\n{detail}" if detail else status
        console.print(Panel(body, title="[red]❌ Run failed[/red]", border_style="red"))
        return

    outputs = result.get("code_answer") or []
    expected = result.get("expected_code_answer") or []
    stdouts = result.get("std_output_list") or []
    compare = result.get("compare_result") or ""
    total = result.get("total_testcases") or len(cases)
    passed = result.get("total_correct") or 0
    ok = all_passed(result)
    color = "bright_green" if ok else "bright_red"

    n = max(len(cases), min(len(outputs), total))
    show_stdout = any(s.strip() for s in stdouts[:n])

    table = Table(box=box.SIMPLE_HEAD, show_lines=True, pad_edge=False)
    table.add_column("", no_wrap=True)
    table.add_column("Input", style="cyan")
    table.add_column("Output")
    table.add_column("Expected", style="dim")
    if show_stdout:
        table.add_column("Stdout", style="dim")
    for i in range(n):
        good = compare[i] == "1" if i < len(compare) else None
        mark = "[bright_green]✓[/]" if good else "[bright_red]✗[/]" if good is False else "·"
        out = outputs[i] if i < len(outputs) else ""
        row = [
            f"{mark} {i + 1}",
            cases[i] if i < len(cases) else "?",
            Text(out, style="bright_green" if good else "bright_red" if good is False else ""),
            expected[i] if i < len(expected) else "",
        ]
        if show_stdout:
            row.append((stdouts[i] if i < len(stdouts) else "").rstrip())
        table.add_row(*row)

    title = f"{'✅' if ok else '❌'} {passed}/{total} test cases passed"
    if result.get("status_runtime"):
        title += f" · {result['status_runtime']}"
    console.print(Panel(table, title=title, border_style=color))


def show_submit_result(result: dict) -> None:
    status = result.get("status_msg") or "Unknown"
    accepted = status == "Accepted"
    color = "bright_green" if accepted else "bright_red"
    if _show_errors(result):
        return

    table = Table(box=None, show_header=False, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column(style="bold")
    table.add_row("Status", f"[{color}]{status}[/]")
    passed, total = result.get("total_correct"), result.get("total_testcases")
    if total:
        table.add_row("Tests passed", f"{passed}/{total}")
    for label, key, pct_key in (("Runtime", "status_runtime", "runtime_percentile"),
                                ("Memory", "status_memory", "memory_percentile")):
        if result.get(key):
            value = result[key]
            pct = result.get(pct_key)
            if isinstance(pct, (int, float)):
                value += f"  [dim](beats {pct:.1f}%)[/dim]"
            table.add_row(label, value)

    parts: list = [table]
    if not accepted:
        detail = Table(box=None, show_header=False, padding=(0, 1))
        detail.add_column(style="dim")
        detail.add_column()
        for label, value in (
            ("Input", result.get("input_formatted") or result.get("last_testcase")),
            ("Your output", result.get("code_output")),
            ("Expected", result.get("expected_output")),
            ("Stdout", (result.get("std_output") or "").rstrip()),
        ):
            if value:
                detail.add_row(label, str(value))
        if detail.row_count:
            parts += [Text("\nFailing case", style="bold yellow"), detail]

    console.print(Panel(Group(*parts), title=f"{'✅' if accepted else '❌'} {status}", border_style=color))


LOCAL_MARKS = {
    "pass": "[bright_green]✓[/]",
    "order": "[yellow]≈[/]",
    "fail": "[bright_red]✗[/]",
    "error": "[bright_red]✗[/]",
    "timeout": "[bright_red]⏱[/]",
    "skipped": "[dim]–[/]",
    "none": "[dim]·[/]",
}


def show_local_result(report) -> None:
    """Results of a local run (see leet.local.LocalReport)."""
    if report.load_error:
        console.print(Panel(report.load_error, title="[red]Your file failed to load[/red]", border_style="red"))
        if "expected an indented block after function definition" in report.load_error:
            console.print("[yellow]Looks like a method still has no body: the solution isn't written yet.[/yellow]")
        return

    results = report.results
    show_stdout = any(r.stdout.strip() for r in results)
    table = Table(box=box.SIMPLE_HEAD, show_lines=True, pad_edge=False)
    table.add_column("", no_wrap=True)
    table.add_column("Input", style="cyan")
    table.add_column("Output")
    table.add_column("Expected", style="dim")
    if show_stdout:
        table.add_column("Stdout", style="dim")
    table.add_column("Time", justify="right", style="dim", no_wrap=True)

    for n, r in enumerate(results, 1):
        tag = "" if r.case.source == "example" else " [dim]@[/dim]" if r.case.source == "custom" else ""
        if r.verdict == "error":
            output = Text("error ↓", style="bright_red")
        elif r.verdict in ("timeout", "skipped"):
            output = Text(r.verdict, style="bright_red" if r.verdict == "timeout" else "dim")
        else:
            color = {"pass": "bright_green", "fail": "bright_red", "order": "yellow"}.get(r.verdict, "")
            output = Text(r.output or "", style=color)
        expected = r.case.expected if r.case.expected is not None else Text("—", style="dim")
        row = [f"{LOCAL_MARKS[r.verdict]} {n}{tag}", r.case.input, output, expected]
        if show_stdout:
            row.append(r.stdout.rstrip())
        row.append(f"{r.ms:.1f} ms" if r.ms is not None else "")
        table.add_row(*row)

    checked = [r for r in results if r.case.expected is not None]
    passed = sum(r.verdict in ("pass", "order") for r in checked)
    errors = sum(r.verdict == "error" for r in results)
    if report.timed_out:
        title, color = f"⏱ Timed out after {report.timeout:g}s (infinite loop?)", "bright_red"
    elif checked:
        ok = passed == len(checked) and not errors
        title = f"{'✅' if ok else '❌'} Local: {passed}/{len(checked)} passed"
        color = "bright_green" if ok else "bright_red"
    else:
        title = f"🐍 Local: ran {len(results)} case{'s' if len(results) != 1 else ''}"
        color = "bright_red" if errors else "blue"
    unchecked = len(results) - len(checked)
    if checked and unchecked:
        title += f" · {unchecked} without expected output"
    console.print(Panel(table, title=title, border_style=color))

    if any(r.verdict == "order" for r in results):
        console.print("[yellow]≈[/yellow] [dim]same elements in a different order. Fine if the problem accepts "
                      "any order.[/dim]")
    if any(r.case.source == "custom" for r in results):
        console.print("[dim]@ = from your @tests. Add `=> expected` after a case to check it.[/dim]")
    for n, r in enumerate(results, 1):
        if r.error:
            console.print(Panel(r.error, title=f"[red]Case {n} error[/red]", border_style="red"))


# ─── Stats ────────────────────────────────────────────────────────────────────

def bar(done: int, total: int, width: int = 20) -> Text:
    filled = round(width * done / total) if total else 0
    t = Text("█" * filled, style="bright_green")
    t.append("░" * (width - filled), style="dim")
    return t


def show_stats(summary: dict, list_progress: list[tuple[str, int, int]], due: int, streak: int) -> None:
    if not summary["solved"] and not summary["submits"]:
        console.print("[dim]No history yet — start with[/dim] [cyan]lc random[/cyan]")
        return

    by = summary["by_difficulty"]
    head = Text()
    head.append(f"{summary['solved']} solved", style="bold")
    for d in ("Easy", "Medium", "Hard"):
        head.append("  ·  ")
        head.append(f"{d} {by.get(d, 0)}", style=DIFFICULTY_COLORS[d])
    if summary["submits"]:
        rate = 100 * summary["accepted"] / summary["submits"]
        head.append(f"\nAcceptance {rate:.0f}% of {summary['submits']} submits", style="dim")
    if streak:
        head.append(f"  ·  🔥 {streak}-day streak", style="dim")
    head.append(f"  ·  {due} review(s) due", style="yellow" if due else "dim")
    console.print(Panel(head, title="Progress", border_style="blue"))

    if list_progress:
        t = Table(box=box.SIMPLE_HEAD, title="Lists", title_justify="left")
        t.add_column("List", style="cyan")
        t.add_column("Progress")
        t.add_column("Solved", justify="right")
        for name, done, total in list_progress:
            t.add_row(name, bar(done, total), f"{done}/{total}")
        console.print(t)

    if summary["avg_time"]:
        t = Table(box=box.SIMPLE_HEAD, title="Average time to solve", title_justify="left")
        t.add_column("Difficulty")
        t.add_column("Time", justify="right")
        for d in ("Easy", "Medium", "Hard", "?"):
            if d in summary["avg_time"]:
                t.add_row(diff_text(d), fmt_duration(summary["avg_time"][d]))
        console.print(t)

    if summary["tags"]:
        t = Table(box=box.SIMPLE_HEAD, title="Top topics", title_justify="left")
        t.add_column("Topic")
        t.add_column("Solved", justify="right")
        for tag, n in summary["tags"].most_common(12):
            t.add_row(tag, str(n))
        console.print(t)
