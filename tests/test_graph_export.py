"""Tests for NameGraph serialisation and new query methods.

Covers to_dict(), to_json(), search(), and parents(). The levels of the
document are in test_graph_levels.py; here are its shape and schema, and
what a section's prose is.
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
from notlob.graph import LEVELS


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


# ── The text of the document ──────────────────────────────────

class TestText:
    """What `--content` used to put on a node is the `text` of the leaves
    at `full`, each once."""

    def _nodes(self, source: str) -> dict:
        doc = _graph(source).to_dict(level="full")
        return {n["address"]: n for n in doc["nodes"]}

    def test_there_is_no_content_at_any_level(self):
        g = _graph("#T\n    def f(): pass\n")
        for level in LEVELS:
            assert all("content" not in n
                       for n in g.to_dict(level=level)["nodes"])

    def test_text_only_at_full(self):
        g = _graph("#T\n\nSome text.\n")
        assert all("text" not in n
                   for n in g.to_dict(level="index")["nodes"])
        assert self._nodes("#T\n\nSome text.\n")["t#prose#1"]["text"] == (
            "Some text.")

    def test_paragraphs_are_separate_nodes_not_run_together(self):
        nodes = self._nodes("#T\n\nFirst paragraph.\n\nSecond paragraph.\n")
        assert nodes["t#prose#1"]["text"] == "First paragraph."
        assert nodes["t#prose#2"]["text"] == "Second paragraph."

    def test_a_paragraph_keeps_its_references_with_their_sigils(self):
        nodes = self._nodes("#T\n\nSee ##Section for details.\n\n##Section\n")
        assert nodes["t#prose#1"]["text"] == "See ##Section for details."

    def test_a_bullet_list_holds_its_items_one_to_a_line(self):
        nodes = self._nodes("#T\n\nIntro.\n\n* one\n* two\n")
        assert nodes["t#bullets#1"]["text"] == "one\ntwo"

    def test_code_is_in_its_block_and_a_symbol_has_none(self):
        nodes = self._nodes("#T\n    def f(): pass\n    def g(): pass\n")
        assert "def f" in nodes["t#code#1"]["text"]
        assert "text" not in nodes["t#f"]
        assert "text" not in nodes["t#g"]

    def test_a_property_holds_its_code(self):
        nodes = self._nodes(
            "#T\n~property commutativity\n    def _(x): pass\n")
        assert "def _" in nodes["t#commutativity"]["text"]

    def test_a_node_with_nothing_of_its_own_has_no_text(self):
        nodes = self._nodes("#T\n##Only Section\n    code\n")
        assert "text" not in nodes["t"]
        assert "text" not in nodes["t#Only Section"]


# ── to_dict ───────────────────────────────────────────────────

class TestToDict:
    def test_the_keys_of_the_document(self):
        d = _graph("#T\n").to_dict()
        assert set(d.keys()) == {"version", "level", "nodes", "edges"}

    def test_node_shape(self):
        d = _graph("#Roman Numerals\n").to_dict()
        node = next(n for n in d["nodes"] if n["kind"] == "MODULE")
        assert {"address", "label", "kind"} <= set(node.keys())
        assert node["address"] == "roman/numerals"
        assert node["label"]   == "Roman Numerals"
        assert node["kind"]    == "MODULE"
        assert node["start_line"] == 1
        assert "end_line" not in node

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
        g2  = _graph("#B\n")
        g.merge(g2)
        g.add_edge(Edge(source="a", target="b", kind=EdgeKind.IMPORTS))
        d     = g.to_dict("index")
        kinds = {e["kind"] for e in d["edges"]}
        assert "CONTAINS" in kinds
        assert "IMPORTS"  in kinds
        assert "DEFINES" not in kinds

    def test_round_trips_via_json(self):
        g = _graph("#Roman Numerals\n##Decoding\n    def f(): pass\n")
        d = json.loads(g.to_json())
        assert isinstance(d["nodes"], list)
        assert isinstance(d["edges"], list)
        assert all(
            {"address", "kind"} <= set(n.keys())
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
        kinds = data["definitions"]["GraphNode"]["properties"]["kind"][
            "enum"]
        assert set(kinds) == {k.name for k in NodeKind}

    def test_schema_edge_kinds_are_the_enum_but_defines(self):
        data  = json.loads(SCHEMA.read_text(encoding="utf-8"))
        kinds = data["definitions"]["GraphEdge"]["properties"]["kind"][
            "enum"]
        assert set(kinds) == {k.name for k in EdgeKind} - {"DEFINES"}

    def test_schema_levels_match_the_levels(self):
        data = json.loads(SCHEMA.read_text(encoding="utf-8"))
        assert tuple(data["properties"]["level"]["enum"]) == LEVELS


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

    @pytest.mark.parametrize("level", LEVELS)
    @pytest.mark.parametrize("label,source", [
        ("empty module",    "#T\n"),
        ("subheading",      "#T\n##Section\n    code\n"),
        ("symbols",         "#T\n    def f(): pass\n    X = 1\n"),
        ("named property",  "#T\n~property p\n    def _(x): pass\n"),
        ("all node kinds",
         "#T\n##Sub\n    def f(): pass\n~property p\n    def _(x): pass\n"),
        ("prose and code",   "#T\n\nIntro.\n\n    def f(): pass\n"),
        ("bullet list",      "#T\n\nIntro.\n\n* one\n* two\n\n    x = 1\n"),
        ("bullets in a subheading",
         "#T\n##S\n\nText.\n\n* a\n* b\n\n    y = 2\n"),
    ])
    def test_conforms(self, label, source, level):
        g = _graph(source)
        jsonschema.validate(g.to_dict(level=level), _SCHEMA)

    def test_conforms_with_imports_edge(self):
        for level in LEVELS:
            jsonschema.validate(
                _all_kinds_graph().to_dict(level=level), _SCHEMA)

    def test_conforms_roman_example(self):
        mod = from_tree(parse_file(
            EXAMPLES / "roman/roman/numerals.lob"
        ))
        g = build(mod)
        enrich(g, mod, extract_symbols)
        for level in LEVELS:
            jsonschema.validate(g.to_dict(level=level), _SCHEMA)

    def test_additionalproperties_rejected(self):
        """Verify the schema actually enforces additionalProperties: false."""
        bad = {
            "version": 2, "level": "outline",
            "nodes": [{"address": "t", "label": "T",
                        "kind": "MODULE", "extra": "oops"}],
            "edges": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, _SCHEMA)

    def test_unknown_kind_rejected(self):
        bad = {
            "version": 2, "level": "outline",
            "nodes": [{"address": "t", "label": "T", "kind": "UNKNOWN"}],
            "edges": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, _SCHEMA)

    def test_missing_required_field_rejected(self):
        bad = {
            "version": 2, "level": "outline",
            "nodes": [{"address": "t", "label": "T"}],  # kind missing
            "edges": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, _SCHEMA)

    def test_a_document_without_a_version_is_rejected(self):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"nodes": [], "edges": []}, _SCHEMA)


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
