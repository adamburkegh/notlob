"""Tests for NameGraph serialisation and new query methods.

Covers to_dict(), to_json(), search(), and parents().
Schema conformance is validated using jsonschema against
notlob/schema/name_graph.json.
"""

import json
from pathlib import Path

import jsonschema
import pytest

from notlob import (
    parse, parse_file, from_tree, build, enrich,
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


# ── content ───────────────────────────────────────────────────

class TestContent:
    """Node.content is populated at build/enrich time and emitted
    in to_dict() only when include_content=True."""

    def test_content_absent_by_default(self):
        d = _graph("#T\n    def f(): pass\n").to_dict()
        for node in d["nodes"]:
            assert "content" not in node

    def test_content_present_when_requested(self):
        d = _graph("#T\n    def f(): pass\n").to_dict(
            include_content=True
        )
        assert any("content" in n for n in d["nodes"])

    def test_module_prose_captured(self):
        g = _graph("#T\nSome introductory text.\n")
        d = g.to_dict(include_content=True)
        mod = next(n for n in d["nodes"] if n["kind"] == "MODULE")
        assert "content" in mod
        assert "introductory" in mod["content"]["prose"]

    def test_subheading_prose_captured(self):
        g = _graph("#T\n##Section\nSection prose here.\n    code\n")
        d = g.to_dict(include_content=True)
        sub = next(
            n for n in d["nodes"] if n["kind"] == "SUBHEADING"
        )
        assert "Section prose" in sub["content"]["prose"]

    def test_subheading_code_captured(self):
        g = _graph("#T\n##Section\n    def decode(): pass\n")
        d = g.to_dict(include_content=True)
        sub = next(
            n for n in d["nodes"] if n["kind"] == "SUBHEADING"
        )
        assert "def decode" in sub["content"]["code"]

    def test_symbol_code_captured(self):
        g = _graph("#T\n    def to_roman(n): return str(n)\n")
        d = g.to_dict(include_content=True)
        sym = next(n for n in d["nodes"] if n["kind"] == "SYMBOL")
        assert "def to_roman" in sym["content"]["code"]

    def test_symbol_source_is_per_definition(self):
        # Two functions in the same block get separate source slices.
        src = "#T\n    def f(): pass\n    def g(): pass\n"
        g = _graph(src)
        d = g.to_dict(include_content=True)
        syms = {
            n["label"]: n
            for n in d["nodes"] if n["kind"] == "SYMBOL"
        }
        assert "def f" in syms["f"]["content"]["code"]
        assert "def g" not in syms["f"]["content"]["code"]
        assert "def g" in syms["g"]["content"]["code"]
        assert "def f" not in syms["g"]["content"]["code"]

    def test_module_no_prose_no_prose_key(self):
        # A module with only code has no "prose" key in content.
        g = _graph("#T\n    def f(): pass\n")
        d = g.to_dict(include_content=True)
        mod = next(n for n in d["nodes"] if n["kind"] == "MODULE")
        assert "prose" not in mod.get("content", {})

    def test_node_with_no_content_omitted(self):
        # A module heading with only subheadings and no own prose/code
        # should have content omitted entirely.
        g = _graph("#T\n##Only Section\n    code\n")
        d = g.to_dict(include_content=True)
        mod = next(n for n in d["nodes"] if n["kind"] == "MODULE")
        assert "content" not in mod

    def test_inline_ref_in_prose_preserved(self):
        # Refs are re-serialised as "#Label" in the prose string.
        src = (
            "#Module A\n"
            "See #Roman Numerals for details.\n"
            "---\n"
            "#References\n"
            "    #Roman Numerals\n"
        )
        mod_a = from_tree(parse(src))
        mod_b = from_tree(parse("#Roman Numerals\n"))
        g = build(mod_a)
        enrich(g, mod_a, extract_symbols)
        g.merge(build(mod_b))
        g.add_edge(Edge(
            source="module/a", target="roman/numerals",
            kind=EdgeKind.IMPORTS,
        ))
        d = g.to_dict(include_content=True)
        mod = next(
            n for n in d["nodes"] if n["address"] == "module/a"
        )
        assert "#Roman Numerals" in mod["content"]["prose"]

    def test_property_code_captured(self):
        src = "#T\n~property commutativity\n    def _(x): pass\n"
        g = _graph(src)
        d = g.to_dict(include_content=True)
        prop = next(
            n for n in d["nodes"] if n["kind"] == "PROPERTY"
        )
        assert "def _" in prop["content"]["code"]

    def test_to_json_include_content(self):
        raw = _graph("#T\n    def f(): pass\n").to_json(
            include_content=True
        )
        data = json.loads(raw)
        syms = [n for n in data["nodes"] if n["kind"] == "SYMBOL"]
        assert all("content" in s for s in syms)

    def test_schema_validates_with_content(self):
        g = _graph(
            "#T\n##S\nProse.\n    def f(): pass\n"
            "~property p\n    def _(x): pass\n"
        )
        jsonschema.validate(g.to_dict(include_content=True), _SCHEMA)

    def test_schema_validates_without_content(self):
        g = _graph("#T\n##S\n    def f(): pass\n")
        jsonschema.validate(g.to_dict(), _SCHEMA)


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


# ── Schema conformance ───────────────────────────────────────

_SCHEMA = json.loads(SCHEMA.read_text(encoding="utf-8"))


def _all_kinds_graph():
    """A graph that exercises all node and edge kinds."""
    src_a = "#Module A\n##Section\n    def f(): pass\n"
    mod_a = from_tree(parse(src_a))
    g     = build(mod_a)
    enrich(g, mod_a, extract_symbols)
    mod_b = from_tree(parse("#Module B\n"))
    g.merge(build(mod_b))
    g.add_edge(Edge(source="module/a", target="module/b",
                    kind=EdgeKind.IMPORTS))
    return g


class TestSchemaConformance:
    """Every to_dict() call must produce output that validates against
    the published JSON Schema.  If to_dict() ever emits an unexpected
    field or wrong type, jsonschema.validate() will raise here.
    """

    @pytest.mark.parametrize("label,source", [
        ("empty module",    "#T\n"),
        ("subheading",      "#T\n##Section\n    code\n"),
        ("symbols",         "#T\n    def f(): pass\n    X = 1\n"),
        ("named property",  "#T\n~property p\n    def _(x): pass\n"),
        ("all node kinds",
         "#T\n##Sub\n    def f(): pass\n~property p\n    def _(x): pass\n"),
    ])
    def test_conforms(self, label, source):
        g = _graph(source)
        jsonschema.validate(g.to_dict(), _SCHEMA)   # raises on failure

    def test_conforms_with_imports_edge(self):
        jsonschema.validate(_all_kinds_graph().to_dict(), _SCHEMA)

    def test_conforms_roman_example(self):
        mod = from_tree(parse_file(
            EXAMPLES / "roman/roman/numerals.lob"
        ))
        g = build(mod)
        enrich(g, mod, extract_symbols)
        jsonschema.validate(g.to_dict(), _SCHEMA)

    def test_additionalproperties_rejected(self):
        """Verify the schema actually enforces additionalProperties: false."""
        bad = {
            "nodes": [{"address": "t", "label": "T",
                        "kind": "MODULE", "extra": "oops"}],
            "edges": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, _SCHEMA)

    def test_unknown_kind_rejected(self):
        bad = {
            "nodes": [{"address": "t", "label": "T", "kind": "UNKNOWN"}],
            "edges": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, _SCHEMA)

    def test_missing_required_field_rejected(self):
        bad = {
            "nodes": [{"address": "t", "label": "T"}],  # kind missing
            "edges": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, _SCHEMA)


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
