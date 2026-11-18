from datetime import date, datetime, timezone

import pytest
from click.testing import CliRunner
from rich.console import Console

from leet import lists
from leet.cli import cli
from leet.dashboard import DashboardState, pretty_slug, render
from leet.history import History

ITEMS = [
    ("Arrays", "two-sum"),
    ("Arrays", "contains-duplicate"),
    ("Stack", "valid-parentheses"),
    ("Stack", "largest-rectangle-in-histogram"),
]
META = {
    "two-sum": {"title": "Two Sum", "difficulty": "Easy", "id": "1"},
    "valid-parentheses": {"title": "Valid Parentheses", "difficulty": "Easy", "id": "20"},
    "largest-rectangle-in-histogram": {"title": "Largest Rectangle in Histogram", "difficulty": "Hard", "id": "84"},
    # contains-duplicate not fetched yet
}
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def state(question):
    h = History()
    h.record("two-sum", question, "submit", {"status_msg": "Accepted"}, "python3", at=T0)  # due 2026-01-02
    h.record("valid-parentheses", None, "submit", {"status_msg": "Wrong Answer"}, "python3", at=T0)
    return DashboardState("neetcode150", ITEMS, h, dict(META), today=date(2026, 1, 5))


def slugs(state):
    return [s for _, s in state.visible()]


def test_rows_have_section_headings(state):
    assert state.rows() == [
        ("section", "Arrays"), ("problem", "two-sum"), ("problem", "contains-duplicate"),
        ("section", "Stack"), ("problem", "valid-parentheses"), ("problem", "largest-rectangle-in-histogram"),
    ]


def test_info_and_totals(state):
    i = state.info("contains-duplicate")
    assert i["title"] == "Contains Duplicate" and not i["known"]
    assert state.info("two-sum")["due"] and state.info("two-sum")["solved"]
    assert state.info("valid-parentheses")["attempted"] and state.info("valid-parentheses")["submits"] == 1
    t = state.totals()
    assert (t["solved"], t["total"], t["due"]) == (1, 4, 1)
    assert t["by_diff"] == {"Easy": [1, 2], "Medium": [0, 0], "Hard": [0, 1]}


def test_ctrl_n_p_navigation_wraps(state):
    assert state.selected() == "two-sum"
    state.handle("down")
    state.handle("down")
    assert state.selected() == "valid-parentheses"
    state.handle("up")
    state.handle("up")
    state.handle("up")
    assert state.selected() == "largest-rectangle-in-histogram"  # wrapped
    state.handle("g")
    assert state.cursor == 0
    state.handle("G")
    assert state.cursor == 3
    state.handle("pgup", page=10)
    assert state.cursor == 0


def test_filters_keep_selection(state):
    state.handle("down")                       # contains-duplicate
    state.handle("f")                          # unsolved
    assert slugs(state) == ["contains-duplicate", "valid-parentheses", "largest-rectangle-in-histogram"]
    assert state.selected() == "contains-duplicate"
    state.handle("f")                          # solved
    assert slugs(state) == ["two-sum"]
    state.handle("f")                          # due
    assert slugs(state) == ["two-sum"]
    state.handle("f")                          # back to all
    state.handle("d")                          # Easy
    assert slugs(state) == ["two-sum", "valid-parentheses"]
    state.handle("d")
    state.handle("d")                          # Hard
    assert slugs(state) == ["largest-rectangle-in-histogram"]


def test_search_types_letters_including_j_and_q(state):
    state.handle("/")
    for ch in "rect":
        state.handle(ch)
    assert slugs(state) == ["largest-rectangle-in-histogram"]
    state.handle("backspace")
    state.handle("backspace")
    state.handle("backspace")
    state.handle("backspace")
    state.handle("q")                          # typed, doesn't quit
    assert state.query == "q" and state.searching
    state.handle("esc")
    assert state.query == "" and not state.searching and len(slugs(state)) == 4


def test_actions(state):
    assert state.handle("enter") == ("solve", "two-sum")
    assert state.handle("o") == ("open", "two-sum")
    assert state.handle("q") == ("quit", "")
    state.handle("r")
    assert not state.info(state.selected())["solved"]
    with pytest.raises(KeyboardInterrupt):
        state.handle("interrupt")


def test_render_scrolls_to_cursor(state):
    console = Console(record=True, width=110, height=12)
    state.handle("G")
    console.print(render(state, height=12, fetch=(3, 10)))
    out = console.export_text()
    assert "1/4 solved" in out and "Easy 1/2" in out and "1 due" in out
    assert "fetching details 3/10" in out
    assert "Largest Rectangle in Histogram" in out
    assert "4/4" in out and "r random · q quit" in out


def test_pretty_slug():
    assert pretty_slug("two-sum-ii-input-array-is-sorted") == "Two Sum Ii Input Array Is Sorted"


def test_dash_falls_back_to_list_when_not_a_terminal():
    result = CliRunner().invoke(cli, ["dash"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "neetcode150" in result.output and "Arrays & Hashing" in result.output
    assert f"Solved 0/{len(lists.load(lists.resolve('neetcode150')))}" in result.output


def test_bare_lc_prints_help_when_not_a_terminal():
    result = CliRunner().invoke(cli, [], catch_exceptions=False)
    assert result.exit_code == 0 and "dashboard" in result.output
