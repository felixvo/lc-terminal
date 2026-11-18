"""LeetCode API client — GraphQL + REST.

Auth: LEETCODE_SESSION + csrftoken cookies from your browser.
Fetched problems are cached in ~/.leet/cache/<slug>.json.
"""
from __future__ import annotations

import time
from typing import Callable

import requests

from . import config as cfg
from .util import slug_from_url

BASE_URL = "https://leetcode.com"
GRAPHQL_URL = f"{BASE_URL}/graphql"

QUESTION_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    questionFrontendId
    title
    titleSlug
    content
    difficulty
    isPaidOnly
    topicTags { name }
    codeSnippets { lang langSlug code }
    exampleTestcaseList
    sampleTestCase
    metaData
    hints
  }
}
"""

DAILY_QUERY = """
query questionOfToday {
  activeDailyCodingChallengeQuestion { date question { titleSlug } }
}
"""

STATUS_QUERY = "query globalData { userStatus { isSignedIn username } }"

Tick = Callable[[float], None]


class LeetCodeError(RuntimeError):
    pass


class AuthError(LeetCodeError):
    """LeetCode rejected the session cookies (missing, invalid or expired)."""


class LeetCodeClient:
    def __init__(self, session_cookie: str = "", csrf_token: str = "", use_cache: bool = True):
        self.session_cookie = session_cookie
        self.csrf_token = csrf_token
        self.use_cache = use_cache
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Content-Type": "application/json",
            "Origin": BASE_URL,
        })
        if session_cookie:
            self._session.cookies.set("LEETCODE_SESSION", session_cookie, domain="leetcode.com")
        if csrf_token:
            self._session.cookies.set("csrftoken", csrf_token, domain="leetcode.com")
            self._session.headers["X-CSRFToken"] = csrf_token

    @classmethod
    def from_config(cls) -> "LeetCodeClient":
        return cls(cfg.get("session") or "", cfg.get("csrf") or "")

    # ── plumbing ──────────────────────────────────────────────────────────────

    def _require_auth(self) -> None:
        if not self.session_cookie or not self.csrf_token:
            raise AuthError("No LeetCode login configured. Run: lc config")

    @staticmethod
    def _check(resp: requests.Response) -> None:
        if resp.status_code in (401, 403) or "/accounts/login" in (resp.url or ""):
            raise AuthError("LeetCode rejected your session cookies.")
        if resp.status_code == 429:
            raise LeetCodeError("LeetCode is rate-limiting you. Wait a few seconds and try again.")
        resp.raise_for_status()

    def _graphql(self, query: str, variables: dict | None = None,
                 operation: str | None = None, referer: str = BASE_URL) -> dict:
        payload: dict = {"query": query, "variables": variables or {}}
        if operation:
            payload["operationName"] = operation
        resp = self._session.post(GRAPHQL_URL, json=payload, headers={"Referer": referer}, timeout=15)
        self._check(resp)
        return resp.json().get("data") or {}

    # ── problems ──────────────────────────────────────────────────────────────

    def cached_question(self, url_or_slug: str) -> dict | None:
        return cfg.read_json(cfg.cache_dir() / f"{slug_from_url(url_or_slug)}.json", None)

    def get_question(self, url_or_slug: str, refresh: bool = False) -> dict:
        slug = slug_from_url(url_or_slug)
        if self.use_cache and not refresh:
            cached = self.cached_question(slug)
            if cached:
                return cached

        data = self._graphql(QUESTION_QUERY, {"titleSlug": slug}, "questionData",
                             referer=f"{BASE_URL}/problems/{slug}/")
        q = data.get("question")
        if not q:
            raise LeetCodeError(f"Question '{slug}' not found.")
        q["slug"] = slug
        if self.use_cache and q.get("content"):  # don't cache premium stubs
            cfg.write_json(cfg.cache_dir() / f"{slug}.json", q)
        return q

    def daily_slug(self) -> str:
        data = self._graphql(DAILY_QUERY, operation="questionOfToday")
        try:
            return data["activeDailyCodingChallengeQuestion"]["question"]["titleSlug"]
        except (KeyError, TypeError):
            raise LeetCodeError("Couldn't get today's daily challenge.") from None

    def whoami(self) -> str | None:
        status = self._graphql(STATUS_QUERY).get("userStatus") or {}
        return status.get("username") if status.get("isSignedIn") else None

    # ── run / submit ──────────────────────────────────────────────────────────

    def run(self, q: dict, code: str, lang: str, data_input: str, on_tick: Tick | None = None) -> dict:
        """Run code against the given test input (no submission count)."""
        slug = q["slug"]
        data = self._authed_post(
            f"{BASE_URL}/problems/{slug}/interpret_solution/",
            {"lang": lang, "question_id": str(q["questionId"]), "typed_code": code, "data_input": data_input},
            slug,
        )
        check_id = data.get("interpret_id")
        if not check_id:
            raise LeetCodeError(f"Unexpected response from LeetCode: {str(data)[:200]}")
        return self._poll(str(check_id), slug, on_tick)

    def submit(self, q: dict, code: str, lang: str, on_tick: Tick | None = None) -> dict:
        """Submit a solution (counts as a submission)."""
        slug = q["slug"]
        data = self._authed_post(
            f"{BASE_URL}/problems/{slug}/submit/",
            {"lang": lang, "question_id": str(q["questionId"]), "typed_code": code},
            slug,
        )
        check_id = data.get("submission_id")
        if not check_id:
            raise LeetCodeError(f"Unexpected response from LeetCode: {str(data)[:200]}")
        return self._poll(str(check_id), slug, on_tick)

    def _authed_post(self, url: str, payload: dict, slug: str) -> dict:
        self._require_auth()
        resp = self._session.post(url, json=payload, timeout=20,
                                  headers={"Referer": f"{BASE_URL}/problems/{slug}/"})
        self._check(resp)
        return resp.json()

    def _poll(self, check_id: str, slug: str, on_tick: Tick | None = None,
              max_wait: float = 60.0, interval: float = 1.0) -> dict:
        url = f"{BASE_URL}/submissions/detail/{check_id}/check/"
        start = time.monotonic()
        while time.monotonic() - start < max_wait:
            time.sleep(interval)
            if on_tick:
                on_tick(time.monotonic() - start)
            resp = self._session.get(url, timeout=10, headers={"Referer": f"{BASE_URL}/problems/{slug}/"})
            self._check(resp)
            data = resp.json()
            if data.get("state") == "SUCCESS":
                return data
        raise TimeoutError(f"LeetCode didn't return a result within {max_wait:.0f}s.")
