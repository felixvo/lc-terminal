"""Local runner tests. These spawn real Python subprocesses (no network)."""
import json
import textwrap

import pytest
from click.testing import CliRunner

from leet import config as cfg
from leet import languages, local, templates
from leet.cli import cli
from leet.local import LocalCase, compare

PY = languages.resolve("python3")


def problem(name, params, ret, examples, outputs, **extra):
    meta = {"name": name, "params": [{"name": n, "type": t} for n, t in params], "return": {"type": ret}, **extra}
    content = "".join(f"<p><strong>Output:</strong> {o}</p>" for o in outputs)
    return {"slug": name, "title": name, "questionId": "1", "questionFrontendId": "1", "difficulty": "Easy",
            "content": content, "metaData": json.dumps(meta), "exampleTestcaseList": examples}


def solution(tmp_path, code):
    path = tmp_path / "sol.py"
    path.write_text(textwrap.dedent(code))
    return path


def run(q, path, timeout=10.0):
    cases, leftover = local.build_cases(q, path.read_text(), PY)
    assert not leftover
    return local.run(q, path, cases, timeout=timeout)


TWO_SUM = problem("twoSum", [("nums", "integer[]"), ("target", "integer")], "integer[]",
                  ["[2,7,11,15]\n9", "[3,2,4]\n6", "[3,3]\n6"], ["[0,1]", "[1,2]", "[0,1]"])


def test_two_sum_passes_with_custom_tests_and_stdout(tmp_path):
    path = solution(tmp_path, """
        # @tests
        # [1,5,9]
        # 14
        # => [1,2]
        # [0,4]
        # 4
        # @end
        class Solution:
            def twoSum(self, nums: List[int], target: int) -> List[int]:
                seen = {}
                for i, n in enumerate(nums):
                    if target - n in seen:
                        print("found", n)
                        return [seen[target - n], i]
                    seen[n] = i
    """)
    report = run(TWO_SUM, path)
    assert [r.verdict for r in report.results] == ["pass", "pass", "pass", "pass", "none"]
    assert report.results[0].stdout == "found 7\n"
    assert report.results[4].output == "[0,1]"
    assert report.all_passed


def test_wrong_answer_and_exception(tmp_path):
    path = solution(tmp_path, """
        class Solution:
            def twoSum(self, nums, target):
                if target == 6:
                    raise ValueError("boom")
                return [1, 0]
    """)
    report = run(TWO_SUM, path)
    assert [r.verdict for r in report.results] == ["order", "error", "error"]
    assert "ValueError: boom" in report.results[1].error
    assert "sol.py" in report.results[1].error and "local_runner" not in report.results[1].error
    assert not report.all_passed


def test_syntax_error_reports_load_failure(tmp_path):
    path = solution(tmp_path, "class Solution:\n    def twoSum(self, nums, target)\n        pass\n")
    report = run(TWO_SUM, path)
    assert report.load_error and "SyntaxError" in report.load_error


def test_infinite_loop_times_out(tmp_path):
    path = solution(tmp_path, """
        class Solution:
            def twoSum(self, nums, target):
                if target == 6:
                    while True:
                        pass
                return [0, 1]
    """)
    report = run(TWO_SUM, path, timeout=2)
    assert report.timed_out
    assert [r.verdict for r in report.results] == ["pass", "timeout", "skipped"]


def test_linked_lists(tmp_path):
    q = problem("mergeTwoLists", [("list1", "ListNode"), ("list2", "ListNode")], "ListNode",
                ["[1,2,4]\n[1,3,4]", "[]\n[]", "[]\n[0]"], ["[1,1,2,3,4,4]", "[]", "[0]"])
    path = solution(tmp_path, """
        class Solution:
            def mergeTwoLists(self, a: Optional[ListNode], b: Optional[ListNode]) -> Optional[ListNode]:
                head = cur = ListNode()
                while a and b:
                    if a.val <= b.val:
                        cur.next, a = a, a.next
                    else:
                        cur.next, b = b, b.next
                    cur = cur.next
                cur.next = a or b
                return head.next
    """)
    assert [r.verdict for r in run(q, path).results] == ["pass", "pass", "pass"]


def test_linked_list_cycle_hidden_pos(tmp_path):
    q = problem("hasCycle", [("head", "ListNode"), ("pos", "integer")], "boolean",
                ["[3,2,0,-4]\n1", "[1,2]\n0", "[1]\n-1"], ["true", "true", "false"])
    path = solution(tmp_path, """
        class Solution:
            def hasCycle(self, head: Optional[ListNode]) -> bool:
                slow = fast = head
                while fast and fast.next:
                    slow, fast = slow.next, fast.next.next
                    if slow is fast:
                        return True
                return False
    """)
    assert [r.verdict for r in run(q, path).results] == ["pass", "pass", "pass"]


def test_trees(tmp_path):
    q = problem("invertTree", [("root", "TreeNode")], "TreeNode",
                ["[4,2,7,1,3,6,9]", "[2,1,3]", "[]"], ["[4,7,2,9,6,3,1]", "[2,3,1]", "[]"])
    path = solution(tmp_path, """
        class Solution:
            def invertTree(self, root):
                if root:
                    root.left, root.right = self.invertTree(root.right), self.invertTree(root.left)
                return root
    """)
    assert [r.verdict for r in run(q, path).results] == ["pass", "pass", "pass"]


def test_void_in_place(tmp_path):
    q = problem("rotate", [("nums", "integer[]"), ("k", "integer")], "void",
                ["[1,2,3,4,5,6,7]\n3", "[-1,-100,3,99]\n2"], ["[5,6,7,1,2,3,4]", "[3,99,-1,-100]"],
                output={"paramindex": 0})
    path = solution(tmp_path, """
        class Solution:
            def rotate(self, nums: List[int], k: int) -> None:
                k %= len(nums)
                nums[:] = nums[-k:] + nums[:-k]
    """)
    assert [r.verdict for r in run(q, path).results] == ["pass", "pass"]


def test_design_problem(tmp_path):
    q = {"slug": "lru-cache", "metaData": json.dumps({"classname": "LRUCache", "systemdesign": True}),
         "content": "<p><strong>Output</strong></p><pre>[null, null, null, 1, null, -1]</pre>",
         "exampleTestcaseList": ['["LRUCache","put","put","get","put","get"]\n[[2],[1,1],[2,2],[1],[3,3],[2]]']}
    q["content"] = "<p><strong>Output:</strong> [null, null, null, 1, null, -1]</p>"
    path = solution(tmp_path, """
        class LRUCache:
            def __init__(self, capacity: int):
                self.cap, self.d = capacity, OrderedDict()
            def get(self, key: int) -> int:
                if key not in self.d:
                    return -1
                self.d.move_to_end(key)
                return self.d[key]
            def put(self, key: int, value: int) -> None:
                self.d[key] = value
                self.d.move_to_end(key)
                if len(self.d) > self.cap:
                    self.d.popitem(last=False)
    """)
    report = run(q, path)
    assert [r.verdict for r in report.results] == ["pass"], report.results[0]


def test_compare():
    assert compare("[0,1]", "[0, 1]") == "pass"
    assert compare("2.0", "2.00000") == "pass"
    assert compare("2.5", "2.00000") == "fail"
    assert compare('[["tan","nat"],["bat"]]', '[["bat"],["nat","tan"]]') == "order"
    assert compare("true", "true") == "pass" and compare("1", "true") == "fail"
    assert compare("[1]", None) == "none" and compare(None, "[1]") == "fail"


def test_custom_cases_with_expected():
    cases, leftover = templates.custom_cases(["[1]", "2", "=> 3", "[4]", "5", "=> 9", "=> ignored", "[7]"], 2)
    assert cases == [("[1]\n2", "3"), ("[4]\n5", "9")] and leftover == ["[7]"]


def test_example_outputs_must_line_up():
    assert templates.example_outputs(TWO_SUM) == ["[0,1]", "[1,2]", "[0,1]"]
    assert templates.example_outputs(dict(TWO_SUM, exampleTestcaseList=["x"])) is None


def test_lc_test_command(tmp_path):
    cfg.cache_dir().mkdir(parents=True)
    (cfg.cache_dir() / "twoSum.json").write_text(json.dumps(TWO_SUM))
    good = solution(tmp_path, "class Solution:\n    def twoSum(self, nums, target):\n"
                              "        return [i for i in range(len(nums)) for j in range(i) if nums[i]+nums[j]==target][:0] or "
                              "next([j, i] for i in range(len(nums)) for j in range(i) if nums[i]+nums[j]==target)\n")
    result = CliRunner().invoke(cli, ["test", "twoSum", str(good)], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Local: 3/3 passed" in result.output

    bad = tmp_path / "bad.py"
    bad.write_text("class Solution:\n    def twoSum(self, nums, target):\n        return [9, 9]\n")
    result = CliRunner().invoke(cli, ["test", "twoSum", str(bad)], catch_exceptions=False)
    assert result.exit_code == 1 and "Local: 0/3 passed" in result.output

    cpp = tmp_path / "sol.cpp"
    cpp.write_text("class Solution {};")
    result = CliRunner().invoke(cli, ["test", "twoSum", str(cpp)], catch_exceptions=False)
    assert result.exit_code == 1 and "Python only" in result.output


def test_solve_flow_offers_local_test_without_login(tmp_path, monkeypatch):
    cfg.cache_dir().mkdir(parents=True)
    q = dict(TWO_SUM, codeSnippets=[{"langSlug": "python3", "code":
             "class Solution:\n    def twoSum(self, nums: List[int], target: int) -> List[int]:\n"
             "        return next([j, i] for i in range(len(nums)) for j in range(i) if nums[i] + nums[j] == target)\n"}])
    (cfg.cache_dir() / "twoSum.json").write_text(json.dumps(q))
    cfg.update(solutions_dir=str(tmp_path / "sol"), editor="true")
    result = CliRunner().invoke(cli, ["solve", "twoSum"], input="test\nquit\n", catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "local testing only" in result.output
    assert "[test/edit/hints/quit]" in result.output      # run/submit hidden without login
    assert "Local: 3/3 passed" in result.output
    assert (tmp_path / "sol" / "twoSum.py").exists()


def test_unfinished_solution_hint(tmp_path):
    path = solution(tmp_path, "class Solution:\n    def twoSum(self, nums, target):\n")
    cfg.cache_dir().mkdir(parents=True)
    (cfg.cache_dir() / "twoSum.json").write_text(json.dumps(TWO_SUM))
    result = CliRunner().invoke(cli, ["test", "twoSum", str(path)], catch_exceptions=False)
    assert result.exit_code == 1 and "isn't written yet" in result.output
