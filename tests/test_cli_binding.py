"""Tests for notlob.commands binding resolution.

Covers _find_binding and the typed BindingSection model.
"""

from pathlib import Path

import pytest

from notlob.commands import _find_binding


# ── _find_binding ─────────────────────────────────────────────

_BINDING_LOB = """\
#Test Binding

A binding.lob for testing purposes.

---

#Binding
    ~language python
    ~external assets/style.css
    ~on-build build.py
"""

_BINDING_LOB_MINIMAL = """\
#Test Binding

---

#Binding
    ~language haskell
"""

_BINDING_LOB_NO_SECTION = """\
#Test Binding

A binding.lob with no #Binding section.

---

#References
    import os
"""


class TestFindBinding:
    def test_language_extracted(self, tmp_path):
        (tmp_path / "binding.lob").write_text(_BINDING_LOB)
        target = tmp_path / "module.lob"
        target.touch()
        result = _find_binding(target)
        assert result["language"] == "python"

    def test_external_extracted(self, tmp_path):
        (tmp_path / "binding.lob").write_text(_BINDING_LOB)
        target = tmp_path / "module.lob"
        target.touch()
        result = _find_binding(target)
        assert result["external"] == ["assets/style.css"]

    def test_on_build_extracted(self, tmp_path):
        (tmp_path / "binding.lob").write_text(_BINDING_LOB)
        target = tmp_path / "module.lob"
        target.touch()
        result = _find_binding(target)
        assert result["on-build"] == "build.py"

    def test_binding_one_level_up(self, tmp_path):
        (tmp_path / "binding.lob").write_text(_BINDING_LOB_MINIMAL)
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        target = pkg / "module.lob"
        target.touch()
        result = _find_binding(target)
        assert result["language"] == "haskell"

    def test_binding_several_levels_up(self, tmp_path):
        (tmp_path / "binding.lob").write_text(_BINDING_LOB_MINIMAL)
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        target = deep / "module.lob"
        target.touch()
        result = _find_binding(target)
        assert result["language"] == "haskell"

    def test_no_binding_returns_empty_dict(self, tmp_path):
        target = tmp_path / "module.lob"
        target.touch()
        assert _find_binding(target) == {}

    def test_binding_without_binding_section_returns_empty(self, tmp_path):
        (tmp_path / "binding.lob").write_text(_BINDING_LOB_NO_SECTION)
        target = tmp_path / "module.lob"
        target.touch()
        assert _find_binding(target) == {}

    def test_stops_at_nearest_binding_lob(self, tmp_path):
        outer = "#Outer\n\n---\n\n#Binding\n    ~language haskell\n"
        inner = "#Inner\n\n---\n\n#Binding\n    ~language python\n"
        (tmp_path / "binding.lob").write_text(outer)
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "binding.lob").write_text(inner)
        target = pkg / "module.lob"
        target.touch()
        assert _find_binding(target)["language"] == "python"

    def test_malformed_binding_lob_returns_empty(self, tmp_path):
        (tmp_path / "binding.lob").write_text("this is not valid lob\n\n???\n")
        target = tmp_path / "module.lob"
        target.touch()
        assert _find_binding(target) == {}

    def test_property_testing_not_in_result(self, tmp_path):
        # ~property-testing is no longer a valid declaration
        (tmp_path / "binding.lob").write_text(_BINDING_LOB)
        target = tmp_path / "module.lob"
        target.touch()
        result = _find_binding(target)
        assert "property-testing" not in result
        assert "unit-testing" not in result

    def test_real_gutenberg_binding(self):
        hamlet = (
            Path(__file__).parent.parent
            / "examples" / "gutenberg" / "gutenberg" / "hamlet.lob"
        )
        if not hamlet.exists():
            pytest.skip("gutenberg example not present")
        result = _find_binding(hamlet)
        assert result.get("language") == "python"

    def test_real_retail_binding(self):
        discounts = (
            Path(__file__).parent.parent
            / "examples" / "retail" / "pricing" / "discounts.lob"
        )
        if not discounts.exists():
            pytest.skip("retail example not present")
        result = _find_binding(discounts)
        assert result.get("language") == "python"
