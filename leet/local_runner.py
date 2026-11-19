"""Run a LeetCode-style Python solution locally.

Standalone on purpose (imports nothing from `leet`). `lc test` runs it in a child process:

    python local_runner.py <spec.json> <results.json>

spec:    {"code_path": str, "meta": <LeetCode metaData>, "cases": ["line1\\nline2", ...]}
results: [{"output": str | None, "stdout": str, "error": str | None, "ms": float}, ...]
         rewritten after every case, so a timeout still leaves the finished cases.
"""
from __future__ import annotations

import ast
import contextlib
import inspect
import io
import json
import os
import sys
import time
import traceback

# Don't let modules next to this file shadow anything the solution imports.
_here = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _here]
sys.setrecursionlimit(100_000)

# What LeetCode's Python 3 environment pre-imports.
PRELUDE = """
from typing import *
import collections, heapq, math, bisect, itertools, functools, string, re, random, operator, sys
from collections import *
from heapq import *
from bisect import *
from functools import *
from itertools import *
from math import *
"""


class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next


class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right


# ─── LeetCode value <-> Python ────────────────────────────────────────────────

def parse_value(text: str):
    text = text.strip()
    try:
        return json.loads(text)
    except ValueError:
        fixed = text.replace("true", "True").replace("false", "False").replace("null", "None")
        return ast.literal_eval(fixed)


def to_list_node(values):
    head = cur = ListNode()
    for v in values or []:
        cur.next = ListNode(v)
        cur = cur.next
    return head.next


def from_list_node(node, limit=100_000):
    out = []
    while node is not None and len(out) < limit:
        out.append(node.val)
        node = node.next
    return out


def to_tree_node(values):
    if not values or values[0] is None:
        return None
    root = TreeNode(values[0])
    queue, i = [root], 1
    for node in queue:
        if i >= len(values):
            break
        if i < len(values) and values[i] is not None:
            node.left = TreeNode(values[i])
            queue.append(node.left)
        i += 1
        if i < len(values) and values[i] is not None:
            node.right = TreeNode(values[i])
            queue.append(node.right)
        i += 1
    return root


def from_tree_node(root):
    out, queue = [], [root]
    for node in queue:
        if node is None:
            out.append(None)
        else:
            out.append(node.val)
            queue.extend([node.left, node.right])
    while out and out[-1] is None:
        out.pop()
    return out


def convert_in(value, typ: str):
    if typ == "ListNode":
        return to_list_node(value)
    if typ == "TreeNode":
        return to_tree_node(value)
    if typ == "ListNode[]":
        return [to_list_node(v) for v in value]
    if typ == "TreeNode[]":
        return [to_tree_node(v) for v in value]
    return value


def serialize(value, typ: str = "") -> str:
    if isinstance(value, ListNode):
        value = from_list_node(value)
    elif isinstance(value, TreeNode):
        value = from_tree_node(value)
    elif isinstance(value, list) and value and isinstance(value[0], (ListNode, TreeNode)):
        value = [from_list_node(v) if isinstance(v, ListNode) else from_tree_node(v) for v in value]
    if typ == "double" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.5f}"
    if value is None and typ in ("ListNode", "TreeNode"):
        return "[]"
    return json.dumps(value, separators=(",", ":"), default=lambda o: sorted(o) if isinstance(o, set) else list(o))


# ─── Running ──────────────────────────────────────────────────────────────────

def run_case(ns: dict, meta: dict, case: str):
    lines = [l for l in case.split("\n") if l.strip()]

    if meta.get("classname"):  # design problem: [methods], [args]
        methods, args = parse_value(lines[0]), parse_value(lines[1])
        cls = ns[meta["classname"]]
        obj = cls(*args[0])
        outputs = [None]
        for name, a in zip(methods[1:], args[1:]):
            outputs.append(getattr(obj, name)(*a))
        return serialize(outputs)

    params = meta.get("params") or []
    if len(lines) != len(params):
        raise ValueError(f"expected {len(params)} input line(s) (one per parameter), got {len(lines)}")
    args = [convert_in(parse_value(line), p.get("type", "")) for line, p in zip(lines, params)]
    if "Solution" not in ns:
        raise NameError("no `class Solution` found in your file")
    method = getattr(ns["Solution"](), meta["name"])
    args = _apply_hidden_params(method, params, args)
    result = method(*args)

    ret = (meta.get("return") or {}).get("type", "")
    if ret == "void":  # in-place: the answer is the modified parameter
        idx = (meta.get("output") or {}).get("paramindex", 0)
        return serialize(args[idx], params[idx].get("type", ""))
    return serialize(result, ret)


def _apply_hidden_params(method, params: list, args: list) -> list:
    """Inputs that aren't method arguments, e.g. `pos` in Linked List Cycle (tail links to node `pos`)."""
    try:
        accepted = len(inspect.signature(method).parameters)
    except (TypeError, ValueError):
        return args
    if accepted >= len(args):
        return args
    for i in range(accepted, len(args)):
        if params[i].get("name") == "pos" and isinstance(args[0], ListNode) and args[i] >= 0:
            nodes, node = [], args[0]
            while node:
                nodes.append(node)
                node = node.next
            if args[i] < len(nodes):
                nodes[-1].next = nodes[args[i]]
    return args[:accepted]


def _user_traceback(code_path: str) -> str:
    """Traceback limited to frames from the user's file."""
    etype, value, tb = sys.exc_info()
    frames = [f for f in traceback.extract_tb(tb) if f.filename == code_path]
    lines = traceback.format_list(frames) if frames else []
    return "".join(lines + traceback.format_exception_only(etype, value)).rstrip()


def main(spec_path: str, results_path: str) -> None:
    with open(spec_path) as f:
        spec = json.load(f)
    code_path, meta, cases = spec["code_path"], spec["meta"], spec["cases"]
    results: list[dict] = []

    def flush():
        with open(results_path, "w") as f:
            json.dump(results, f)

    ns: dict = {"__name__": "solution", "ListNode": ListNode, "TreeNode": TreeNode}
    exec(PRELUDE, ns)
    try:
        with open(code_path) as f:
            source = f.read()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            exec(compile(source, code_path, "exec"), ns)
    except BaseException:
        results.append({"output": None, "stdout": "", "error": _user_traceback(code_path), "ms": 0, "load": True})
        flush()
        return

    for case in cases:
        out = io.StringIO()
        start = time.perf_counter()
        entry: dict = {"output": None, "stdout": "", "error": None}
        try:
            with contextlib.redirect_stdout(out):
                entry["output"] = run_case(ns, meta, case)
        except RecursionError:
            entry["error"] = "RecursionError: maximum recursion depth exceeded"
        except BaseException:
            entry["error"] = _user_traceback(code_path)
        entry["ms"] = (time.perf_counter() - start) * 1000
        entry["stdout"] = out.getvalue()
        results.append(entry)
        flush()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
