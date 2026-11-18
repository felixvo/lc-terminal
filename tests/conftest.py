import pytest


@pytest.fixture(autouse=True)
def leet_home(tmp_path, monkeypatch):
    """Every test gets its own empty ~/.leet."""
    home = tmp_path / "leet-home"
    monkeypatch.setenv("LEET_HOME", str(home))
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.delenv("VISUAL", raising=False)
    return home


@pytest.fixture
def question():
    return {
        "questionId": "1",
        "questionFrontendId": "1",
        "title": "Two Sum",
        "slug": "two-sum",
        "difficulty": "Easy",
        "content": "<p>Given an array <code>nums</code>, return indices.</p>"
                   "<p><strong class=\"example\">Example 1:</strong></p>"
                   "<pre><strong>Input:</strong> nums = [2,7], target = 9\n<strong>Output:</strong> [0,1]</pre>"
                   "<ul><li><code>2 &lt;= nums.length &lt;= 10<sup>4</sup></code></li></ul>",
        "topicTags": [{"name": "Array"}, {"name": "Hash Table"}],
        "codeSnippets": [
            {"lang": "Python3", "langSlug": "python3", "code": "class Solution:\n    def twoSum(self, nums, target):\n        "},
            {"lang": "C++", "langSlug": "cpp", "code": "class Solution {\n};"},
        ],
        "exampleTestcaseList": ["[2,7,11,15]\n9", "[3,2,4]\n6"],
        "sampleTestCase": "[2,7,11,15]\n9",
        "metaData": '{"name": "twoSum", "params": [{"name": "nums"}, {"name": "target"}]}',
        "hints": ["Use a <b>hash map</b>."],
    }
