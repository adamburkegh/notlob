"""Tests for NameGraph serialisation and new query methods.

Covers to_dict(), to_json(), search(), and parents().
"""

import json
from pathlib import Path

import pytest

from notlob import (
    parse, from_tree, build, enrich,
    Edge, EdgeKind, NodeKind,
)
from notlob.bindings.python import extract_symbols


def _graph(source: str):
    mod = from_tree(parse(source))
    g   = build(mod)
    enrich(g, mod, extract_symbols)
    return g


EXAMPLES = Path(__file__).parent.parent / "examples"
SCHEMA   = (
    Path(__file__).parent.parent
    / "notlob" / "schema" / "name_graph.json"
)


# ── to_dict ───────────────────────────────────────────────────

class TestToDict:
    def test_has_nodes_and_edges_keys(self):
        d = _graph("#T\n").to_dict()
        assert set(d.keys()) == {"nodes", "edges"}

    def test_node_shape(self):
        d = _graph("#Roman Numerals\n").to_dict()
        node = next(n for n in d["nodes"] if n["kind"] == "MODULE")
        assert set(node.keys()) == {"address", "label", "kind"}
        assert node["address"] == "roman/numerals"
        assert node["label"]   == "Roman Numerals"
        assert node["kind"]    == "MODULE"

    def test_edge_shape(self):
        d = _graph("#T\n##Section\n    code\n").to_dict()
        edge = next(e for e in d["edges"] if e["kind"] == "CONTAINS")
        assert set(edge.keys()) == {"source", "target", "kind"}
        assert edge["source"] == "t"
        assert edge["target"] == "t#Section"

    def test_all_node_kinds_serialise(self):
        src = (
            "#T\n"
            "##Sub\n"
            "    def f(): pass\n"
            "~property commutativity\n"
            "    def _(x): pass\n"
        )
        d     = _graph(src).to_dict()
        kinds = {n["kind"] for n in d["nodes"]}
        assert "MODULE"     in kinds
        assert "SUBHEADING" in kinds
        assert "SYMBOL"     in kinds
        assert "PROPERTY"   in kinds

    def test_all_edge_kinds_serialise(self):
        src = "#A\n##S\n    def f(): pass\n"
        g   = _graph(src)
        src2 = "#B\n"
        g2   = _graph(src2)
        g.merge(g2)
        g.add_edge(Edge(source="a", target="b", kind=EdgeKind.IMPORTS))
        d     = g.to_dict()
        kinds = {e["kind"] for e in d["edges"]}
        assert "CONTAINS" in kinds
        assert "DEFINES"  in kinds
        assert "IMPORTS"  in kinds

    def test_round_trips_via_json(self):
        g = _graph("#Roman Numerals\n##Decoding\n    def f(): pass\n")
        d = json.loads(g.to_json())
        assert isinstance(d["nodes"], list)
        assert isinstance(d["edges"], list)
        assert all(
            {"address", "label", "kind"} <= set(n.keys())
            for n in d["nodes"]
        )


# ── to_json ───────────────────────────────────────────────────

class TestToJson:
    def test_is_valid_json(self):
        g = _graph("#T\n##S\n    code\n")
        parsed = json.loads(g.to_json())
        assert "nodes" in parsed

    def test_pretty_printed_by_default(self):
        raw = _graph("#T\n").to_json()
        assert "\n" in raw

    def test_compact_with_none_indent(self):
        raw = _graph("#T\n").to_json(indent=None)
        assert "\n" not in raw


# ── JSON schema file ──────────────────────────────────────────

class TestSchema:
    def test_schema_file_exists(self):
        assert SCHEMA.exists()

    def test_schema_is_valid_json(self):
        data = json.loads(SCHEMA.read_text(encoding="utf-8"))
        assert data["title"] == "NameGraph"

    def test_schema_node_kinds_match_enum(self):
        data  = json.loads(SCHEMA.read_text(encoding="utf-8"))
        kinds = data["definitions"]["Node"]["properties"]["kind"]["enum"]
        assert set(kinds) == {k.name for k in NodeKind}

    def test_schema_edge_kinds_match_enum(self):
        data  = json.loads(SCHEMA.read_text(encoding="utf-8"))
        kinds = data["definitions"]["Edge"]["properties"]["kind"]["enum"]
        assert set(kinds) == {k.name for k in EdgeKind}


# ── search ────────────────────────────────────────────────────

class TestSearch:
    def test_exact_match(self):
        g = _graph("#T\n    def apply_discount(): pass\n")
        results = list(g.search("apply_discount"))
        assert len(results) == 1
        assert results[0].label == "apply_discount"

    def test_wildcard_suffix(self):
        src = (
            "#T\n"
            "    def apply_discount(): pass\n"
            "    def apply_tax(): pass\n"
            "    def compute(): pass\n"
        )
        g       = _graph(src)
        labels  = {n.label for n in g.search("apply_*")}
        assert labels == {"apply_discount", "apply_tax"}

    def test_wildcard_prefix_and_suffix(self):
        src = (
            "#T\n"
            "    def to_roman(): pass\n"
            "    def from_roman(): pass\n"
            "    def helper(): pass\n"
        )
        g      = _graph(src)
        labels = {n.label for n in g.search("*roman*")}
        assert labels == {"to_roman", "from_roman"}

    def test_filter_by_kind(self):
        src = "#T\n##Decoding\n    def from_roman(): pass\n"
        g   = _graph(src)
        # "Decoding" is a SUBHEADING — should not appear when filtering SYMBOL
        syms = list(g.search("*", NodeKind.SYMBOL))
        assert all(n.kind == NodeKind.SYMBOL for n in syms)

    def test_no_match_returns_empty(self):
        g = _graph("#T\n")
        assert list(g.search("nonexistent")) == []

    def test_search_all_with_star(self):
        src = "#T\n##S\n    def f(): pass\n"
        g   = _graph(src)
        assert len(list(g.search("*"))) == len(g)


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


# ── Integration ───────────────────────────────────────────────

class TestIntegration:
    def test_roman_export_is_valid(self):
        mod = from_tree(__import__(
            "notlob", fromlist=["parse_file"]
        ).parse_file(EXAMPLES / "roman/roman/numerals.lob"))
        g   = build(mod)
        enrich(g, mod, extract_symbols)
        d   = g.to_dict()
        addrs = {n["address"] for n in d["nodes"]}
        assert "roman/numerals" in addrs
        assert "roman/numerals#to_roman" in addrs

    def test_search_symbols_in_roman(self):
        from notlob import parse_file
        mod = from_tree(parse_file(
            EXAMPLES / "roman/roman/numerals.lob"
        ))
        g = build(mod)
        enrich(g, mod, extract_symbols)
        results = list(g.search("*roman*", NodeKind.SYMBOL))
        labels  = {n.label for n in results}
        assert "to_roman"   in labels
        assert "from_roman" in labels
