"""Tests for the Haskell runner.

Two tiers:
  • Pure unit tests (no GHC needed): harness generation, output parsing,
    string escaping, assertion iteration.
  • Integration tests (GHC via runghc / stack): exercise actual
    compilation and execution.  Skipped when no runner is available.

Integration tests are slow on first run because stack may need to
install GHC; subsequent runs hit the stack cache and are fast.
"""

from __future__ import annotations

import shutil
import textwrap

import pytest

from notlob.bindings import ClaimResult, Status
from notlob.bindings.haskell.runner import (
    _hs_string_escape,
    _iter_assertions,
    _build_examples_harness,
    _build_property_harness,
    _parse_output,
    run_examples,
    run_tests,
    run_properties,
)
from notlob.model import (
    Claim,
    CodeBlock,
    Module,
    PostText,
    ProseBlock,
    ReferencesSection,
    Subheading,
    TestsSection,
    TestGroup,
)


# ── Skip marker ───────────────────────────────────────────────

_HAS_RUNNER = shutil.which("runghc") is not None or shutil.which("stack") is not None
_RUNNER_SKIP = pytest.mark.skipif(
    not _HAS_RUNNER,
    reason="runghc or stack not found",
)

# ── Module builders ───────────────────────────────────────────

def _module(title, body=None, refs=None, tests=None):
    """Build a minimal Module for tests."""
    body = body or []
    sections = []
    if refs is not None:
        sections.append(ReferencesSection(lines=refs))
    if tests is not None:
        sections.append(tests)
    post = PostText(sections=sections) if sections else None
    return Module(title=title, body=body, post_text=post)


def _code(text):
    """Build a CodeBlock from a dedented text string."""
    lines = ["    " + line for line in text.splitlines()]
    return CodeBlock(lines=lines)


def _example(lines):
    """Build a ~example Claim with the given assertion lines."""
    return Claim(
        sigil="~example",
        lines=["    " + ln for ln in lines],
    )


def _property_claim(sigil, lines):
    """Build a ~property Claim."""
    return Claim(
        sigil=sigil,
        lines=["    " + ln for ln in lines],
    )


# ── _hs_string_escape ─────────────────────────────────────────

class TestHsStringEscape:
    def test_plain(self):
        assert _hs_string_escape("hello") == "hello"

    def test_double_quote(self):
        assert _hs_string_escape('say "hi"') == 'say \\"hi\\"'

    def test_backslash(self):
        assert _hs_string_escape("a\\b") == "a\\\\b"

    def test_newline(self):
        assert _hs_string_escape("a\nb") == "a\\nb"

    def test_tab(self):
        assert _hs_string_escape("a\tb") == "a\\tb"

    def test_expression_with_string_literal(self):
        assert _hs_string_escape('toRoman 1 == "I"') == 'toRoman 1 == \\"I\\"'


# ── _iter_assertions ──────────────────────────────────────────

class TestIterAssertions:
    def test_single_line(self):
        assert list(_iter_assertions(["    f x == 1"])) == ["f x == 1"]

    def test_blank_lines_skipped(self):
        lines = ["    f x == 1", "", "    g x == 2"]
        assert list(_iter_assertions(lines)) == ["f x == 1", "g x == 2"]

    def test_empty_input(self):
        assert list(_iter_assertions([])) == []

    def test_strips_whitespace(self):
        assert list(_iter_assertions(["        deep == True"])) == ["deep == True"]

    def test_multiple_lines(self):
        lines = ["    a == 1", "    b == 2", "    c == 3"]
        assert list(_iter_assertions(lines)) == ["a == 1", "b == 2", "c == 3"]


# ── _build_examples_harness ───────────────────────────────────

class TestBuildExamplesHarness:
    def _harness_for(self, code_text, assertions):
        m = _module("Test Module", body=[_code(code_text)])
        return _build_examples_harness(m, assertions)

    def test_starts_with_module_decl(self):
        h = self._harness_for("f x = x", [("addr", "f 1 == 1")])
        assert h.startswith("module NotlobRunner where")

    def test_not_user_module_name(self):
        # Must NOT be "module TestModule where"
        h = self._harness_for("f x = x", [("addr", "f 1 == 1")])
        assert "module TestModule where" not in h

    def test_helper_present(self):
        h = self._harness_for("f x = x", [("addr", "f 1 == 1")])
        assert "_notlobCheck" in h

    def test_main_present(self):
        h = self._harness_for("f x = x", [("addr", "f 1 == 1")])
        assert "main :: IO ()" in h

    def test_assertion_embedded(self):
        h = self._harness_for("f x = x", [("addr", "f 1 == 1")])
        assert "f 1 == 1" in h

    def test_address_embedded(self):
        h = self._harness_for("f x = x", [("test/mod#example#1", "f 1 == 1")])
        assert "test/mod#example#1" in h

    def test_user_code_embedded(self):
        h = self._harness_for("answer = 42", [("addr", "answer == 42")])
        assert "answer = 42" in h

    def test_quotes_in_expression_escaped(self):
        h = self._harness_for(
            'greet = "hello"',
            [("addr", 'greet == "hello"')],
        )
        # The escaped form should appear (for the display string arg)
        assert '\\"hello\\"' in h
        # The raw expression also appears (for actual evaluation)
        assert 'greet == "hello"' in h

    def test_imports_from_refs_included(self):
        m = _module(
            "Test Module",
            body=[_code("f x = x")],
            refs=["    import Data.List (sort)"],
        )
        h = _build_examples_harness(m, [("addr", "f 1 == 1")])
        assert "import Data.List (sort)" in h

    def test_lob_refs_excluded(self):
        m = _module(
            "Test Module",
            body=[_code("f x = x")],
            refs=["    #Roman Numerals", "    import Data.Char"],
        )
        h = _build_examples_harness(m, [("addr", "f 1 == 1")])
        assert "#Roman Numerals" not in h
        assert "import Data.Char" in h

    def test_multiple_assertions_all_present(self):
        assertions = [
            ("addr1", "f 1 == 2"),
            ("addr2", "g 3 == 4"),
        ]
        h = self._harness_for("f x = x\ng x = x", assertions)
        assert "f 1 == 2" in h
        assert "g 3 == 4" in h


# ── _parse_output ─────────────────────────────────────────────

class TestParseOutput:
    def _parse(self, stdout, assertions=None, stderr="", rc=0):
        assertions = assertions or [("addr", "expr")]
        return _parse_output(stdout, stderr, rc, assertions)

    def test_pass_result(self):
        results = self._parse("CLAIM\taddr\texpr\nPASS\n")
        assert len(results) == 1
        assert results[0].status == Status.PASS
        assert results[0].address == "addr"
        assert results[0].line == "expr"

    def test_fail_result(self):
        results = self._parse("CLAIM\taddr\texpr\nFAIL\n")
        assert len(results) == 1
        assert results[0].status == Status.FAIL

    def test_two_pass_results(self):
        stdout = "CLAIM\ta1\te1\nPASS\nCLAIM\ta2\te2\nPASS\n"
        assertions = [("a1", "e1"), ("a2", "e2")]
        results = _parse_output(stdout, "", 0, assertions)
        assert len(results) == 2
        assert all(r.status == Status.PASS for r in results)

    def test_mixed_results(self):
        stdout = "CLAIM\ta1\te1\nPASS\nCLAIM\ta2\te2\nFAIL\n"
        assertions = [("a1", "e1"), ("a2", "e2")]
        results = _parse_output(stdout, "", 0, assertions)
        assert results[0].status == Status.PASS
        assert results[1].status == Status.FAIL

    def test_crash_after_claim_gives_error(self):
        # CLAIM line with no following result = crash
        results = self._parse(
            "CLAIM\taddr\texpr\n",
            assertions=[("addr", "expr")],
            stderr="runtime error",
        )
        assert results[0].status == Status.ERROR

    def test_empty_stdout_with_failed_rc_gives_error(self):
        results = self._parse(
            "",
            assertions=[("addr", "expr")],
            stderr="parse error",
            rc=1,
        )
        assert len(results) == 1
        assert results[0].status == Status.ERROR

    def test_empty_stdout_no_assertions_returns_empty(self):
        results = _parse_output("", "", 0, [])
        assert results == []

    def test_address_and_expr_extracted(self):
        results = self._parse(
            "CLAIM\troman/numerals#example#1\ttoRoman 1 == \"I\"\nPASS\n",
            assertions=[("roman/numerals#example#1", 'toRoman 1 == "I"')],
        )
        assert results[0].address == "roman/numerals#example#1"
        assert results[0].line == 'toRoman 1 == "I"'

    def test_error_line_in_output(self):
        stdout = "CLAIM\taddr\texpr\nERROR\tsomething went wrong\n"
        results = _parse_output(stdout, "", 0, [("addr", "expr")])
        assert results[0].status == Status.ERROR
        assert "something went wrong" in str(results[0].error)


# ── Integration: run_examples ─────────────────────────────────

@_RUNNER_SKIP
class TestRunExamplesIntegration:
    def _run(self, code_text, assertion_lines):
        body = [
            _code(code_text),
            _example(assertion_lines),
        ]
        m = _module("Test Module", body=body)
        return run_examples(m)

    def test_passing_example(self):
        results = self._run("answer = 42", ["answer == 42"])
        assert len(results) == 1
        assert results[0].status == Status.PASS

    def test_failing_example(self):
        results = self._run("answer = 42", ["answer == 99"])
        assert len(results) == 1
        assert results[0].status == Status.FAIL

    def test_two_assertions_both_pass(self):
        results = self._run("f x = x + 1", ["f 1 == 2", "f 0 == 1"])
        assert len(results) == 2
        assert all(r.status == Status.PASS for r in results)

    def test_first_pass_second_fail(self):
        results = self._run("f x = x + 1", ["f 1 == 2", "f 1 == 99"])
        assert results[0].status == Status.PASS
        assert results[1].status == Status.FAIL

    def test_string_assertions(self):
        results = self._run(
            'greet = "hello"',
            ['greet == "hello"'],
        )
        assert results[0].status == Status.PASS

    def test_no_examples_returns_empty(self):
        m = _module("Test Module", body=[_code("f x = x")])
        assert run_examples(m) == []

    def test_example_address(self):
        body = [_code("f x = x"), _example(["f 1 == 1"])]
        m = _module("Test Module", body=body)
        results = run_examples(m)
        assert results[0].address == "test/module#example#1"

    def test_compile_error_gives_error_result(self):
        results = self._run("this is not valid haskell !@#", ["True == True"])
        assert len(results) >= 1
        assert results[0].status == Status.ERROR

    def test_list_operations(self):
        results = self._run(
            "myList = [1, 2, 3]",
            ["length myList == 3", "head myList == 1"],
        )
        assert all(r.status == Status.PASS for r in results)

    def test_example_in_subheading(self):
        example = _example(["g 5 == 25"])
        sub = Subheading(title="Squaring", body=[_code("g x = x * x"), example])
        m = _module("Test Module", body=[sub])
        results = run_examples(m)
        assert len(results) == 1
        assert results[0].status == Status.PASS
        assert "Squaring" in results[0].address

    def test_multiline_function(self):
        code = textwrap.dedent("""\
            fib :: Int -> Int
            fib 0 = 0
            fib 1 = 1
            fib n = fib (n-1) + fib (n-2)
        """).strip()
        results = self._run(code, ["fib 10 == 55"])
        assert results[0].status == Status.PASS


# ── Integration: run_tests ────────────────────────────────────

@_RUNNER_SKIP
class TestRunTestsIntegration:
    def _tests_section(self, bare_lines=None, groups=None):
        items = []
        for line in (bare_lines or []):
            items.append(line)
        for title, lines in (groups or []):
            items.append(TestGroup(title=title, lines=lines))
        return TestsSection(items=items)

    def _run(self, code_text, bare_lines=None, groups=None):
        tests = self._tests_section(bare_lines, groups)
        m = _module(
            "Test Module",
            body=[_code(code_text)],
            tests=tests,
        )
        return run_tests(m)

    def test_bare_passing_assertion(self):
        results = self._run("x = 10", bare_lines=["    x == 10"])
        assert len(results) == 1
        assert results[0].status == Status.PASS

    def test_bare_failing_assertion(self):
        results = self._run("x = 10", bare_lines=["    x == 99"])
        assert results[0].status == Status.FAIL

    def test_grouped_assertions(self):
        results = self._run(
            "f x = x * 2",
            groups=[("Doubling", ["    f 3 == 6", "    f 0 == 0"])],
        )
        assert len(results) == 2
        assert all(r.status == Status.PASS for r in results)
        assert "Doubling" in results[0].address

    def test_no_tests_section_returns_empty(self):
        m = _module("Test Module", body=[_code("f x = x")])
        assert run_tests(m) == []

    def test_tests_address_format(self):
        results = self._run("x = 1", bare_lines=["    x == 1"])
        assert results[0].address == "test/module#Tests"

    def test_group_address_format(self):
        results = self._run(
            "f x = x",
            groups=[("MyGroup", ["    f 1 == 1"])],
        )
        assert results[0].address == "test/module#Tests#MyGroup"


# ── Integration: run_properties ──────────────────────────────

@_RUNNER_SKIP
class TestRunPropertiesIntegration:
    def test_skip_without_binding(self):
        prop = _property_claim(
            "~property",
            ["prop_id :: Int -> Bool", "prop_id x = x == x"],
        )
        m = _module("Test Module", body=[_code("f x = x"), prop])
        results = run_properties(m, binding=None)
        assert len(results) == 1
        assert results[0].status == Status.SKIP

    def test_skip_without_quickcheck_binding(self):
        prop = _property_claim(
            "~property",
            ["prop_id :: Int -> Bool", "prop_id x = x == x"],
        )
        m = _module("Test Module", body=[_code("f x = x"), prop])
        results = run_properties(m, binding={"property-testing": "hypothesis"})
        assert results[0].status == Status.SKIP

    def test_passing_property(self):
        prop = _property_claim(
            "~property",
            ["prop_id :: Int -> Bool", "prop_id x = x == x"],
        )
        m = _module("Test Module", body=[_code("f x = x"), prop])
        results = run_properties(m, binding={"property-testing": "quickcheck"})
        assert len(results) == 1
        assert results[0].status == Status.PASS

    def test_failing_property(self):
        # Always False — QuickCheck will find a counterexample
        prop = _property_claim(
            "~property",
            ["prop_bad :: Int -> Bool", "prop_bad _ = False"],
        )
        m = _module("Test Module", body=[_code("f x = x"), prop])
        results = run_properties(m, binding={"property-testing": "quickcheck"})
        assert results[0].status == Status.FAIL

    def test_named_property_address(self):
        prop = _property_claim(
            "~property commutativity",
            ["prop_comm :: Int -> Int -> Bool",
             "prop_comm a b = a + b == b + a"],
        )
        m = _module("Test Module", body=[_code("f x = x"), prop])
        results = run_properties(m, binding={"property-testing": "quickcheck"})
        assert results[0].address == "test/module#commutativity"

    def test_unnamed_property_address(self):
        prop = _property_claim(
            "~property",
            ["prop_id :: Int -> Bool", "prop_id x = x == x"],
        )
        m = _module("Test Module", body=[_code("f x = x"), prop])
        results = run_properties(m, binding={"property-testing": "quickcheck"})
        assert results[0].address == "test/module#property#1"

    def test_no_properties_returns_empty(self):
        m = _module("Test Module", body=[_code("f x = x")])
        results = run_properties(m, binding={"property-testing": "quickcheck"})
        assert results == []
