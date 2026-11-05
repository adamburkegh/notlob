"""Tests for the graph's queries: a section's prose, ``search()`` and
``parents()``, and the schema's kinds.

What a graph writes is in ``test_view.py`` (the view and its writers) and
``test_graph_document.py`` (the document, held to its schema).
"""

import json
from pathlib import Path

from notlob import (
    parse, from_tree, build, enrich,
    Edge, EdgeKind, NodeKind,
)
from notlob.bindings.python import extract_symbols
from notlob.graph import PRESETS


def _graph(source: str):
    mod = from_tree(parse(source))
    g   = build(mod)
    enrich(g, mod, extract_symbols)
    return g


SCHEMA   = (
    Path(__file__).parent.parent
    / "notlob" / "schema" / "name_graph.json"
)


# ── The prose of a section ────────────────────────────────────

class TestSectionProse:
    """What a section's prose is, as the graph answers it (`prose()` and
    `bullet_list_count()`), which the checks read."""

    def test_module_prose_captured(self):
        g = _graph("#T\nSome introductory text.\n")
        assert "introductory" in g.prose("t")

    def test_paragraphs_are_separated_not_run_together(self):
        """Two prose paragraphs must not be glued into 'one.Two': the
        join dropped the paragraph break, so a sentence boundary
        vanished from the stored prose (and from the `quantifier`
        advisory built on it)."""
        g = _graph("#T\n\nFirst paragraph.\n\nSecond paragraph.\n")
        prose = g.prose("t")
        assert "paragraph.Second" not in prose
        assert "First paragraph." in prose and "Second paragraph." in prose
        assert prose.index("First") < prose.index("Second")

    def test_prose_and_bullets_are_separated(self):
        g = _graph("#T\n\nIntro text.\n\n* one\n* two\n\nOutro text.\n")
        prose = g.prose("t")
        assert "text.* one" not in prose
        assert "two" in prose and "Outro" in prose
        assert "twoOutro" not in prose

    def test_single_paragraph_prose_is_unchanged(self):
        """A paragraph's own spans (text and inline refs) still join
        without added separators."""
        g = _graph("#T\n\nSee ##Section for details.\n\n##Section\n")
        assert g.prose("t") == "See ##Section for details."

    def test_subheading_prose_captured(self):
        g = _graph("#T\n##Section\nSection prose here.\n    code\n")
        assert "Section prose" in g.prose("t#Section")

    def test_module_with_only_code_has_no_prose(self):
        assert _graph("#T\n    def f(): pass\n").prose("t") == ""

    def test_inline_ref_in_prose_preserved(self):
        # Refs are re-serialised as "#Label" in the prose string.
        g = _graph("#Module A\nSee #Roman Numerals for details.\n")
        assert "#Roman Numerals" in g.prose("module/a")

    def test_the_bullet_count(self):
        g = _graph("#T\n\nIntro.\n\n* one\n* two\n")
        assert g.bullet_list_count("t") == 1


# ── JSON schema file ──────────────────────────────────────────

class TestSchema:
    def test_schema_file_exists(self):
        assert SCHEMA.exists()

    def test_schema_is_valid_json(self):
        data = json.loads(SCHEMA.read_text(encoding="utf-8"))
        assert data["title"] == "NameGraph"

    def test_schema_node_kinds_match_enum(self):
        data  = json.loads(SCHEMA.read_text(encoding="utf-8"))
        kinds = data["definitions"]["GraphNode"]["properties"]["kind"][
            "enum"]
        assert set(kinds) == {k.name for k in NodeKind}

    def test_schema_edge_kinds_are_the_enum(self):
        data  = json.loads(SCHEMA.read_text(encoding="utf-8"))
        kinds = data["definitions"]["GraphEdge"]["properties"]["kind"][
            "enum"]
        assert set(kinds) == {k.name for k in EdgeKind}

    def test_schema_levels_are_the_presets(self):
        data = json.loads(SCHEMA.read_text(encoding="utf-8"))
        assert tuple(data["properties"]["level"]["enum"]) == tuple(PRESETS)


# ── search ────────────────────────────────────────────────────

class TestSearch:
    def test_exact_match(self):
        g = _graph("#T\n    def apply_discount(): pass\n")
        results = list(g.search("apply_discount"))
        assert len(results) == 1
        assert results[0].name == "apply_discount"

    def test_wildcard_suffix(self):
        src = (
            "#T\n"
            "    def apply_discount(): pass\n"
            "    def apply_tax(): pass\n"
            "    def compute(): pass\n"
        )
        g       = _graph(src)
        names   = {n.name for n in g.search("apply_*")}
        assert names == {"apply_discount", "apply_tax"}

    def test_wildcard_prefix_and_suffix(self):
        src = (
            "#T\n"
            "    def to_roman(): pass\n"
            "    def from_roman(): pass\n"
            "    def helper(): pass\n"
        )
        g      = _graph(src)
        names = {n.name for n in g.search("*roman*")}
        assert names == {"to_roman", "from_roman"}

    def test_filter_by_kind(self):
        src = "#T\n##Decoding\n    def from_roman(): pass\n"
        g   = _graph(src)
        # "Decoding" is a SUBHEADING — should not appear when filtering SYMBOL
        syms = list(g.search("*", NodeKind.SYMBOL))
        assert all(n.kind == NodeKind.SYMBOL for n in syms)

    def test_no_match_returns_empty(self):
        g = _graph("#T\n")
        assert list(g.search("nonexistent")) == []

    def test_search_all_with_star_finds_every_named_node(self):
        src = "#T\n##S\n    def f(): pass\n"
        g   = _graph(src)
        found = {n.address for n in g.search("*")}
        assert found == {n.address for n in g.nodes() if n.name}
        assert found == {"t", "t#S", "t#f"}


# ── parents ───────────────────────────────────────────────────

class TestParents:
    def test_imported_by(self):
        g  = _graph("#Module A\n")
        g2 = _graph("#Module B\n")
        g.merge(g2)
        g.add_edge(Edge(
            source="module/b",
            target="module/a",
            kind=EdgeKind.IMPORTS,
        ))
        result = list(g.parents("module/a", EdgeKind.IMPORTS))
        assert len(result) == 1
        assert result[0].address == "module/b"

    def test_multiple_importers(self):
        g  = _graph("#Lib\n")
        g2 = _graph("#App One\n")
        g3 = _graph("#App Two\n")
        g.merge(g2)
        g.merge(g3)
        g.add_edge(Edge(source="app/one", target="lib", kind=EdgeKind.IMPORTS))
        g.add_edge(Edge(source="app/two", target="lib", kind=EdgeKind.IMPORTS))
        addrs = {n.address for n in g.parents("lib", EdgeKind.IMPORTS)}
        assert addrs == {"app/one", "app/two"}

    def test_no_importers_returns_empty(self):
        g = _graph("#Lib\n")
        assert list(g.parents("lib", EdgeKind.IMPORTS)) == []

    def test_contains_parents(self):
        # parents() works for CONTAINS too: find which module contains a sub
        g = _graph("#T\n##Section\n    code\n")
        result = list(g.parents("t#Section", EdgeKind.CONTAINS))
        assert len(result) == 1
        assert result[0].address == "t"
