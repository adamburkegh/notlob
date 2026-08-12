"""Tests for the #Tests section runner.

run_tests() assembles a module, executes it, then evaluates every
assertion in the #Tests post-text section and returns ClaimResults.
"""

from pathlib import Path

from notlob import parse, parse_file, from_tree
from notlob.bindings.python.harness import build_tests_harness
from notlob.bindings.python.runner import (
    ClaimResult, Status, run_tests,
)


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
        assert "pricing/discounts#Tests#composition#composition_is_commutative" in addrs

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


# ── Keep-dir: _tests.py contains assert statements ────────────

class TestKeepDirTests:
    def _src(self):
        return "#T\n    x = 1\n---\n#Tests\n    x == 1\n"

    def test_tests_py_contains_check_call(self, tmp_path):
        module = from_tree(parse(self._src()))
        run_tests(module, keep_dir=tmp_path)
        content = (tmp_path / "_tests.py").read_text(encoding="utf-8")
        assert "'x == 1'" in content

    def test_tests_py_contains_module_code(self, tmp_path):
        module = from_tree(parse(self._src()))
        run_tests(module, keep_dir=tmp_path)
        content = (tmp_path / "_tests.py").read_text(encoding="utf-8")
        assert "x = 1" in content

    def test_tests_py_bare_address(self, tmp_path):
        module = from_tree(parse(self._src()))
        run_tests(module, keep_dir=tmp_path)
        content = (tmp_path / "_tests.py").read_text(encoding="utf-8")
        assert "'t#Tests'" in content

    def test_tests_py_group_address(self, tmp_path):
        src = "#T\n    x = 1\n---\n#Tests\n##basics\n    x == 1\n"
        module = from_tree(parse(src))
        run_tests(module, keep_dir=tmp_path)
        content = (tmp_path / "_tests.py").read_text(encoding="utf-8")
        assert "'t#Tests#basics'" in content

    def test_tests_py_is_executable(self, tmp_path):
        module = from_tree(parse(self._src()))
        run_tests(module, keep_dir=tmp_path)
        kept = (tmp_path / "_tests.py").read_text(encoding="utf-8")
        exec(compile(kept, "_tests.py", "exec"), {})

    def test_no_keep_dir_no_file_written(self, tmp_path):
        module = from_tree(parse(self._src()))
        run_tests(module, keep_dir=None)
        assert not list(tmp_path.iterdir())


# ── build_tests_harness unit tests ───────────────────────────

class TestBuildTestsHarness:
    def test_bare_assertion(self):
        result = build_tests_harness(
            "x = 1", [("t#Tests", "x == 1", 1)],
        )
        assert "_notlob_check('t#Tests', 1, 'x == 1')" in result

    def test_grouped_assertion(self):
        result = build_tests_harness(
            "x = 1", [("t#Tests#grp", "x == 1", 1)],
        )
        assert "_notlob_check('t#Tests#grp', 1, 'x == 1')" in result

    def test_pytest_import_present(self):
        result = build_tests_harness("x = 1", [("t#Tests", "x == 1", 1)])
        assert "import pytest" in result

    def test_no_fallback_path_by_default(self):
        result = build_tests_harness("x = 1", [("t#Tests", "x == 1", 1)])
        assert "sys.path.append" not in result

    def test_fallback_path_appended_when_given(self):
        result = build_tests_harness(
            "x = 1", [("t#Tests", "x == 1", 1)],
            notlob_site_packages="/fake/site-packages",
        )
        assert "_notlob_sys.path.append('/fake/site-packages')" in result

    def test_fallback_path_before_pytest_import(self):
        # Must be set up before `import pytest` runs, or the fallback
        # is useless.
        result = build_tests_harness(
            "x = 1", [("t#Tests", "x == 1", 1)],
            notlob_site_packages="/fake/site-packages",
        )
        fallback_pos = result.index("sys.path.append")
        pytest_pos = result.index("import pytest as _notlob_pytest")
        assert fallback_pos < pytest_pos

    def test_bare_before_group(self):
        result = build_tests_harness(
            "x = 1\ny = 2",
            [("t#Tests", "x == 1", 1), ("t#Tests#grp", "y == 2", 2)],
        )
        assert "_notlob_check('t#Tests', 1, 'x == 1')" in result
        assert "_notlob_check('t#Tests#grp', 2, 'y == 2')" in result

    def test_harness_is_syntactically_valid(self):
        result = build_tests_harness("x = 1", [("t#Tests", "x == 1", 1)])
        compile(result, "_tests.py", "exec")  # must not raise
