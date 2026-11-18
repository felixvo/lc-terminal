import pytest
from click.testing import CliRunner

from leet import menu
from leet.cli import cli
from leet.history import History
from leet.menu import Menu


def press(m, *keys):
    for k in keys:
        done, chosen = m.handle(k)
        if done:
            return chosen
    raise AssertionError("menu didn't finish")


def test_ctrl_n_p_move_and_wrap():
    m = Menu(3)
    assert press(m, "down", "down", "enter") == 2
    assert press(Menu(3), "up", "enter") == 2          # wraps to the bottom
    assert press(Menu(3), "down", "down", "down", "enter") == 0  # wraps to the top
    assert press(Menu(3, default=1), "enter") == 1


def test_raw_key_mapping():
    assert menu.KEYS[b"\x0e"] == "down"  # Ctrl+N
    assert menu.KEYS[b"\x10"] == "up"    # Ctrl+P
    assert menu.ESCAPES[b"[B"] == "down" and menu.ESCAPES[b"[A"] == "up"


def test_shortcuts_digits_and_cancel():
    keys = ["r", "s", "e", "h", "q"]
    assert press(Menu(5, keys=keys), "s") == 1
    assert press(Menu(5, keys=keys), "q") == 4      # q is a shortcut here → picks "quit"
    assert press(Menu(5), "3") == 2
    assert press(Menu(5), "q") is None             # no q shortcut → cancel
    assert press(Menu(5), "esc") is None
    assert press(Menu(2), "x", "9", "enter") == 0   # unknown keys / out-of-range digits ignored
    with pytest.raises(KeyboardInterrupt):
        Menu(2).handle("interrupt")


def test_fallback_when_not_a_terminal(monkeypatch):
    monkeypatch.setattr(menu, "interactive", lambda: False)
    monkeypatch.setattr(menu.Prompt, "ask", lambda *a, **k: "submit")
    assert menu.choose("What next?", ["run …", "submit …"], names=["run", "submit"]) == 1
    monkeypatch.setattr(menu.IntPrompt, "ask", lambda *a, **k: 7)
    assert menu.choose("Which one?", ["a", "b"]) is None  # out of range


def test_review_picker_fallback(question, monkeypatch):
    h = History()
    h.mark("two-sum", question)
    h.problems["two-sum"]["review"]["due"] = "2000-01-01"
    h.save()
    picked = []
    monkeypatch.setattr("leet.cli._fetch", lambda client, slug: picked.append(slug) or question)
    monkeypatch.setattr("leet.cli._solve", lambda *a, **k: None)
    result = CliRunner().invoke(cli, ["review"], input="1\n", catch_exceptions=False)
    assert result.exit_code == 0
    assert "Two Sum" in result.output and "overdue" in result.output
    assert picked == ["two-sum"]
