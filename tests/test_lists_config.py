import os

import pytest

from leet import config as cfg
from leet import lists


def test_config_roundtrip_and_permissions():
    assert cfg.get("lang") == "python3"  # default
    cfg.update(session="s", csrf="c")
    cfg.update(lang="cpp")  # merges, doesn't wipe cookies
    assert cfg.load() == {"session": "s", "csrf": "c", "lang": "cpp"}
    assert cfg.has_auth()
    assert oct(os.stat(cfg.config_file()).st_mode & 0o777) == "0o600"


def test_solutions_dir_and_editor(tmp_path, monkeypatch):
    assert cfg.solutions_dir() == cfg.home() / "solutions"
    cfg.update(solutions_dir=str(tmp_path / "sol"))
    assert cfg.solutions_dir() == tmp_path / "sol"
    assert cfg.editor_command() == ["vim"]
    monkeypatch.setenv("EDITOR", "code -w")
    assert cfg.editor_command() == ["code", "-w"]


def test_corrupt_config_is_ignored():
    cfg.config_file().parent.mkdir(parents=True)
    cfg.config_file().write_text("{not json")
    assert cfg.load() == {}


def test_load_list_comments_dupes_and_sections(tmp_path):
    f = tmp_path / "mine.txt"
    f.write_text(
        "# header comment\n"
        "  # indented comment\n"
        "# ── Arrays (2) ──────\n"
        "https://leetcode.com/problems/two-sum/\n"
        "  contains-duplicate  \n"
        "two-sum\n"
        "\n"
        "# ── Stack ──\n"
        "valid-parentheses\n"
    )
    assert lists.load(f) == ["two-sum", "contains-duplicate", "valid-parentheses"]
    assert lists.load_sections(f)[0] == ("Arrays (2)", "two-sum")
    assert lists.load_sections(f)[2] == ("Stack", "valid-parentheses")


def test_bundled_lists_resolve():
    names = lists.available()
    assert {"questions", "neetcode150"} <= set(names)
    assert lists.resolve("neetcode150") == names["neetcode150"]
    assert len(lists.load(names["neetcode150"])) > 140
    with pytest.raises(FileNotFoundError):
        lists.resolve("nope")


def test_add_copies_bundled_list_and_skips_dupes():
    bundled = lists.resolve("questions")
    before = bundled.read_text()

    path, added = lists.add("questions", "two-sum")  # already there
    assert not added and path == bundled

    path, added = lists.add("questions", "lru-cache")
    assert added and path == cfg.lists_dir() / "questions.txt"
    assert bundled.read_text() == before  # package untouched
    assert lists.resolve("questions") == path  # user copy now shadows it
    assert lists.load(path)[-1] == "lru-cache"


def test_add_creates_new_list():
    path, added = lists.add("graphs", "number-of-islands")
    assert added and path == cfg.lists_dir() / "graphs.txt"
    assert lists.load(path) == ["number-of-islands"]
