"""Tests for notlob.cli binding resolution.

Covers two private helpers:

_parse_binding_declarations(lines)
    Extracts ~sigil declarations from a #Binding section's raw lines.

_find_binding(file_path)
    Walks up the directory tree from file_path to find the nearest
    binding.lob and returns its declarations.
"""

from pathlib import Path

import pytest

from notlob.commands import _find_binding, _parse_binding_declarations


# ── _parse_binding_declarations ───────────────────────────────


class TestParseBindingDeclarations:
    def test_single_declaration(self):
        lines = ["    ~language python"]
        assert _parse_binding_declarations(lines) == {"language": "python"}

    def test_multiple_declarations(self):
        lines = [
            "    ~language python",
            "    ~property-testing hypothesis",
            "    ~unit-testing pytest",
        ]
        result = _parse_binding_declarations(lines)
        assert result == {
            "language": "python",
            "property-testing": "hypothesis",
            "unit-testing": "pytest",
        }

    def test_non_sigil_lines_ignored(self):
        lines = [
            "    ~language python",
            "    This is prose, not a declaration.",
            "    # also not a sigil",
        ]
        assert _parse_binding_declarations(lines) == {"language": "python"}

    def test_empty_lines_ignored(self):
        lines = ["", "    ~language python", ""]
        assert _parse_binding_declarations(lines) == {"language": "python"}

    def test_declaration_with_no_value(self):
        # ~key alone — value should be empty string
        lines = ["    ~standalone"]
        assert _parse_binding_declarations(lines) == {"standalone": ""}

    def test_empty_input(self):
        assert _parse_binding_declarations([]) == {}

    def test_value_with_internal_spaces_preserved(self):
        # Only the first word after ~ is the key; remainder is value
        lines = ["    ~description some long value here"]
        result = _parse_binding_declarations(lines)
        assert result == {"description": "some long value here"}

    def test_leading_whitespace_stripped(self):
        # Lines may carry indentation (as stored in BindingSection.lines)
        lines = ["        ~language python"]  # double-indented
        assert _parse_binding_declarations(lines) == {"language": "python"}


# ── _find_binding ─────────────────────────────────────────────

_BINDING_LOB = """\
#Test Binding

A binding.lob for testing purposes.

---

#Binding
    ~language python
    ~property-testing hypothesis
    ~unit-testing pytest
"""

_BINDING_LOB_NO_SECTION = """\
#Test Binding

A binding.lob with no #Binding section.

---

#References
    import os
"""


class TestFindBinding:
    def test_binding_in_same_directory(self, tmp_path):
        (tmp_path / "binding.lob").write_text(_BINDING_LOB)
        target = tmp_path / "module.lob"
        target.touch()
        result = _find_binding(target)
        assert result["language"] == "python"
        assert result["property-testing"] == "hypothesis"
        assert result["unit-testing"] == "pytest"

    def test_binding_one_level_up(self, tmp_path):
        (tmp_path / "binding.lob").write_text(_BINDING_LOB)
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        target = pkg / "module.lob"
        target.touch()
        result = _find_binding(target)
        assert result["language"] == "python"

    def test_binding_several_levels_up(self, tmp_path):
        (tmp_path / "binding.lob").write_text(_BINDING_LOB)
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        target = deep / "module.lob"
        target.touch()
        result = _find_binding(target)
        assert result["language"] == "python"

    def test_no_binding_returns_empty_dict(self, tmp_path):
        # No binding.lob anywhere under tmp_path
        target = tmp_path / "module.lob"
        target.touch()
        assert _find_binding(target) == {}

    def test_binding_without_binding_section_returns_empty(self, tmp_path):
        # binding.lob exists but has no #Binding section
        (tmp_path / "binding.lob").write_text(_BINDING_LOB_NO_SECTION)
        target = tmp_path / "module.lob"
        target.touch()
        assert _find_binding(target) == {}

    def test_stops_at_nearest_binding_lob(self, tmp_path):
        # A binding.lob in pkg/ should shadow one in tmp_path/
        outer = """\
#Outer

---

#Binding
    ~language haskell
"""
        inner = """\
#Inner

---

#Binding
    ~language python
"""
        (tmp_path / "binding.lob").write_text(outer)
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "binding.lob").write_text(inner)
        target = pkg / "module.lob"
        target.touch()
        result = _find_binding(target)
        # The nearest binding.lob wins; outer is never consulted
        assert result["language"] == "python"

    def test_malformed_binding_lob_returns_empty(self, tmp_path):
        # A binding.lob that fails to parse returns {} and does not raise
        (tmp_path / "binding.lob").write_text("this is not valid lob\n\n???\n")
        target = tmp_path / "module.lob"
        target.touch()
        assert _find_binding(target) == {}

    def test_real_gutenberg_binding(self):
        # Integration: the actual gutenberg binding.lob resolves correctly
        hamlet = (
            Path(__file__).parent.parent
            / "examples" / "gutenberg" / "gutenberg" / "hamlet.lob"
        )
        if not hamlet.exists():
            pytest.skip("gutenberg example not present")
        result = _find_binding(hamlet)
        assert result.get("language") == "python"
        assert result.get("property-testing") == "hypothesis"
        assert result.get("unit-testing") == "pytest"

    def test_real_retail_binding(self):
        # Integration: the actual retail binding.lob resolves correctly
        discounts = (
            Path(__file__).parent.parent
            / "examples" / "retail" / "pricing" / "discounts.lob"
        )
        if not discounts.exists():
            pytest.skip("retail example not present")
        result = _find_binding(discounts)
        assert result.get("language") == "python"
        assert result.get("unit-testing") == "pytest"
