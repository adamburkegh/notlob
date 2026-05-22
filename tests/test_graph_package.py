"""Tests for the package-spanning name-graph.

Covers the three additions that lift the graph from single-file to
package scope:

  - EdgeKind.IMPORTS  — declared lob-ref dependency between modules.
  - build_package()   — discovers all .lob files, merges their graphs,
                        and adds IMPORTS edges from #References.
  - resolve() step 3  — restricted to IMPORTS edges when context is
                        given (unimported modules are invisible).
"""

from pathlib import Path

import pytest

from notlob import (
    build, build_package,
    NameGraph, Node, NodeKind, Edge, EdgeKind,
)
from notlob.bindings.python import extract_symbols

EXAMPLES = Path(__file__).parent.parent / "examples"


# ── IMPORTS edge basics ──────────────────────────────────────

class TestImportsEdge:
    def test_imports_kind_exists(self):
        assert EdgeKind.IMPORTS is not None

    def test_add_imports_edge_and_query(self):
        g = NameGraph()
        g.add_node(Node("mod/a", "Mod A", NodeKind.MODULE))
        g.add_node(Node("mod/b", "Mod B", NodeKind.MODULE))
        g.add_edge(Edge("mod/a", "mod/b", EdgeKind.IMPORTS))
        imported = list(g.children("mod/a", EdgeKind.IMPORTS))
        assert len(imported) == 1
        assert imported[0].address == "mod/b"

    def test_imports_does_not_appear_in_contains_children(self):
        g = NameGraph()
        g.add_node(Node("mod/a", "Mod A", NodeKind.MODULE))
        g.add_node(Node("mod/b", "Mod B", NodeKind.MODULE))
        g.add_edge(Edge("mod/a", "mod/b", EdgeKind.IMPORTS))
        # children() defaults to CONTAINS — IMPORTS edge is separate
        contains = list(g.children("mod/a"))
        assert not any(n.address == "mod/b" for n in contains)

    def test_multiple_imports(self):
        g = NameGraph()
        for addr, label in [("a", "A"), ("b", "B"), ("c", "C")]:
            g.add_node(Node(addr, label, NodeKind.MODULE))
        g.add_edge(Edge("a", "b", EdgeKind.IMPORTS))
        g.add_edge(Edge("a", "c", EdgeKind.IMPORTS))
        imported = {n.address for n in g.children("a", EdgeKind.IMPORTS)}
        assert imported == {"b", "c"}


# ── resolve() step 3 with IMPORTS edges ─────────────────────

class TestResolveStep3:
    def _two_module_graph(self) -> NameGraph:
        """Graph with modules 'A' and 'B', no edges yet."""
        g = NameGraph()
        g.add_node(Node("a", "A", NodeKind.MODULE))
        g.add_node(Node("b", "B", NodeKind.MODULE))
        return g

    def test_imported_module_resolves_in_context(self):
        g = self._two_module_graph()
        g.add_edge(Edge("a", "b", EdgeKind.IMPORTS))
        node = g.resolve("B", context="a")
        assert node is not None
        assert node.kind == NodeKind.MODULE
        assert node.address == "b"

    def test_unimported_module_invisible_in_context(self):
        g = self._two_module_graph()
        # B is in the graph but A doesn't import it
        assert g.resolve("B", context="a") is None

    def test_full_scan_without_context(self):
        g = self._two_module_graph()
        # No context — find any MODULE by label
        node = g.resolve("B")
        assert node is not None
        assert node.kind == NodeKind.MODULE

    def test_step1_still_works_with_imports_edges(self):
        # IMPORTS edge doesn't interfere with step-1 symbol lookup
        from notlob import parse, from_tree, enrich
        module = from_tree(parse("#T\n    def f(): pass\n"))
        g = build(module)
        enrich(g, module, extract_symbols)
        g.add_node(Node("other", "Other", NodeKind.MODULE))
        g.add_edge(Edge("t", "other", EdgeKind.IMPORTS))
        node = g.resolve("f", context="t")
        assert node is not None
        assert node.kind == NodeKind.SYMBOL

    def test_imports_edge_in_wrong_direction_not_visible(self):
        # B imports A, not the other way around
        g = self._two_module_graph()
        g.add_edge(Edge("b", "a", EdgeKind.IMPORTS))
        # A cannot resolve B (A doesn't import B)
        assert g.resolve("B", context="a") is None
        # B can resolve A
        node = g.resolve("A", context="b")
        assert node is not None
        assert node.address == "a"


# ── build_package() ──────────────────────────────────────────

class TestBuildPackage:
    def test_discovers_all_lob_files(self, tmp_path):
        (tmp_path / "a.lob").write_text(
            "#Pkg A\n", encoding="utf-8"
        )
        (tmp_path / "b.lob").write_text(
            "#Pkg B\n", encoding="utf-8"
        )
        g = build_package(tmp_path)
        assert g.node("pkg/a") is not None
        assert g.node("pkg/b") is not None

    def test_discovers_nested_lob_files(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "mod.lob").write_text(
            "#Sub Mod\n", encoding="utf-8"
        )
        g = build_package(tmp_path)
        assert g.node("sub/mod") is not None

    def test_adds_imports_edges_from_references(self, tmp_path):
        (tmp_path / "a.lob").write_text(
            "#A\n\n---\n\n#References\n    #B\n",
            encoding="utf-8",
        )
        (tmp_path / "b.lob").write_text(
            "#B\n", encoding="utf-8"
        )
        g = build_package(tmp_path)
        imported = list(g.children("a", EdgeKind.IMPORTS))
        assert len(imported) == 1
        assert imported[0].address == "b"

    def test_dangling_ref_produces_no_edge(self, tmp_path):
        # A declares #Missing but missing.lob is not in the package
        (tmp_path / "a.lob").write_text(
            "#A\n\n---\n\n#References\n    #Missing\n",
            encoding="utf-8",
        )
        g = build_package(tmp_path)
        imported = list(g.children("a", EdgeKind.IMPORTS))
        assert imported == []

    def test_duplicate_ref_produces_one_edge(self, tmp_path):
        (tmp_path / "a.lob").write_text(
            "#A\n\n---\n\n#References\n    #B\n    #B\n",
            encoding="utf-8",
        )
        (tmp_path / "b.lob").write_text(
            "#B\n", encoding="utf-8"
        )
        g = build_package(tmp_path)
        imported = list(g.children("a", EdgeKind.IMPORTS))
        assert len(imported) == 1

    def test_unparseable_file_is_skipped(self, tmp_path):
        (tmp_path / "good.lob").write_text(
            "#Good\n", encoding="utf-8"
        )
        # A file with no title will fail the parser
        (tmp_path / "bad.lob").write_text(
            "not a lob file at all\n", encoding="utf-8"
        )
        g = build_package(tmp_path)
        assert g.node("good") is not None

    def test_empty_package(self, tmp_path):
        # No .lob files — returns an empty graph, not an error
        g = build_package(tmp_path)
        assert len(g) == 0

    def test_with_extractor_adds_symbols(self, tmp_path):
        (tmp_path / "a.lob").write_text(
            "#A\n\n    def f(): pass\n",
            encoding="utf-8",
        )
        g = build_package(tmp_path, extractor=extract_symbols)
        assert g.node("a#f") is not None

    def test_without_extractor_no_symbols(self, tmp_path):
        (tmp_path / "a.lob").write_text(
            "#A\n\n    def f(): pass\n",
            encoding="utf-8",
        )
        g = build_package(tmp_path)
        assert g.node("a#f") is None

    def test_resolve_imported_module_in_package_context(self, tmp_path):
        # After build_package, resolve() uses IMPORTS edges
        (tmp_path / "importer.lob").write_text(
            "#Importer\n\n---\n\n#References\n    #Target\n",
            encoding="utf-8",
        )
        (tmp_path / "target.lob").write_text(
            "#Target\n", encoding="utf-8"
        )
        g = build_package(tmp_path)
        node = g.resolve("Target", context="importer")
        assert node is not None
        assert node.kind == NodeKind.MODULE

    def test_resolve_unimported_module_in_package_context(self, tmp_path):
        # A module in the package that is not imported is invisible
        (tmp_path / "importer.lob").write_text(
            "#Importer\n", encoding="utf-8"
        )
        (tmp_path / "target.lob").write_text(
            "#Target\n", encoding="utf-8"
        )
        g = build_package(tmp_path)
        assert g.resolve("Target", context="importer") is None


# ── Integration: litstats example ────────────────────────────

class TestLitstatsIntegration:
    ROOT = EXAMPLES / "litstats"

    @pytest.fixture
    def pkg(self):
        return build_package(self.ROOT)

    def test_corpus_module_present(self, pkg):
        assert pkg.node("litstats/corpus") is not None

    def test_hamlet_module_present(self, pkg):
        assert pkg.node("litstats/hamlet") is not None

    def test_hamlet_imports_corpus(self, pkg):
        imported = [
            n for n in pkg.children("litstats/hamlet", EdgeKind.IMPORTS)
        ]
        assert any(n.address == "litstats/corpus" for n in imported)

    def test_corpus_imports_nothing(self, pkg):
        # corpus.lob has only Python imports, no lob-ref imports
        imported = list(pkg.children("litstats/corpus", EdgeKind.IMPORTS))
        assert imported == []

    def test_resolve_corpus_from_hamlet_context(self, pkg):
        node = pkg.resolve("Litstats Corpus", context="litstats/hamlet")
        assert node is not None
        assert node.kind == NodeKind.MODULE

    def test_corpus_not_visible_without_import(self, pkg):
        # binding.lob doesn't import corpus — should not resolve
        binding_addr = "litstats"   # #Litstats → litstats
        node = pkg.resolve("Litstats Corpus", context=binding_addr)
        assert node is None

    def test_with_symbols(self, pkg_with_symbols):
        # corpus functions appear as symbols
        assert pkg_with_symbols.node(
            "litstats/corpus#load_play"
        ) is not None
        assert pkg_with_symbols.node(
            "litstats/corpus#word_frequencies"
        ) is not None
        assert pkg_with_symbols.node(
            "litstats/corpus#parse_speakers"
        ) is not None

    @pytest.fixture
    def pkg_with_symbols(self):
        return build_package(self.ROOT, extractor=extract_symbols)
