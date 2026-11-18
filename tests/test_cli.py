"""CLI smoke tests: commands that don't need the network or an editor."""
import json

from click.testing import CliRunner

from leet import config as cfg
from leet.cli import cli
from leet.history import History

ACCEPTED = {"status_msg": "Accepted"}


def invoke(*args, input=None):
    result = CliRunner().invoke(cli, list(args), input=input, catch_exceptions=False)
    return result.exit_code, result.output


def test_help_lists_all_commands():
    code, out = invoke("--help")
    assert code == 0
    for cmd in ("random", "daily", "review", "solve", "run", "submit", "stats", "list", "add", "mark", "cache"):
        assert cmd in out


def test_config_settings_and_show(tmp_path):
    code, out = invoke("config", "--lang", "c++", "--editor", "nvim", "--solutions-dir", str(tmp_path))
    assert code == 0
    assert cfg.get("lang") == "cpp" and cfg.get("editor") == "nvim"
    code, out = invoke("config", "--show")
    assert "not set" in out and "cpp" in out


def test_config_rejects_bad_lang():
    code, out = invoke("config", "--lang", "cobol")
    assert code == 1 and "Unknown language" in out


def test_stats_empty_and_with_history(question):
    assert "No history yet" in invoke("stats")[1]
    h = History()
    h.record("two-sum", question, "submit", ACCEPTED, "python3", elapsed=90)
    h.save()
    code, out = invoke("stats")
    assert code == 0 and "1 solved" in out and "questions" in out and "1m 30s" in out


def test_review_nothing_due(question):
    assert "Nothing due" in invoke("review")[1]


def test_list_shows_solved_marks(question):
    h = History()
    h.record("two-sum", question, "submit", ACCEPTED, "python3")
    h.save()
    code, out = invoke("list", "questions")
    assert code == 0 and "Two Sum" in out and "Solved 1/" in out


def test_random_when_everything_solved(tmp_path, question):
    lst = tmp_path / "tiny.txt"
    lst.write_text("two-sum\n")
    h = History()
    h.record("two-sum", question, "submit", ACCEPTED, "python3")
    h.save()
    code, out = invoke("random", "--list", str(lst))
    assert code == 0 and "solved all 1" in out


def test_random_filters_use_cache(tmp_path, question, monkeypatch):
    cfg.cache_dir().mkdir(parents=True)
    (cfg.cache_dir() / "two-sum.json").write_text(json.dumps(question))
    lst = tmp_path / "tiny.txt"
    lst.write_text("two-sum\n")
    code, out = invoke("random", "--list", str(lst), "-d", "hard")
    assert code == 1 and "matches those filters" in out
    code, out = invoke("random", "--list", str(lst), "-t", "hash", input="n\n")
    assert code == 0 and "Two Sum" in out


def test_run_without_solution_file(question):
    cfg.cache_dir().mkdir(parents=True)
    (cfg.cache_dir() / "two-sum.json").write_text(json.dumps(question))
    code, out = invoke("run", "two-sum")
    assert code == 1 and "No solution" in out


def test_cache_clear(question):
    cfg.cache_dir().mkdir(parents=True)
    (cfg.cache_dir() / "two-sum.json").write_text("{}")
    assert "Removed 1" in invoke("cache", "clear")[1]
