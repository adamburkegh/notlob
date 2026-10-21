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


# ── load_dependency_modules ───────────────────────────────────

def _load(tmp_path: Path, name: str):
    from notlob import from_tree, parse_file
    return from_tree(parse_file(tmp_path / name))


class TestLoadDependencyModules:
    """The one place that says which modules a module's code needs in
    order to run: its lob-refs, and theirs, transitively, each once,
    dependencies first. Python, Haskell and TypeScript all load through
    it (it was three private loops, two of them direct-only)."""

    def _titles(self, tmp_path, name):
        from notlob.project import load_dependency_modules
        mods = load_dependency_modules(_load(tmp_path, name), tmp_path)
        return [m.title for m in mods]

    def test_returns_parsed_modules_not_addresses(self, tmp_path):
        from notlob.model import Module
        from notlob.project import load_dependency_modules
        _binding(tmp_path)
        _write(tmp_path, "util.lob", "#Util\n\n    x = 1\n")
        _write(tmp_path, "main.lob",
               "#Main\n\n    y = 2\n---\n\n#References\n    #Util\n")
        mods = load_dependency_modules(_load(tmp_path, "main.lob"), tmp_path)
        assert all(isinstance(m, Module) for m in mods)
        assert [m.title for m in mods] == ["Util"]

    def test_follows_references_of_references(self, tmp_path):
        _binding(tmp_path)
        _write(tmp_path, "base.lob", "#Base\n\n    b = 0\n")
        _write(tmp_path, "mid.lob",
               "#Mid\n\n    m = 1\n---\n\n#References\n    #Base\n")
        _write(tmp_path, "top.lob",
               "#Top\n\n    t = 2\n---\n\n#References\n    #Mid\n")
        assert self._titles(tmp_path, "top.lob") == ["Base", "Mid"]

    def test_dependencies_come_before_their_dependents(self, tmp_path):
        """Whatever order the references are listed in."""
        _binding(tmp_path)
        _write(tmp_path, "base.lob", "#Base\n\n    b = 0\n")
        _write(tmp_path, "mid.lob",
               "#Mid\n\n    m = 1\n---\n\n#References\n    #Base\n")
        _write(tmp_path, "listed_wrong.lob",
               "#Listed Wrong\n\n    t = 2\n---\n\n"
               "#References\n    #Mid\n    #Base\n")
        assert self._titles(tmp_path, "listed_wrong.lob") == ["Base", "Mid"]

    def test_a_diamond_loads_the_shared_module_once(self, tmp_path):
        _binding(tmp_path)
        _write(tmp_path, "d.lob", "#D\n\n    d = 0\n")
        _write(tmp_path, "b.lob",
               "#B\n\n    b = 1\n---\n\n#References\n    #D\n")
        _write(tmp_path, "c.lob",
               "#C\n\n    c = 2\n---\n\n#References\n    #D\n")
        _write(tmp_path, "a.lob",
               "#A\n\n    a = 3\n---\n\n#References\n    #B\n    #C\n")
        titles = self._titles(tmp_path, "a.lob")
        assert titles.count("D") == 1
        assert titles.index("D") < titles.index("B")
        assert titles.index("D") < titles.index("C")

    def test_listings_that_cite_each_other_terminate_and_load_nothing(
        self, tmp_path,
    ):
        """With a binding that can tell use (the Python kit), two modules
        that list each other but whose code uses neither are citations."""
        from notlob.bindings.python import kit
        from notlob.project import load_dependency_modules
        _binding(tmp_path)
        _write(tmp_path, "x.lob",
               "#X\n\n    x = 1\n---\n\n#References\n    #Y\n")
        _write(tmp_path, "y.lob",
               "#Y\n\n    y = 2\n---\n\n#References\n    #X\n")
        assert load_dependency_modules(
            _load(tmp_path, "x.lob"), tmp_path, kit) == []

    def test_without_a_kit_mutual_listings_are_a_cycle(self, tmp_path):
        """Use cannot be determined, so the tree decides (neither module
        is below the other): each listing is followed, and that is a
        cycle, reported rather than looped on."""
        from notlob.project import LobRefCycleError, load_dependency_modules
        _binding(tmp_path)
        _write(tmp_path, "x.lob",
               "#X\n\n    x = 1\n---\n\n#References\n    #Y\n")
        _write(tmp_path, "y.lob",
               "#Y\n\n    y = 2\n---\n\n#References\n    #X\n")
        with pytest.raises(LobRefCycleError) as caught:
            load_dependency_modules(_load(tmp_path, "x.lob"), tmp_path)
        assert caught.value.cycle == ["x", "y", "x"]

    def test_a_missing_dependency_is_skipped_not_fatal(self, tmp_path):
        """Its absence surfaces where it is used, as a NameError or a
        compile error, in the usual claim-result machinery."""
        _binding(tmp_path)
        _write(tmp_path, "main.lob",
               "#Main\n\n    y = 2\n---\n\n#References\n    #Nowhere\n")
        assert self._titles(tmp_path, "main.lob") == []

    def test_no_references_no_modules(self, tmp_path):
        _binding(tmp_path)
        _write(tmp_path, "main.lob", "#Main\n\n    x = 1\n")
        assert self._titles(tmp_path, "main.lob") == []

    def test_the_module_itself_is_not_included(self, tmp_path):
        _binding(tmp_path)
        _write(tmp_path, "util.lob", "#Util\n\n    x = 1\n")
        _write(tmp_path, "main.lob",
               "#Main\n\n    y = 2\n---\n\n#References\n    #Util\n")
        assert "Main" not in self._titles(tmp_path, "main.lob")
