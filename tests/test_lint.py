"""Tests for the Python linter integration.

parse_source_map translates assembled-source line numbers to notlob
section addresses.  lint_python runs ruff and returns LintResult
objects.
"""

from __future__ import annotations

import pytest

from notlob import from_tree, parse
from notlob.bindings import LintResult
from notlob.bindings.python.assemble import assemble
from notlob.bindings.python.lint import lint_python, parse_source_map


def _module(text: str):
    return from_tree(parse(text))


# ── parse_source_map ─────────────────────────────────────────

class TestParseSourceMap:
    def test_empty_string(self):
        assert parse_source_map("") == {}

    def test_single_section(self):
        src = "# roman/numerals\ndef to_roman(n):\n    return 'I'"
        m = parse_source_map(src)
        assert m[2] == "roman/numerals"
        assert m[3] == "roman/numerals"

    def test_location_comment_line_not_mapped(self):
        """The # <address> comment line itself is not in the map."""
        src = "# roman/numerals\nx = 1"
        m = parse_source_map(src)
        assert 1 not in m   # the comment line
        assert m[2] == "roman/numerals"

    def test_two_sections(self):
        src = (
            "# roman/numerals\n"
            "x = 1\n"
            "\n"
            "# roman/numerals#Decoding\n"
            "y = 2\n"
        )
        m = parse_source_map(src)
        assert m[2] == "roman/numerals"
        assert m[5] == "roman/numerals#Decoding"

    def test_pre_header_lines_assigned_to_first_section(self):
        """Lines before the first address marker (e.g. imports) go to
        the first section once it appears."""
        src = (
            "import re\n"
            "from collections import Counter\n"
            "\n"
            "# gutenberg/corpus\n"
            "def f(): pass\n"
        )
        m = parse_source_map(src)
        assert m[1] == "gutenberg/corpus"
        assert m[2] == "gutenberg/corpus"
        assert m[5] == "gutenberg/corpus"

    def test_subheading_address(self):
        src = (
            "# mymod\n"
            "x = 1\n"
            "\n"
            "# mymod#Loading\n"
            "y = 2\n"
        )
        m = parse_source_map(src)
        assert m[2] == "mymod"
        assert m[5] == "mymod#Loading"


# ── lint_python ───────────────────────────────────────────────

class TestLintPython:
    def test_empty_module_no_results(self):
        """A module with no code blocks produces no lint results.

        No source to check, so ruff is not invoked.
        """
        mod = _module("#Empty\nJust prose.\n")
        assert lint_python(mod) == []

    def test_missing_tool_raises(self, monkeypatch):
        """A non-empty module with ruff absent raises, never returns []."""
        from notlob.bindings import LintToolUnavailable
        import notlob.bindings.python.lint as lint_mod
        monkeypatch.setattr(
            lint_mod.importlib.util, "find_spec", lambda name: None
        )
        src = "#M\n\n    x = 1\n"
        with pytest.raises(LintToolUnavailable):
            lint_python(_module(src))

    def test_clean_code_no_results(self):
        """Clean, valid Python code produces no lint results."""
        src = (
            "#Clean Module\n"
            "\n"
            "    def greet(name: str) -> str:\n"
            "        return f'hello {name}'\n"
        )
        results = lint_python(_module(src))
        assert results == []

    def test_returns_lint_result_objects(self):
        """lint_python always returns LintResult instances."""
        src = (
            "#My Module\n"
            "\n"
            "    x = 1\n"
            "\n"
            "---\n"
            "#References\n"
            "    import os\n"
        )
        results = lint_python(_module(src))
        for r in results:
            assert isinstance(r, LintResult)

    def test_unused_import_flagged(self):
        """An unused import in #References is caught by ruff (F401)."""
        src = (
            "#My Module\n"
            "\n"
            "    x = 1\n"
            "\n"
            "---\n"
            "#References\n"
            "    import os\n"
        )
        results = lint_python(_module(src))
        codes = [r.code for r in results]
        assert "F401" in codes

    def test_lint_result_has_address(self):
        """Every LintResult has a non-empty address."""
        src = (
            "#My Module\n"
            "\n"
            "    x = 1\n"
            "\n"
            "---\n"
            "#References\n"
            "    import os\n"
        )
        results = lint_python(_module(src))
        assert all(r.address for r in results)

    def test_address_matches_module(self):
        """Lint results for module-level code are attributed to the
        module address."""
        src = (
            "#My Module\n"
            "\n"
            "    x = 1\n"
            "\n"
            "---\n"
            "#References\n"
            "    import os\n"
        )
        results = lint_python(_module(src))
        # F401 for unused import should map to the module address.
        # module_address("My Module") == "my/module"
        f401 = [r for r in results if r.code == "F401"]
        assert all(r.address == "my/module" for r in f401)
