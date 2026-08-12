"""Tests for the ~example claim runner.

run_examples() assembles a module, executes it, then evaluates each
~example claim assertion and returns a list of ClaimResults.
"""

from pathlib import Path


from notlob import parse, parse_file, from_tree, claim_address
from notlob.bindings.python.harness import build_examples_harness
from notlob.bindings.python.runner import (
    ClaimResult, Status, run_examples,
)


EXAMPLES = Path(__file__).parent.parent / "examples"


def ran(source: str) -> list[ClaimResult]:
    return run_examples(from_tree(parse(source)))


# ── claim_address helper ──────────────────────────────────────

class TestClaimAddress:
    def test_module_level(self):
        assert (
            claim_address("roman/numerals", "example", 1)
            == "roman/numerals#example#1"
        )

    def test_subheading(self):
        assert (
            claim_address("roman/numerals#Decoding", "example", 2)
            == "roman/numerals#Decoding#example#2"
        )

    def test_property_kind(self):
        assert (
            claim_address("pricing/discounts", "property", 1)
            == "pricing/discounts#property#1"
        )


# ── Basic pass/fail ───────────────────────────────────────────

class TestPassFail:
    def test_passing_claim(self):
        src = "#T\n    def f(): return 1\n~example\n    f() == 1\n"
        results = ran(src)
        assert len(results) == 1
        assert results[0].status == Status.PASS

    def test_failing_claim(self):
        src = "#T\n    def f(): return 2\n~example\n    f() == 1\n"
        results = ran(src)
        assert len(results) == 1
        assert results[0].status == Status.FAIL

    def test_error_claim(self):
        # g is not defined
        src = "#T\n    def f(): return 1\n~example\n    g() == 1\n"
        results = ran(src)
        assert results[0].status == Status.ERROR
        assert isinstance(results[0].error, Exception)

    def test_no_claims_returns_empty(self):
        assert ran("#T\n    x = 1\n") == []

    def test_property_claims_not_run(self):
        src = "#T\n~property\n    x = 1\n"
        assert ran(src) == []


# ── Left/right extraction on failure ─────────────────────────

class TestFailureValues:
    def test_left_right_populated(self):
        src = "#T\n    x = 2\n~example\n    x == 1\n"
        result = ran(src)[0]
        assert result.status == Status.FAIL
        assert result.left == 2
        assert result.right == 1

    def test_left_right_none_for_complex_expression(self):
        # Not a simple == comparison; falls back gracefully.
        src = "#T\n    x = 2\n~example\n    x > 5\n"
        result = ran(src)[0]
        assert result.status == Status.FAIL
        assert result.left is None
        assert result.right is None

    def test_source_line_preserved(self):
        src = "#T\n    x = 1\n~example\n    x == 1\n"
        assert ran(src)[0].line == "x == 1"


# ── Addresses ─────────────────────────────────────────────────

class TestAddresses:
    def test_module_level_address(self):
        src = "#T\n    def f(): return 1\n~example\n    f() == 1\n"
        assert ran(src)[0].address == "t#example#1"

    def test_subheading_address(self):
        src = "#T\n##S\n    def f(): return 1\n~example\n    f() == 1\n"
        assert ran(src)[0].address == "t#S#example#1"

    def test_multiword_module_address(self):
        src = (
            "#Roman Numerals\n"
            "    def f(): return 1\n"
            "~example\n"
            "    f() == 1\n"
        )
        assert ran(src)[0].address == "roman/numerals#example#1"

    def test_ordinals_count_per_containing_node(self):
        src = (
            "#T\n"
            "    def f(): return 1\n"
            "~example\n    f() == 1\n"
            "~example\n    f() == 1\n"
        )
        results = ran(src)
        assert results[0].address == "t#example#1"
        assert results[1].address == "t#example#2"

    def test_ordinals_reset_per_subheading(self):
        src = (
            "#T\n"
            "    def f(): return 1\n"
            "~example\n    f() == 1\n"
            "##S\n"
            "~example\n    f() == 1\n"
        )
        results = ran(src)
        assert results[0].address == "t#example#1"
        assert results[1].address == "t#S#example#1"


# ── Multiple lines per claim ──────────────────────────────────

class TestMultiLineClaims:
    def test_each_line_is_a_result(self):
        src = (
            "#T\n"
            "    def f(n): return n * 2\n"
            "~example\n"
            "    f(1) == 2\n"
            "    f(2) == 4\n"
        )
        results = ran(src)
        assert len(results) == 2
        assert all(r.status == Status.PASS for r in results)

    def test_multiline_expression_joined(self):
        # A single expression split across lines is one assertion.
        src = (
            "#T\n"
            "    def f(a, b): return a + b\n"
            "~example\n"
            "    f(1,\n"
            "      2) == 3\n"
        )
        results = ran(src)
        assert len(results) == 1
        assert results[0].status == Status.PASS

    def test_blank_lines_between_assertions_skipped(self):
        # Blank lines between complete expressions within a claim
        # are ignored; each complete expression is one assertion.
        src = (
            "#T\n"
            "    def f(): return 1\n"
            "~example\n"
            "    f() == 1\n"
            "\n"
            "    f() == 1\n"
        )
        results = ran(src)
        assert len(results) == 2


# ── References and assembly ───────────────────────────────────

class TestReferencesInScope:
    def test_references_available_to_claims(self):
        src = (
            "#T\n"
            "    result = Path('.')\n"
            "~example\n"
            "    result is not None\n"
            "---\n"
            "#References\n"
            "    from pathlib import Path\n"
        )
        assert ran(src)[0].status == Status.PASS

    def test_assembly_error_reported(self):
        # Force an exec-time error: reference to undefined name at
        # module level (not inside a function).
        src = "#T\n    x = undefined_name\n~example\n    x == 1\n"
        results = ran(src)
        assert len(results) == 1
        assert results[0].status == Status.ERROR
        assert results[0].line == "<assembly>"


# ── Integration: example files ────────────────────────────────

class TestExampleFiles:
    def _run(self, path):
        return run_examples(from_tree(parse_file(path)))

    def test_pricing_discounts_all_pass(self):
        results = self._run(EXAMPLES / "retail/pricing/discounts.lob")
        assert results, "expected at least one ~example claim"
        failures = [r for r in results if r.status != Status.PASS]
        assert failures == [], failures

    def test_roman_numerals_all_pass(self):
        results = self._run(EXAMPLES / "roman/roman/numerals.lob")
        assert results, "expected at least one ~example claim"
        # roman/numerals#example#2 is a deliberate failure in the file
        failures = [
            r for r in results
            if r.status != Status.PASS
            and r.address != "roman/numerals#example#2"
        ]
        assert failures == [], failures

    def test_roman_deliberate_failure(self):
        # The file contains a known-wrong claim to exercise the
        # runner's failure path.  to_roman(8) is 'VIII', not 'IIX'.
        results = self._run(EXAMPLES / "roman/roman/numerals.lob")
        bad = [r for r in results
               if r.address == "roman/numerals#example#2"]
        assert len(bad) == 1
        assert bad[0].status == Status.FAIL
        assert bad[0].left  == 'VIII'
        assert bad[0].right == 'IIX'


# ── Keep-dir: _examples.py contains assert statements ─────────

class TestKeepDirExamples:
    def test_examples_py_contains_check_call(self, tmp_path):
        src = "#T\n    def f(): return 1\n~example\n    f() == 1\n"
        module = from_tree(parse(src))
        run_examples(module, keep_dir=tmp_path)
        content = (tmp_path / "_examples.py").read_text(encoding="utf-8")
        assert "'f() == 1'" in content

    def test_examples_py_contains_module_code(self, tmp_path):
        src = "#T\n    def f(): return 1\n~example\n    f() == 1\n"
        module = from_tree(parse(src))
        run_examples(module, keep_dir=tmp_path)
        content = (tmp_path / "_examples.py").read_text(encoding="utf-8")
        assert "def f()" in content

    def test_examples_py_address_in_check_call(self, tmp_path):
        src = "#T\n    def f(): return 1\n~example\n    f() == 1\n"
        module = from_tree(parse(src))
        run_examples(module, keep_dir=tmp_path)
        content = (tmp_path / "_examples.py").read_text(encoding="utf-8")
        assert "'t#example#1'" in content

    def test_examples_py_subheading_address(self, tmp_path):
        src = "#T\n##S\n    def f(): return 1\n~example\n    f() == 1\n"
        module = from_tree(parse(src))
        run_examples(module, keep_dir=tmp_path)
        content = (tmp_path / "_examples.py").read_text(encoding="utf-8")
        assert "'t#S#example#1'" in content

    def test_examples_py_is_executable(self, tmp_path):
        src = "#T\n    def f(): return 1\n~example\n    f() == 1\n"
        module = from_tree(parse(src))
        run_examples(module, keep_dir=tmp_path)
        kept = (tmp_path / "_examples.py").read_text(encoding="utf-8")
        exec(compile(kept, "_examples.py", "exec"), {})

    def test_no_keep_dir_no_file_written(self, tmp_path):
        src = "#T\n    def f(): return 1\n~example\n    f() == 1\n"
        module = from_tree(parse(src))
        run_examples(module, keep_dir=None)
        assert not list(tmp_path.iterdir())


# ── build_examples_harness unit tests ──────────────────────────

class TestBuildExamplesHarness:
    def test_no_assertions_no_check_calls(self):
        result = build_examples_harness("x = 1", [])
        assert "x = 1" in result
        # _notlob_check's own def is always present; only a *call* to
        # it (recognisable by the leading string-literal address arg)
        # should be absent when there are no assertions.
        assert "_notlob_check('" not in result

    def test_single_example(self):
        result = build_examples_harness(
            "def f(): return 1", [("t#example#1", "f() == 1", 1)],
        )
        assert "_notlob_check('t#example#1', 1, 'f() == 1')" in result

    def test_multiple_assertions_multiple_check_calls(self):
        result = build_examples_harness(
            "def f(): return 1",
            [
                ("t#example#1", "f() == 1", 1),
                ("t#example#2", "f() == 1", 2),
            ],
        )
        assert "_notlob_check('t#example#1', 1, 'f() == 1')" in result
        assert "_notlob_check('t#example#2', 2, 'f() == 1')" in result

    def test_harness_is_syntactically_valid(self):
        result = build_examples_harness(
            "def f(): return 1", [("t#example#1", "f() == 1", 1)],
        )
        compile(result, "_examples.py", "exec")  # must not raise
