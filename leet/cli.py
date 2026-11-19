"""lc — terminal LeetCode practice.

  lc random              pick an unsolved problem from your list and solve it
  lc daily               today's daily challenge
  lc review              re-solve problems that are due (spaced repetition)
  lc solve <slug|url>    show → editor → run/submit
  lc stats               progress by difficulty, topic and list
"""
from __future__ import annotations

import random
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import click
from rich import box
from rich.markup import escape
from rich.prompt import Confirm, Prompt
from rich.table import Table

from . import config as cfg
from . import display, languages, lists, local, menu, templates
from .api import AuthError, LeetCodeClient, LeetCodeError
from .display import console
from .history import INTERVALS, History, now
from .languages import Lang
from .timer import Timer
from .util import fmt_duration, slug_from_url


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fail(message: str) -> None:
    console.print(f"[red]Error:[/red] {message}")
    sys.exit(1)


def _auth_hint() -> str:
    age = ""
    saved = cfg.get("saved_at")
    if saved:
        try:
            days = (now() - datetime.fromisoformat(saved)).days
            age = f" (saved {days} day{'s' if days != 1 else ''} ago)"
        except ValueError:
            pass
    return f"LeetCode rejected your session cookies{age}. They've probably expired. Run: [cyan]lc config[/cyan]"


def _lang(name: str | None) -> Lang:
    try:
        return languages.resolve(name or cfg.get("lang"))
    except ValueError as e:
        _fail(str(e))
        raise  # unreachable; keeps type checkers happy


def _list_path(name: str | None) -> Path:
    try:
        return lists.resolve(name or cfg.get("default_list"))
    except FileNotFoundError as e:
        _fail(str(e))
        raise


def _fetch(client: LeetCodeClient, slug_or_url: str, refresh: bool = False) -> dict:
    try:
        with display.waiting("Fetching problem"):
            return client.get_question(slug_or_url, refresh=refresh)
    except Exception as e:
        _fail(f"Couldn't fetch problem: {e}")
        raise


def _solution_path(slug: str, lang: Lang) -> Path:
    return cfg.solutions_dir() / f"{slug}{lang.ext}"


def _find_solution(slug: str, file: Path | None, lang_name: str | None) -> tuple[Path, Lang]:
    if file:
        lang = languages.resolve(lang_name) if lang_name else languages.from_path(file)
        if not lang:
            _fail(f"Can't tell the language of {file}. Pass --lang.")
        return file, lang

    if lang_name:
        lang = _lang(lang_name)
        path = _solution_path(slug, lang)
        if path.exists():
            return path, lang
    else:
        preferred = _solution_path(slug, _lang(None))
        if preferred.exists():
            return preferred, _lang(None)
        for f in sorted(cfg.solutions_dir().glob(f"{slug}.*")):
            if languages.from_path(f):
                return f, languages.from_path(f)
    _fail(f"No solution for '{slug}' in {cfg.solutions_dir()}. Pass a file, or start with: lc solve {slug}")
    raise SystemExit(1)


def _open_editor(path: Path) -> None:
    cmd = cfg.editor_command()
    console.print(f"\nOpening [cyan]{path}[/cyan] in [bold]{cmd[0]}[/bold] — save and close when done.\n")
    try:
        subprocess.call([*cmd, str(path)])
    except FileNotFoundError:
        _fail(f"Editor '{cmd[0]}' not found. Set $EDITOR or run: lc config --editor nvim")


def _build_cases(q: dict, code: str, lang: Lang, custom_input: str | None) -> list[str]:
    if custom_input is not None:
        return [custom_input.replace("\\n", "\n")]
    cases = templates.example_cases(q)
    extra_lines = templates.parse_custom_tests(code, lang)
    if extra_lines:
        per = templates.params_per_case(q)
        extra, leftover = templates.custom_cases(extra_lines, per)
        _warn_leftover(leftover, per)
        cases += [inp for inp, _ in extra]
    return cases


def _warn_leftover(leftover: list[str], per: int) -> None:
    if leftover:
        console.print(f"[yellow]Ignoring {len(leftover)} trailing line(s) in @tests: "
                      f"each case needs {per} line(s).[/yellow]")


def _do_test(q, path: Path, lang: Lang, custom_input=None, timeout: float = 10.0):
    """Run a Python solution locally against examples + @tests."""
    if lang.slug != "python3":
        raise local.LocalRunError(f"Local testing supports Python only ({lang.name} isn't). Use run instead.")
    cases, leftover = local.build_cases(q, path.read_text(), lang, custom_input)
    _warn_leftover(leftover, templates.params_per_case(q))
    with display.waiting(f"Testing locally ({len(cases)} case{'s' if len(cases) != 1 else ''})"):
        report = local.run(q, path, cases, timeout=timeout)
    display.show_local_result(report)
    return report


def _do_run(client, q, code, lang, history, custom_input=None) -> dict:
    cases = _build_cases(q, code, lang, custom_input)
    with display.waiting(f"Running {len(cases)} test case(s)") as tick:
        result = client.run(q, code, lang.slug, "\n".join(cases), on_tick=tick)
    history.record(q["slug"], q, "run", result, lang.slug)
    history.save()
    display.show_run_result(result, cases)
    return result


def _do_submit(client, q, code, lang, history, elapsed=None) -> dict:
    with display.waiting("Submitting") as tick:
        result = client.submit(q, code, lang.slug, on_tick=tick)
    entry = history.record(q["slug"], q, "submit", result, lang.slug, elapsed=elapsed)
    history.save()
    display.show_submit_result(result)
    if result.get("status_msg") == "Accepted" and entry.get("review"):
        due = date.fromisoformat(entry["review"]["due"])
        days = (due - now().date()).days
        console.print(f"[dim]📅 Next review in {days} day{'s' if days != 1 else ''} ({due}).[/dim]")
    return result


ACTIONS = {
    "test": "run locally: examples + your @tests (Python, no LeetCode)",
    "run": "run on LeetCode: examples + your @tests",
    "submit": "submit to LeetCode",
    "edit": "reopen the editor",
    "hints": "show hints",
    "quit": "stop for now",
}


def _available_actions(lang: Lang) -> list[str]:
    names = list(ACTIONS)
    if lang.slug != "python3":
        names.remove("test")
    if not cfg.has_auth():
        names = [n for n in names if n not in ("run", "submit")]
    return names


def _next_action(names: list[str]) -> str:
    width = max(len(n) for n in names)
    i = menu.choose(
        "What next?",
        [f"{n.ljust(width)}  [dim]{ACTIONS[n]}[/dim]" for n in names],
        names=names,
        keys=[n[0] for n in names],
    )
    return "quit" if i is None else names[i]


def _after_edit(client, q, path: Path, lang: Lang, timer: Timer, history: History) -> None:
    names = _available_actions(lang)
    if not cfg.has_auth():
        if "test" not in names:
            console.print("\n[dim]No LeetCode login configured, so you can't run or submit. Run: lc config[/dim]")
            return
        console.print("\n[dim]No LeetCode login: local testing only. Run `lc config` to run/submit on LeetCode.[/dim]")

    while True:
        clock = f"⏱  {fmt_duration(timer.elapsed())}"
        if timer.timebox:
            clock += f" / {timer.timebox:g}m timebox"
            if timer.over:
                clock += f" [red](over by {fmt_duration(timer.over)})[/red]"
        console.print(f"\n[dim]{clock}[/dim]")

        choice = _next_action(names)
        if choice == "quit":
            return
        if choice == "edit":
            _open_editor(path)
            continue
        if choice == "hints":
            display.show_hints(q)
            continue

        code = path.read_text()
        try:
            if choice == "test":
                report = _do_test(q, path, lang)
                if not (report.all_passed and cfg.has_auth()
                        and Confirm.ask("\n[yellow]All local tests passed! Submit to LeetCode?[/yellow]",
                                        default=False)):
                    continue
            elif choice == "run":
                result = _do_run(client, q, code, lang, history)
                if not (display.all_passed(result)
                        and Confirm.ask("\n[yellow]All tests passed! Submit?[/yellow]", default=False)):
                    continue
            result = _do_submit(client, q, code, lang, history, elapsed=timer.elapsed())
            if result.get("status_msg") == "Accepted":
                msg = f"🎉 Solved in [bold]{fmt_duration(timer.elapsed())}[/bold]"
                if timer.timebox:
                    msg += (f" [red](over your {timer.timebox:g}m timebox by {fmt_duration(timer.over)})[/red]"
                            if timer.over else f" [green](within your {timer.timebox:g}m timebox)[/green]")
                console.print(msg)
                return
        except AuthError:
            console.print(f"[red]Error:[/red] {_auth_hint()}")
            return
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")


def _solve(client: LeetCodeClient, q: dict, lang: Lang, hints: bool, timebox: float | None,
           show: bool = True) -> None:
    history = History()
    if show:
        display.show_question(q, history.get(q["slug"]))
        if hints:
            display.show_hints(q)
    if not q.get("content"):
        _fail("This problem is premium-only.")

    path = _solution_path(q["slug"], lang)
    if path.exists():
        console.print(f"\n[dim]Resuming your existing solution:[/dim] [cyan]{path}[/cyan]")
    else:
        code = templates.starter_code(q, lang)
        if code is None:
            _fail(f"No {lang.name} starter code for this problem.")
        display.show_code(code, lang)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(templates.build_template(q, code, lang))

    timer = Timer(timebox)
    timer.start()
    try:
        _open_editor(path)
        _after_edit(client, q, path, lang, timer, history)
    finally:
        timer.cancel()


def solve_options(f):
    f = click.option("--timebox", type=float, metavar="MIN",
                     help="Desktop notification after MIN minutes.")(f)
    f = click.option("--lang", "lang_name", metavar="LANG",
                     help="Language (python3, cpp, java, go, …). Default from config.")(f)
    f = click.option("--hints", is_flag=True, help="Show hints too.")(f)
    return f


# ─── CLI ──────────────────────────────────────────────────────────────────────

@click.group(invoke_without_command=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="leet")
@click.pass_context
def cli(ctx):
    """🧩 lc — terminal LeetCode practice. Run with no command to open the dashboard."""
    if ctx.invoked_subcommand is None:
        if menu.interactive():
            ctx.invoke(dash)
        else:
            click.echo(ctx.get_help())


DASHBOARD_LIST = "neetcode150"


@cli.command()
@click.option("--list", "list_name", default=DASHBOARD_LIST, show_default=True, metavar="NAME",
              help="List to show.")
@click.option("--lang", "lang_name", metavar="LANG", help="Language for problems you open.")
@click.option("--timebox", type=float, metavar="MIN", help="Timebox for problems you open.")
def dash(list_name, lang_name, timebox):
    """Interactive dashboard: browse a list with your progress and pick a problem."""
    path = _list_path(list_name)
    if not menu.interactive():
        list_cmd.callback(list_name)  # not a terminal: print the static list instead
        return
    lang = _lang(lang_name)
    from .dashboard import Dashboard

    board = Dashboard(path)
    try:
        while (slug := board.run()) is not None:
            client = LeetCodeClient.from_config()
            try:
                _solve(client, _fetch(client, slug), lang, False, timebox)
            except SystemExit:
                pass  # e.g. premium problem: show the error, then go back
            console.input("\n[dim]Press Enter to return to the dashboard…[/dim]")
            board.reload()
    finally:
        board.stop()


cli.add_command(dash, "dashboard")


@cli.command()
@click.option("--solutions-dir", type=click.Path(file_okay=False, path_type=Path),
              help="Where solution files are saved.")
@click.option("--lang", help="Default language.")
@click.option("--editor", help='Editor command, e.g. "nvim" or "code -w".')
@click.option("--list", "default_list", help="Default list for random/list/add.")
@click.option("--show", is_flag=True, help="Print current settings.")
def config(solutions_dir, lang, editor, default_list, show):
    """Log in (paste browser cookies) or change settings."""
    changes = {}
    if solutions_dir:
        changes["solutions_dir"] = str(solutions_dir.expanduser().resolve())
    if lang:
        changes["lang"] = _lang(lang).slug
    if editor:
        changes["editor"] = editor
    if default_list:
        _list_path(default_list)
        changes["default_list"] = default_list
    if changes:
        cfg.update(**changes)
        for k, v in changes.items():
            console.print(f"[bright_green]✓[/bright_green] {k} = [cyan]{v}[/cyan]")
        return

    if show:
        t = Table(box=box.SIMPLE, show_header=False)
        t.add_column(style="dim")
        t.add_column()
        login = "[bright_green]set[/]" if cfg.has_auth() else "[red]not set[/]"
        if cfg.get("saved_at"):
            login += f" [dim](saved {cfg.get('saved_at')[:10]})[/dim]"
        t.add_row("login", login)
        t.add_row("lang", cfg.get("lang"))
        t.add_row("editor", " ".join(cfg.editor_command()))
        t.add_row("default list", cfg.get("default_list"))
        t.add_row("solutions dir", str(cfg.solutions_dir()))
        t.add_row("data dir", str(cfg.home()))
        console.print(t)
        return

    console.print(
        "\n[bold]To get your cookies:[/bold]\n"
        "1. Log in to [link=https://leetcode.com]leetcode.com[/link] in your browser\n"
        "2. Open DevTools → Application → Cookies → [bold]leetcode.com[/bold]\n"
        "3. Copy the [cyan]LEETCODE_SESSION[/cyan] and [cyan]csrftoken[/cyan] values\n"
        "[dim](input is hidden)[/dim]\n"
    )
    session = Prompt.ask("[cyan]LEETCODE_SESSION[/cyan]", password=True).strip()
    csrf = Prompt.ask("[cyan]csrftoken[/cyan]", password=True).strip()
    if not session or not csrf:
        _fail("Both values are required.")

    cfg.update(session=session, csrf=csrf, saved_at=now().isoformat(timespec="seconds"))
    console.print(f"\n[bright_green]✓ Saved to {cfg.config_file()}[/bright_green]")
    try:
        with display.waiting("Checking login"):
            username = LeetCodeClient(session, csrf).whoami()
        if username:
            console.print(f"[bright_green]✓ Logged in as [bold]{username}[/bold][/bright_green]")
        else:
            console.print("[yellow]⚠ LeetCode didn't recognise these cookies. Double-check them.[/yellow]")
    except Exception as e:
        console.print(f"[red]Couldn't verify: {e}[/red]")


@cli.command("random")
@click.option("--list", "list_name", metavar="NAME", help="List name or file (default from config).")
@click.option("-d", "--difficulty", multiple=True,
              type=click.Choice(["easy", "medium", "hard"], case_sensitive=False), help="Repeatable.")
@click.option("-t", "--tag", multiple=True, help='Topic filter, e.g. -t "dynamic". Repeatable.')
@click.option("--include-solved", is_flag=True, help="Also pick problems you've already solved.")
@solve_options
def random_cmd(list_name, difficulty, tag, include_solved, hints, lang_name, timebox):
    """Pick a random unsolved problem from a list."""
    lang = _lang(lang_name)
    path = _list_path(list_name)
    slugs = lists.load(path)
    history = History()
    pool = slugs if include_solved else [s for s in slugs if not history.is_solved(s)]
    if not slugs:
        _fail(f"{path} has no problems.")
    if not pool:
        console.print(f"🎉 You've solved all {len(slugs)} problems in [cyan]{path.stem}[/cyan]! "
                      "Use --include-solved, or try [cyan]lc review[/cyan].")
        return

    wanted_diff = {d.lower() for d in difficulty}
    wanted_tags = [t.lower() for t in tag]

    def matches(q: dict) -> bool:
        if wanted_diff and (q.get("difficulty") or "").lower() not in wanted_diff:
            return False
        names = [t["name"].lower() for t in q.get("topicTags") or []]
        return not wanted_tags or any(w in n for w in wanted_tags for n in names)

    random.shuffle(pool)
    client = LeetCodeClient.from_config()
    q, last_error = None, None
    with display.waiting(f"Picking from {len(pool)} problems"):
        for slug in pool:
            try:
                cand = client.get_question(slug)
            except Exception as e:
                last_error = e
                continue
            if cand.get("content") and matches(cand):
                q = cand
                break
    if not q:
        if last_error and not wanted_diff and not wanted_tags:
            _fail(f"Couldn't fetch problems: {last_error}")
        _fail(f"No {'' if include_solved else 'unsolved '}problem in {path.stem} matches those filters.")

    kind = "problems" if include_solved else "unsolved problems"
    console.print(f"[dim]Picked from {len(pool)} {kind} in {path.stem}[/dim]\n")
    display.show_question(q, history.get(q["slug"]))
    if hints:
        display.show_hints(q)
    if Confirm.ask("\n[yellow]Solve this one?[/yellow]", default=True):
        _solve(client, q, lang, hints, timebox, show=False)


@cli.command()
@solve_options
def daily(hints, lang_name, timebox):
    """Solve today's LeetCode daily challenge."""
    lang = _lang(lang_name)
    client = LeetCodeClient.from_config()
    try:
        with display.waiting("Getting today's challenge"):
            slug = client.daily_slug()
    except Exception as e:
        _fail(str(e))
    _solve(client, _fetch(client, slug), lang, hints, timebox)


@cli.command()
@solve_options
def review(hints, lang_name, timebox):
    """Re-solve problems that are due for spaced-repetition review."""
    history = History()
    due = history.due()
    if not due:
        nxt = history.upcoming()
        msg = "Nothing due for review 🎉"
        if nxt:
            msg += f" Next up: [cyan]{nxt[1]['title']}[/cyan] on {nxt[1]['review']['due']}."
        console.print(msg)
        return

    today = now().date()
    width = max(len(e["title"]) for _, e in due)
    labels = []
    for _, e in due:
        overdue = (today - date.fromisoformat(e["review"]["due"])).days
        when = "due today" if overdue == 0 else f"[red]{overdue}d overdue[/red]"
        diff = e.get("difficulty") or ""
        color = display.DIFFICULTY_COLORS.get(diff, "dim")
        labels.append(f"{escape(e['title'].ljust(width))}  [{color}]{diff:<6}[/]  {when}  "
                      f"[dim]· {INTERVALS[e['review']['level']]}d interval[/dim]")

    console.print(f"[bold]{len(due)} problem(s) due for review[/bold]")
    pick = menu.choose("Which one?", labels)
    if pick is None:
        return
    client = LeetCodeClient.from_config()
    _solve(client, _fetch(client, due[pick][0]), _lang(lang_name), hints, timebox)


@cli.command()
@click.argument("slug_or_url")
@click.option("--hints", is_flag=True, help="Show hints.")
@click.option("--refresh", is_flag=True, help="Ignore the cache and re-fetch.")
def show(slug_or_url, hints, refresh):
    """Display a problem."""
    client = LeetCodeClient.from_config()
    q = _fetch(client, slug_or_url, refresh=refresh)
    display.show_question(q, History().get(q["slug"]))
    if hints:
        display.show_hints(q)


@cli.command()
@click.argument("slug_or_url")
@solve_options
def solve(slug_or_url, hints, lang_name, timebox):
    """Show a problem, open your editor, then run/submit."""
    lang = _lang(lang_name)
    client = LeetCodeClient.from_config()
    _solve(client, _fetch(client, slug_or_url), lang, hints, timebox)


@cli.command()
@click.argument("slug_or_url")
@click.argument("file", required=False, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--input", "custom_input", help=r'Test input instead of examples + @tests, e.g. "[3,2,4]\n6".')
@click.option("--timeout", type=float, default=10.0, show_default=True, help="Seconds before giving up.")
def test(slug_or_url, file, custom_input, timeout):
    """Run a Python solution locally against examples + @tests (no LeetCode, no login)."""
    client = LeetCodeClient.from_config()
    q = _fetch(client, slug_or_url)
    path, lang = _find_solution(q["slug"], file, None if file else "python3")
    try:
        report = _do_test(q, path, lang, custom_input, timeout)
    except local.LocalRunError as e:
        _fail(str(e))
    if report.load_error or report.timed_out or any(r.verdict in ("fail", "error", "timeout")
                                                    for r in report.results):
        sys.exit(1)


@cli.command()
@click.argument("slug_or_url")
@click.argument("file", required=False, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--input", "custom_input", help=r'Test input instead of examples + @tests, e.g. "[3,2,4]\n6".')
@click.option("--lang", "lang_name", metavar="LANG", help="Language (default: from file extension).")
def run(slug_or_url, file, custom_input, lang_name):
    """Run a solution against examples + your @tests (doesn't count as a submission)."""
    client = LeetCodeClient.from_config()
    q = _fetch(client, slug_or_url)
    path, lang = _find_solution(q["slug"], file, lang_name)
    try:
        _do_run(client, q, path.read_text(), lang, History(), custom_input)
    except AuthError:
        _fail(_auth_hint())
    except Exception as e:
        _fail(str(e))


@cli.command()
@click.argument("slug_or_url")
@click.argument("file", required=False, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--lang", "lang_name", metavar="LANG", help="Language (default: from file extension).")
def submit(slug_or_url, file, lang_name):
    """Submit a solution to LeetCode (counts toward your stats)."""
    client = LeetCodeClient.from_config()
    q = _fetch(client, slug_or_url)
    path, lang = _find_solution(q["slug"], file, lang_name)
    try:
        _do_submit(client, q, path.read_text(), lang, History())
    except AuthError:
        _fail(_auth_hint())
    except Exception as e:
        _fail(str(e))


@cli.command()
def stats():
    """Show your progress."""
    history = History()
    solved = history.solved_slugs()
    progress = []
    for name, path in lists.available().items():
        slugs = lists.load(path)
        if slugs:
            progress.append((name, sum(s in solved for s in slugs), len(slugs)))
    display.show_stats(history.summary(), progress, len(history.due()), history.streak())


@cli.command("list")
@click.argument("name", required=False)
def list_cmd(name):
    """Show a list with your progress (default list if NAME is omitted)."""
    path = _list_path(name)
    items = lists.load_sections(path)
    history = History()
    client = LeetCodeClient.from_config()

    t = Table(box=box.SIMPLE_HEAD, title=f"{path.stem}  [dim]{path}[/dim]", title_justify="left")
    t.add_column("", no_wrap=True)
    t.add_column("Problem")
    t.add_column("Difficulty")
    t.add_column("Next review", style="dim")
    current_section, solved = None, 0
    for section, slug in items:
        if section and section != current_section:
            t.add_row("", f"[bold blue]{section}[/bold blue]", "", "")
            current_section = section
        e = history.get(slug) or {}
        q = client.cached_question(slug) or {}
        title = e.get("title") if e.get("title") not in (None, slug) else q.get("title", slug)
        if e.get("solved"):
            solved += 1
            mark = "[bright_green]✓[/]"
        elif e.get("attempts"):
            mark = "[yellow]◐[/]"
        else:
            mark = "[dim]·[/]"
        review = (e.get("review") or {}).get("due", "")
        t.add_row(mark, title, display.diff_text(e.get("difficulty") or q.get("difficulty")), review)
    console.print(t)
    console.print(f"Solved [bold]{solved}/{len(items)}[/bold]  ", display.bar(solved, len(items)))


@cli.command()
@click.argument("slug_or_url")
@click.option("--list", "list_name", metavar="NAME", help="List to add to (default from config).")
def add(slug_or_url, list_name):
    """Add a problem to a list (bundled lists are copied to ~/.leet/lists first)."""
    slug = slug_from_url(slug_or_url)
    title = slug
    try:
        title = LeetCodeClient.from_config().get_question(slug)["title"]
    except LeetCodeError as e:
        _fail(str(e))
    except Exception as e:
        console.print(f"[yellow]⚠ Couldn't verify the problem ({e}); adding anyway.[/yellow]")
    path, added = lists.add(list_name or cfg.get("default_list"), slug)
    if added:
        console.print(f"[bright_green]✓[/bright_green] Added [cyan]{title}[/cyan] to {path}")
    else:
        console.print(f"[dim]{title} is already in {path}[/dim]")


@cli.command()
@click.argument("slugs", nargs=-1, required=True)
@click.option("--unsolved", is_flag=True, help="Mark as not solved (removes it from reviews).")
def mark(slugs, unsolved):
    """Mark problems solved outside this tool (or unsolved)."""
    history = History()
    client = LeetCodeClient.from_config()
    for raw in slugs:
        slug = slug_from_url(raw)
        try:
            q = client.get_question(slug)
        except Exception as e:
            console.print(f"[yellow]⚠ {slug}: couldn't fetch details ({e})[/yellow]")
            q = None
        history.mark(slug, q, solved=not unsolved)
        state = "unsolved" if unsolved else "solved"
        console.print(f"[bright_green]✓[/bright_green] {q['title'] if q else slug} marked {state}")
    history.save()


@cli.group()
def cache():
    """Manage the local problem cache."""


@cache.command("clear")
def cache_clear():
    """Delete all cached problems."""
    files = list(cfg.cache_dir().glob("*.json"))
    for f in files:
        f.unlink()
    console.print(f"Removed {len(files)} cached problem(s).")


@cache.command("warm")
@click.option("--list", "list_name", metavar="NAME", help="List to pre-fetch (default from config).")
def cache_warm(list_name):
    """Pre-fetch every problem in a list (faster filters, offline browsing)."""
    from rich.progress import track

    slugs = lists.load(_list_path(list_name))
    client = LeetCodeClient.from_config()
    failed = []
    for slug in track(slugs, description="Fetching", console=console):
        try:
            client.get_question(slug)
        except Exception:
            failed.append(slug)
    console.print(f"Cached {len(slugs) - len(failed)}/{len(slugs)} problems.")
    if failed:
        console.print(f"[yellow]Failed: {', '.join(failed)}[/yellow]")


def main() -> None:
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
        sys.exit(130)


if __name__ == "__main__":
    main()
