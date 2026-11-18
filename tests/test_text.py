import pytest

from leet import languages, templates
from leet.display import html_to_md
from leet.util import fmt_duration, slug_from_url


@pytest.mark.parametrize("raw, slug", [
    ("two-sum", "two-sum"),
    ("  Two-Sum  ", "two-sum"),
    ("https://leetcode.com/problems/two-sum/", "two-sum"),
    ("https://leetcode.com/problems/two-sum", "two-sum"),
    ("https://leetcode.com/problems/two-sum/description/?envType=study", "two-sum"),
    ("leetcode.com/problems/valid-parentheses/solutions/", "valid-parentheses"),
])
def test_slug_from_url(raw, slug):
    assert slug_from_url(raw) == slug


def test_fmt_duration():
    assert fmt_duration(None) == "—"
    assert fmt_duration(42) == "42s"
    assert fmt_duration(723) == "12m 03s"
    assert fmt_duration(3 * 3600 + 5 * 60) == "3h 05m"


def test_html_to_md_headings_bold_and_pre(question):
    md = html_to_md(question["content"])
    assert "### Example 1:" in md
    assert "`nums`" in md
    # tags inside <pre> become plain text, not markdown bold
    assert "```\nInput: nums = [2,7], target = 9\nOutput: [0,1]\n```" in md
    assert "10^4" in md and "<=" in md


def test_html_to_md_current_leetcode_markup():
    content = (
        '<p><strong class="example">Example 1:</strong></p>\n'
        '<div class="example-block">\n'
        '<p><strong>Input:</strong> <span class="example-io">target = 12</span></p>\n\n'
        '<p><strong>Output:</strong> <span class="example-io">3</span></p>\n\n'
        '<p><strong>Explanation:</strong></p>\n\n'
        '<ul>\n\t<li>The cars at <code>10</code> meet.</li>\n</ul>\n</div>'
    )
    md = html_to_md(content)
    assert "**Input:** target = 12" in md
    assert "**Output:** 3" in md
    assert "### Explanation:" in md
    assert "\n- The cars at `10` meet." in md  # not indented into a code block
    assert md.count("**") == 4


def test_html_to_md_plain_heading_and_inline_bold():
    assert html_to_md("<p><strong>Example 1:</strong></p><p>x <strong>b</strong></p>") == "### Example 1:\n\nx **b**"
    assert html_to_md(None) == ""


def test_languages():
    assert languages.resolve("py").slug == "python3"
    assert languages.resolve("C++").ext == ".cpp"
    assert languages.resolve("go").slug == "golang"
    assert languages.from_path("x/two-sum.rs").slug == "rust"
    assert languages.from_path("notes.txt") is None
    with pytest.raises(ValueError):
        languages.resolve("cobol")


def test_template_python(question):
    lang = languages.resolve("python3")
    code = templates.starter_code(question, lang)
    text = templates.build_template(question, code, lang)
    assert text.startswith("# 1. Two Sum\n# Difficulty: Easy\n# https://leetcode.com/problems/two-sum/")
    assert "# @tests" in text and "# @end" in text
    assert text.rstrip().endswith("def twoSum(self, nums, target):")
    assert all(len(line) <= 120 for line in text.splitlines())
    assert templates.parse_custom_tests(text, lang) == []
    assert "# - 2 <= nums.length <= 10^4" in text


def test_template_cpp_uses_slash_comments(question):
    lang = languages.resolve("cpp")
    text = templates.build_template(question, templates.starter_code(question, lang), lang)
    assert text.startswith("// 1. Two Sum")
    assert "// @tests" in text
    assert templates.starter_code(question, languages.resolve("rust")) is None


def test_parse_custom_tests():
    lang = languages.resolve("python3")
    src = "# header\n# @tests — note\n# [1,2]\n#\n# 3\n# @end\n# [9]\nclass Solution: ..."
    assert templates.parse_custom_tests(src, lang) == ["[1,2]", "3"]
    # unterminated block stops at the first code line
    assert templates.parse_custom_tests("# @tests\n# [1]\nx = 1\n# [2]", lang) == ["[1]"]


def test_case_grouping(question):
    per = templates.params_per_case(question)
    assert per == 2
    cases, leftover = templates.group_cases(["[1]", "1", "[2]", "2", "[3]"], per)
    assert cases == ["[1]\n1", "[2]\n2"] and leftover == ["[3]"]
    assert templates.params_per_case({"metaData": '{"classname": "LRUCache"}'}) == 2
    assert templates.params_per_case({"metaData": None}) == 1
    assert templates.example_cases(question) == ["[2,7,11,15]\n9", "[3,2,4]\n6"]
    assert templates.example_cases({"sampleTestCase": "x"}) == ["x"]
