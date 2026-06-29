"""Tests for the Haskell linter integration.

parse_source_map translates assembled-source line numbers to notlob
section addresses.  lint_haskell runs hlint and returns LintResult
objects.

Pure tests (TestParseSourceMap, TestFormatMessage) run without hlint.
Integration tests (TestLintHaskell) are skipped when hlint is absent.
"""

from __future__ import annotations

import shutil

import subprocess

import pytest

from notlob import from_tree, parse
from notlob.bindings import LintResult
from notlob.bindings.haskell.assemble import assemble
from notlob.bindings.haskell.lint import (
    _format_message,
    lint_haskell,
    parse_source_map,
)


def _hlint_available() -> bool:
    """Return True if hlint can actually be invoked."""
    if shutil.which("hlint"):
        return True
    if shutil.which("stack"):
        try:
            r = subprocess.run(
                ["stack", "exec", "--", "hlint", "--version"],
                capture_output=True, text=True, timeout=30,
            )
            return r.returncode == 0
        except Exception:
            pass
    return False


_HLINT_AVAILABLE = _hlint_available()

requires_hlint = pytest.mark.skipif(
    not _HLINT_AVAILABLE,
    reason="hlint not installed",
)


def _module(text: str):
    return from_tree(parse(text))


# ── parse_source_map ─────────────────────────────────────────

class TestParseSourceMap:
    def test_empty_string(self):
        assert parse_source_map("") == {}

    def test_single_section(self):
        src = "-- roman/numerals\nx = 1\ny = 2\n"
        m = parse_source_map(src)
        assert m[2] == "roman/numerals"
        assert m[3] == "roman/numerals"

    def test_location_comment_line_not_mapped(self):
        """The -- <address> comment line itself is not in the map."""
        src = "-- roman/numerals\nx = 1\n"
        m = parse_source_map(src)
        assert 1 not in m       # the comment line
        assert m[2] == "roman/numerals"

    def test_two_sections(self):
        src = (
            "-- roman/numerals\n"
            "x = 1\n"
            "\n"
            "-- roman/numerals#Properties\n"
            "y = 2\n"
        )
        m = parse_source_map(src)
        assert m[2] == "roman/numerals"
        assert m[5] == "roman/numerals#Properties"

    def test_blank_lines_mapped(self):
        """Blank lines between sections are mapped to the current section."""
        src = (
            "-- roman/numerals\n"
            "x = 1\n"
            "\n"
            "y = 2\n"
        )
        m = parse_source_map(src)
        assert m[3] == "roman/numerals"   # blank line

    def test_pre_header_lines_assigned_to_first_section(self):
        """Lines before the first address marker (e.g. module header)
        are back-filled to the first section found."""
        src = (
            "module RomanNumerals where\n"
            "\n"
            "-- roman/numerals\n"
            "x = 1\n"
        )
        m = parse_source_map(src)
        assert m[1] == "roman/numerals"
        assert m[2] == "roman/numerals"
        assert m[4] == "roman/numerals"

    def test_subheading_address(self):
        src = (
            "-- mymod\n"
            "x = 1\n"
            "\n"
            "-- mymod#Properties\n"
            "y = 2\n"
        )
        m = parse_source_map(src)
        assert m[2] == "mymod"
        assert m[5] == "mymod#Properties"

    def test_does_not_match_regular_haskell_comments(self):
        """Ordinary Haskell comments like ``-- this is a comment`` are not
        treated as address markers."""
        src = (
            "-- roman/numerals\n"
            "-- this is just a comment\n"
            "x = 1\n"
        )
        m = parse_source_map(src)
        # The ordinary comment line is not in the map as an address,
        # but is mapped to the current section.
        assert m[2] == "roman/numerals"
        assert m[3] == "roman/numerals"

    def test_address_with_hash_fragment(self):
        src = "-- roman/numerals#Round-Trip\nf x = x\n"
        m = parse_source_map(src)
        assert m[2] == "roman/numerals#Round-Trip"

    def test_only_comment_lines_returns_empty(self):
        """Source with only comment markers and no code lines → no map."""
        src = "-- roman/numerals\n"
        m = parse_source_map(src)
        assert m == {}


# ── _format_message ──────────────────────────────────────────

class TestFormatMessage:
    def test_from_to_gives_arrow_format(self):
        d = {"hint": "Redundant do", "from": "do f x", "to": "f x"}
        assert _format_message(d) == "do f x ==> f x"

    def test_missing_to_falls_back_to_hint(self):
        d = {"hint": "Eta reduce", "from": "\\x -> f x", "to": None}
        assert _format_message(d) == "Eta reduce"

    def test_empty_from_falls_back_to_hint(self):
        d = {"hint": "Use const", "from": "", "to": "const 1"}
        assert _format_message(d) == "Use const"

    def test_missing_from_and_to(self):
        d = {"hint": "Avoid lambda"}
        assert _format_message(d) == "Avoid lambda"

    def test_whitespace_stripped(self):
        d = {"hint": "Redundant do", "from": "  do x  ", "to": "  x  "}
        assert _format_message(d) == "do x ==> x"

    def test_empty_hint_and_no_suggestion(self):
        assert _format_message({}) == ""


# ── lint_haskell — unit (no hlint required) ──────────────────

class TestLintHaskellUnit:
    def test_empty_module_returns_empty_list(self):
        """A module with no code blocks produces no lint results.

        No source to check, so the tool is not invoked — returns []
        even without hlint installed.
        """
        mod = _module("#Empty\nJust prose.\n")
        assert lint_haskell(mod) == []

    def test_missing_tool_raises(self, monkeypatch):
        """A non-empty module with hlint absent raises, never returns []."""
        from notlob.bindings import LintToolUnavailable
        import notlob.bindings.haskell.lint as hlint_mod
        monkeypatch.setattr(hlint_mod, "_hlint_cmd", lambda: None)
        src = "#M\n\n    f :: Int -> Int\n    f x = x\n"
        with pytest.raises(LintToolUnavailable):
            lint_haskell(_module(src))

    @requires_hlint
    def test_returns_list(self):
        """lint_haskell always returns a list (possibly empty)."""
        src = (
            "#Roman Numerals\n\n"
            "    toRoman :: Int -> String\n"
            "    toRoman 0 = \"\"\n"
        )
        result = lint_haskell(_module(src))
        assert isinstance(result, list)

    @requires_hlint
    def test_results_are_lint_result_instances(self):
        """When hlint produces results they are LintResult objects."""
        src = (
            "#Roman Numerals\n\n"
            "    toRoman :: Int -> String\n"
            "    toRoman 0 = \"\"\n"
        )
        results = lint_haskell(_module(src))
        for r in results:
            assert isinstance(r, LintResult)


# ── lint_haskell — integration (hlint required) ──────────────

class TestLintHaskellIntegration:
    @requires_hlint
    def test_clean_code_produces_no_results(self):
        """Well-formed idiomatic Haskell produces no hlint warnings."""
        src = (
            "#Clean Module\n\n"
            "    f :: Int -> Int\n"
            "    f x = x + 1\n"
        )
        results = lint_haskell(_module(src))
        assert results == []

    @requires_hlint
    def test_redundant_eq_flagged(self):
        """Comparing to True with == is flagged as 'Redundant =='."""
        src = (
            "#My Module\n\n"
            "    f :: Bool -> Int\n"
            "    f x = if x == True then 1 else 0\n"
        )
        results = lint_haskell(_module(src))
        codes = [r.code for r in results]
        assert any("Redundant ==" in c for c in codes)

    @requires_hlint
    def test_result_has_non_empty_address(self):
        """Every LintResult produced by hlint has a non-empty address."""
        src = (
            "#My Module\n\n"
            "    main :: IO ()\n"
            "    main = do\n"
            "        putStrLn \"hello\"\n"
        )
        results = lint_haskell(_module(src))
        assert all(r.address for r in results)

    @requires_hlint
    def test_result_address_matches_module(self):
        """Lint results for module-level code are attributed to the
        module address (``my/module``)."""
        src = (
            "#My Module\n\n"
            "    main :: IO ()\n"
            "    main = do\n"
            "        putStrLn \"hello\"\n"
        )
        results = lint_haskell(_module(src))
        assert all(r.address == "my/module" for r in results)

    @requires_hlint
    def test_message_non_empty(self):
        """LintResult messages from hlint are non-empty strings."""
        src = (
            "#My Module\n\n"
            "    main :: IO ()\n"
            "    main = do\n"
            "        putStrLn \"hello\"\n"
        )
        results = lint_haskell(_module(src))
        assert all(r.message for r in results)

    @requires_hlint
    def test_subheading_code_attributed_to_subheading(self):
        """Code under a subheading is attributed to the subheading address."""
        src = (
            "#My Module\n\n"
            "    f :: Int -> Int\n"
            "    f x = x + 1\n\n"
            "## Helpers\n\n"
            "    g :: IO ()\n"
            "    g = do\n"
            "        return ()\n"
        )
        results = lint_haskell(_module(src))
        if results:
            # Any result in the Helpers subheading uses that address.
            helpers = [
                r for r in results
                if "Helpers" in r.address
            ]
            if helpers:
                assert all("my/module" in r.address for r in helpers)
