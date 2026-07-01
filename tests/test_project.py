"""Tests for notlob.project — foundation utilities for import support."""

from pathlib import Path

import pytest

from notlob.project import (
    find_project_root,
    parse_lob_refs,
    parse_python_imports,
    resolve_module_path,
    transitive_lob_refs,
)


# ── find_project_root ─────────────────────────────────────────

class TestFindProjectRoot:
    def test_binding_in_same_directory(self, tmp_path):
        (tmp_path / "binding.lob").touch()
        target = tmp_path / "module.lob"
        target.touch()
        assert find_project_root(target) == tmp_path

    def test_binding_one_level_up(self, tmp_path):
        (tmp_path / "binding.lob").touch()
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        target = pkg / "module.lob"
        target.touch()
        assert find_project_root(target) == tmp_path

    def test_binding_several_levels_up(self, tmp_path):
        (tmp_path / "binding.lob").touch()
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        target = deep / "module.lob"
        target.touch()
        assert find_project_root(target) == tmp_path

    def test_no_binding_returns_none(self, tmp_path):
        target = tmp_path / "module.lob"
        target.touch()
        assert find_project_root(target) is None

    def test_stops_at_nearest_binding_lob(self, tmp_path):
        (tmp_path / "binding.lob").touch()
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "binding.lob").touch()
        target = pkg / "module.lob"
        target.touch()
        assert find_project_root(target) == pkg

    def test_real_roman_example(self):
        numerals = (
            Path(__file__).parent.parent
            / "examples" / "roman" / "roman" / "numerals.lob"
        )
        if not numerals.exists():
            pytest.skip("roman example not present")
        root = find_project_root(numerals)
        assert root is not None
        assert (root / "binding.lob").exists()
        assert root.name == "roman"


# ── resolve_module_path ───────────────────────────────────────

class TestResolveModulePath:
    def test_single_segment(self, tmp_path):
        assert resolve_module_path("pricing", tmp_path) == (
            tmp_path / "pricing.lob"
        )

    def test_two_segments(self, tmp_path):
        assert resolve_module_path("roman/numerals", tmp_path) == (
            tmp_path / "roman" / "numerals.lob"
        )

    def test_three_segments(self, tmp_path):
        assert resolve_module_path("a/b/c", tmp_path) == (
            tmp_path / "a" / "b" / "c.lob"
        )


# ── parse_lob_refs ────────────────────────────────────────────

class TestParseLobRefs:
    def test_single_ref(self):
        lines = ["    #Roman Numerals"]
        assert parse_lob_refs(lines) == ["roman/numerals"]

    def test_multiword_title(self):
        lines = ["    #Pricing Discount Strategies"]
        assert parse_lob_refs(lines) == ["pricing/discount/strategies"]

    def test_mixed_with_python_imports(self):
        lines = [
            "    #Roman Numerals",
            "    from decimal import Decimal",
            "    #Pricing Discounts",
        ]
        assert parse_lob_refs(lines) == ["roman/numerals", "pricing/discounts"]

    def test_no_refs_returns_empty(self):
        lines = ["    from pathlib import Path", "    import os"]
        assert parse_lob_refs(lines) == []

    def test_blank_lines_ignored(self):
        lines = ["", "    #Roman Numerals", ""]
        assert parse_lob_refs(lines) == ["roman/numerals"]

    def test_empty_input(self):
        assert parse_lob_refs([]) == []

    def test_bare_hash_ignored(self):
        # A bare "#" with no label should not produce a ref
        lines = ["    #"]
        assert parse_lob_refs(lines) == []

    def test_single_word_title(self):
        lines = ["    #Pricing"]
        assert parse_lob_refs(lines) == ["pricing"]

    def test_preserves_order(self):
        lines = ["    #A B", "    #C D", "    #E F"]
        assert parse_lob_refs(lines) == ["a/b", "c/d", "e/f"]


# ── parse_python_imports ──────────────────────────────────────

class TestParsePythonImports:
    def test_returns_non_hash_lines(self):
        lines = ["    from decimal import Decimal"]
        assert parse_python_imports(lines) == lines

    def test_filters_out_lob_refs(self):
        lines = [
            "    #Roman Numerals",
            "    from decimal import Decimal",
        ]
        assert parse_python_imports(lines) == ["    from decimal import Decimal"]

    def test_preserves_blank_lines(self):
        lines = ["    import os", "", "    import sys"]
        assert parse_python_imports(lines) == lines

    def test_empty_input(self):
        assert parse_python_imports([]) == []

    def test_all_lob_refs_returns_empty(self):
        lines = ["    #Roman Numerals", "    #Pricing Discounts"]
        assert parse_python_imports(lines) == []

    def test_preserves_indentation(self):
        lines = ["    from pathlib import Path"]
        result = parse_python_imports(lines)
        assert result[0].startswith("    ")


# ── transitive_lob_refs ───────────────────────────────────────

def _write(tmp_path: Path, name: str, content: str) -> None:
    (tmp_path / name).write_text(content, encoding="utf-8")


def _binding(tmp_path: Path) -> None:
    _write(tmp_path, "binding.lob",
           "#P\n\n---\n\n#Binding\n    ~language python\n")


class TestTransitiveLobRefs:
    def test_direct_dep_included(self, tmp_path):
        _binding(tmp_path)
        _write(tmp_path, "util.lob", "#Util\n\n    x = 1\n")
        _write(tmp_path, "main.lob",
               "#Main\n\n    y = 2\n---\n\n#References\n    #Util\n")
        from notlob import from_tree, parse_file
        mod = from_tree(parse_file(tmp_path / "main.lob"))
        refs = transitive_lob_refs(mod, tmp_path)
        assert "util" in refs

    def test_transitive_dep_included(self, tmp_path):
        _binding(tmp_path)
        _write(tmp_path, "base.lob", "#Base\n\n    b = 0\n")
        _write(tmp_path, "mid.lob",
               "#Mid\n\n    m = 1\n---\n\n#References\n    #Base\n")
        _write(tmp_path, "main.lob",
               "#Main\n\n    z = 2\n---\n\n#References\n    #Mid\n")
        from notlob import from_tree, parse_file
        mod = from_tree(parse_file(tmp_path / "main.lob"))
        refs = transitive_lob_refs(mod, tmp_path)
        assert "base" in refs
        assert "mid" in refs
        assert refs.index("base") < refs.index("mid")

    def test_root_module_not_in_result(self, tmp_path):
        _binding(tmp_path)
        _write(tmp_path, "util.lob", "#Util\n\n    x = 1\n")
        _write(tmp_path, "main.lob",
               "#Main\n\n    y = 2\n---\n\n#References\n    #Util\n")
        from notlob import from_tree, parse_file
        mod = from_tree(parse_file(tmp_path / "main.lob"))
        refs = transitive_lob_refs(mod, tmp_path)
        assert "main" not in refs

    def test_no_deps_returns_empty(self, tmp_path):
        _binding(tmp_path)
        _write(tmp_path, "main.lob", "#Main\n\n    x = 1\n")
        from notlob import from_tree, parse_file
        mod = from_tree(parse_file(tmp_path / "main.lob"))
        assert transitive_lob_refs(mod, tmp_path) == []

    def test_diamond_dep_included_once(self, tmp_path):
        # A imports B and C; B and C both import D.  D should appear once.
        _binding(tmp_path)
        _write(tmp_path, "d.lob", "#D\n\n    d = 0\n")
        _write(tmp_path, "b.lob",
               "#B\n\n    b = 1\n---\n\n#References\n    #D\n")
        _write(tmp_path, "c.lob",
               "#C\n\n    c = 2\n---\n\n#References\n    #D\n")
        _write(tmp_path, "a.lob",
               "#A\n\n    a = 3\n---\n\n#References\n    #B\n    #C\n")
        from notlob import from_tree, parse_file
        mod = from_tree(parse_file(tmp_path / "a.lob"))
        refs = transitive_lob_refs(mod, tmp_path)
        assert refs.count("d") == 1
