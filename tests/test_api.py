"""API client tests with a fake HTTP session — no network."""
import pytest

from leet import api
from leet import config as cfg
from leet.api import AuthError, LeetCodeClient, LeetCodeError


class FakeResp:
    def __init__(self, data=None, status=200, url="https://leetcode.com/x"):
        self._data, self.status_code, self.url = data or {}, status, url

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, posts, gets=()):
        self.posts, self.gets = list(posts), list(gets)
        self.post_calls, self.get_calls = [], []

    def post(self, url, **kw):
        self.post_calls.append((url, kw))
        return self.posts.pop(0)

    def get(self, url, **kw):
        self.get_calls.append(url)
        return self.gets.pop(0)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(api.time, "sleep", lambda s: None)


def client_with(posts, gets=(), auth=True):
    c = LeetCodeClient("sess", "csrf") if auth else LeetCodeClient()
    c._session = FakeSession(posts, gets)
    return c


def test_get_question_caches(question):
    c = client_with([FakeResp({"data": {"question": dict(question)}})])
    q = c.get_question("https://leetcode.com/problems/two-sum/")
    assert q["slug"] == "two-sum"
    assert (cfg.cache_dir() / "two-sum.json").exists()
    assert c.get_question("two-sum")["title"] == "Two Sum"  # served from cache
    assert len(c._session.post_calls) == 1


def test_premium_not_cached_and_missing_raises(question):
    c = client_with([
        FakeResp({"data": {"question": dict(question, content=None)}}),
        FakeResp({"data": {"question": None}}),
    ])
    assert c.get_question("two-sum")["content"] is None
    assert not (cfg.cache_dir() / "two-sum.json").exists()
    with pytest.raises(LeetCodeError, match="not found"):
        c.get_question("nope")


def test_run_polls_and_reports_progress(question):
    c = client_with(
        [FakeResp({"interpret_id": "abc"})],
        [FakeResp({"state": "PENDING"}), FakeResp({"state": "SUCCESS", "run_success": True})],
    )
    ticks = []
    result = c.run(question, "code", "cpp", "[1]\n2", on_tick=ticks.append)
    assert result["run_success"]
    url, kw = c._session.post_calls[0]
    assert url.endswith("/problems/two-sum/interpret_solution/")
    assert kw["json"] == {"lang": "cpp", "question_id": "1", "typed_code": "code", "data_input": "[1]\n2"}
    assert len(ticks) == 2 and c._session.get_calls[0].endswith("/submissions/detail/abc/check/")


def test_submit(question):
    c = client_with([FakeResp({"submission_id": 42})], [FakeResp({"state": "SUCCESS", "status_msg": "Accepted"})])
    assert c.submit(question, "code", "python3")["status_msg"] == "Accepted"
    assert "data_input" not in c._session.post_calls[0][1]["json"]


@pytest.mark.parametrize("resp", [
    FakeResp(status=403),
    FakeResp(status=401),
    FakeResp(url="https://leetcode.com/accounts/login/?next=/problems/two-sum/"),
])
def test_expired_session_raises_auth_error(question, resp):
    with pytest.raises(AuthError):
        client_with([resp]).submit(question, "code", "python3")


def test_rate_limit_and_missing_auth(question):
    with pytest.raises(LeetCodeError, match="rate-limiting"):
        client_with([FakeResp(status=429)]).submit(question, "x", "python3")
    with pytest.raises(AuthError, match="lc config"):
        client_with([], auth=False).run(question, "x", "python3", "")


def test_poll_timeout(question):
    c = client_with([], [FakeResp({"state": "PENDING"})] * 5)
    with pytest.raises(TimeoutError):
        c._poll("1", "two-sum", max_wait=0.0)


def test_daily_and_whoami():
    c = client_with([
        FakeResp({"data": {"activeDailyCodingChallengeQuestion": {"question": {"titleSlug": "lru-cache"}}}}),
        FakeResp({"data": {"userStatus": {"isSignedIn": True, "username": "me"}}}),
        FakeResp({"data": {"userStatus": {"isSignedIn": False, "username": ""}}}),
    ])
    assert c.daily_slug() == "lru-cache"
    assert c.whoami() == "me"
    assert c.whoami() is None
