"""Tests for the #Tests section runner.

run_tests() assembles a module, executes it, then evaluates every
assertion in the #Tests post-text section and returns ClaimResults.
"""

from pathlib import Path

from notlob import parse, parse_file, from_tree
from notlob.bindings.python.runner import ClaimResult, Status, run_tests


EXAMPLES = Path(__file__).parent.parent / "examples"


def ran(source: str) -> list[ClaimResult]:
    return run_tests(from_tree(parse(source)))


# ── Empty / absent #Tests ─────────────────────────────────────

class TestAbsent:
    def test_no_post_text(self):
        assert ran("#T\n    x = 1\n") == []

    def test_post_text_without_tests(self):
        src = "#T\n    x = 1\n---\n#References\n    import os\n"
        assert ran(src) == []

    def test_empty_tests_section(self):
        src = "#T\n    x = 1\n---\n#Tests\n"
        assert ran(src) == []


# ── Bare assertions (no ## group) ────────────────────────────

class TestBareAssertions:
    def test_bare_passing(self):
        src = "#T\n    x = 1\n---\n#Tests\n    x == 1\n"
        results = ran(src)
        assert len(results) == 1
        assert results[0].status == Status.PASS

    def test_bare_address(self):
        src = "#T\n    x = 1\n---\n#Tests\n    x == 1\n"
        assert ran(src)[0].address == "t#Tests"

    def test_bare_multiword_module_address(self):
        src = (
            "#Roman Numerals\n"
            "    x = 1\n"
            "---\n"
            "#Tests\n"
            "    x == 1\n"
        )
        assert ran(src)[0].address == "roman/numerals#Tests"

    def test_bare_failing(self):
        src = "#T\n    x = 2\n---\n#Tests\n    x == 1\n"
        result = ran(src)[0]
        assert result.status == Status.FAIL
        assert result.left == 2
        assert result.right == 1


# ── Named test groups ─────────────────────────────────────────

class TestGroups:
    def test_group_address(self):
        src = (
            "#T\n    x = 1\n"
            "---\n#Tests\n##basics\n    x == 1\n"
        )
        assert ran(src)[0].address == "t#Tests#basics"

    def test_group_with_spaces_in_title(self):
        src = (
            "#T\n    x = 1\n"
            "---\n#Tests\n##boundary conditions\n    x == 1\n"
        )
        assert ran(src)[0].address == "t#Tests#boundary conditions"

    def test_multiple_groups(self):
        src = (
            "#T\n    x = 1\n    y = 2\n"
            "---\n#Tests\n"
            "##a\n    x == 1\n"
            "##b\n    y == 2\n"
        )
        results = ran(src)
        assert results[0].address == "t#Tests#a"
        assert results[1].address == "t#Tests#b"

    def test_multiple_assertions_in_group(self):
        src = (
            "#T\n    def f(n): return n * 2\n"
            "---\n#Tests\n##doubles\n"
            "    f(1) == 2\n"
            "    f(2) == 4\n"
        )
        results = ran(src)
        assert len(results) == 2
        assert all(r.status == Status.PASS for r in results)


# ── Multi-line assertions ─────────────────────────────────────

class TestMultiLine:
    def test_multiline_in_group(self):
        src = (
            "#T\n    def f(a, b): return a + b\n"
            "---\n#Tests\n##sums\n"
            "    f(1,\n"
            "      2) == 3\n"
        )
        results = ran(src)
        assert len(results) == 1
        assert results[0].status == Status.PASS


# ── Bare lines before a group ─────────────────────────────────

class TestMixed:
    def test_bare_before_group(self):
        src = (
            "#T\n    x = 1\n    y = 2\n"
            "---\n#Tests\n"
            "    x == 1\n"
            "##group\n    y == 2\n"
        )
        results = ran(src)
        assert results[0].address == "t#Tests"
        assert results[1].address == "t#Tests#group"


# ── Integration: example files ────────────────────────────────

class TestExampleFiles:
    def _run(self, path):
        return run_tests(from_tree(parse_file(path)))

    def test_pricing_discounts_all_pass(self):
        results = self._run(EXAMPLES / "retail/pricing/discounts.lob")
        assert results, "expected assertions in #Tests"
        failures = [r for r in results if r.status != Status.PASS]
        assert failures == [], failures

    def test_pricing_discounts_group_addresses(self):
        results = self._run(EXAMPLES / "retail/pricing/discounts.lob")
        addrs = {r.address for r in results}
        assert "pricing/discounts#Tests#boundary conditions" in addrs
        assert "pricing/discounts#Tests#composition" in addrs

    def test_roman_numerals_all_pass(self):
        results = self._run(EXAMPLES / "roman/roman/numerals.lob")
        assert results, "expected assertions in #Tests"
        failures = [r for r in results if r.status != Status.PASS]
        assert failures == [], failures

    def test_roman_numerals_group_addresses(self):
        results = self._run(EXAMPLES / "roman/roman/numerals.lob")
        addrs = {r.address for r in results}
        assert "roman/numerals#Tests#encoding"   in addrs
        assert "roman/numerals#Tests#decoding"   in addrs
        assert "roman/numerals#Tests#round-trip" in addrs
