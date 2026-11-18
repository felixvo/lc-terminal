from datetime import date, datetime, timedelta, timezone

from leet.history import INTERVALS, History

T0 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
ACCEPTED = {"status_msg": "Accepted", "total_correct": 50, "total_testcases": 50}
WRONG = {"status_msg": "Wrong Answer", "total_correct": 10, "total_testcases": 50}


def day(n):
    return T0 + timedelta(days=n)


def test_first_accept_marks_solved_and_schedules(question):
    h = History()
    e = h.record("two-sum", question, "submit", ACCEPTED, "python3", elapsed=300, at=T0)
    assert e["solved"] and e["difficulty"] == "Easy" and e["tags"] == ["Array", "Hash Table"]
    assert e["review"] == {"level": 0, "due": "2026-01-02"}
    assert e["attempts"][0]["elapsed"] == 300


def test_runs_and_wrong_answers_dont_solve(question):
    h = History()
    h.record("two-sum", question, "run", {"status_msg": "Accepted", "run_success": True}, "python3", at=T0)
    h.record("two-sum", question, "submit", WRONG, "python3", at=T0)
    assert not h.is_solved("two-sum")
    assert h.get("two-sum")["review"] is None


def test_clean_review_climbs_the_ladder(question):
    h = History()
    h.record("two-sum", question, "submit", ACCEPTED, "python3", at=T0)
    t = T0
    for level in range(1, len(INTERVALS) + 2):
        t = t + timedelta(days=INTERVALS[h.get("two-sum")["review"]["level"]])
        h.record("two-sum", question, "submit", ACCEPTED, "python3", at=t)
        assert h.get("two-sum")["review"]["level"] == min(level, len(INTERVALS) - 1)


def test_struggle_resets_and_early_solve_keeps_schedule(question):
    h = History()
    h.record("two-sum", question, "submit", ACCEPTED, "python3", at=day(0))
    h.record("two-sum", question, "submit", ACCEPTED, "python3", at=day(1))   # due → level 1
    assert h.get("two-sum")["review"] == {"level": 1, "due": "2026-01-05"}

    h.record("two-sum", question, "submit", ACCEPTED, "python3", at=day(2))   # early → unchanged
    assert h.get("two-sum")["review"] == {"level": 1, "due": "2026-01-05"}

    h.record("two-sum", question, "submit", WRONG, "python3", at=day(4))
    h.record("two-sum", question, "submit", ACCEPTED, "python3", at=day(4))   # struggled → reset
    assert h.get("two-sum")["review"] == {"level": 0, "due": "2026-01-06"}


def test_due_persistence_and_mark(question, leet_home):
    h = History()
    h.record("two-sum", question, "submit", ACCEPTED, "python3", at=day(0))
    h.mark("car-fleet", None, at=day(3))
    h.save()

    h2 = History()
    assert h2.solved_slugs() == {"two-sum", "car-fleet"}
    assert [s for s, _ in h2.due(today=date(2026, 1, 1))] == []
    assert [s for s, _ in h2.due(today=date(2026, 1, 5))] == ["two-sum", "car-fleet"]
    assert h2.upcoming()[0] == "two-sum"

    h2.mark("car-fleet", None, solved=False)
    assert not h2.is_solved("car-fleet") and h2.get("car-fleet")["review"] is None


def test_summary_and_streak(question):
    h = History()
    h.record("two-sum", question, "submit", WRONG, "python3", at=day(0))
    h.record("two-sum", question, "submit", ACCEPTED, "python3", elapsed=600, at=day(0))
    hard = dict(question, title="Trap", difficulty="Hard", topicTags=[{"name": "Stack"}])
    h.record("trap", hard, "submit", ACCEPTED, "python3", elapsed=1800, at=day(1))

    s = h.summary()
    assert s["solved"] == 2 and s["submits"] == 3 and s["accepted"] == 2
    assert s["by_difficulty"] == {"Easy": 1, "Hard": 1}
    assert s["avg_time"] == {"Easy": 600, "Hard": 1800}
    assert s["tags"]["Array"] == 1 and s["tags"]["Stack"] == 1

    assert h.streak(today=date(2026, 1, 2)) == 2
    assert h.streak(today=date(2026, 1, 3)) == 2   # nothing today yet: yesterday keeps it alive
    assert h.streak(today=date(2026, 1, 4)) == 0
