"""Tests for symbol enrichment of ~property claims in the name-graph.

Named ~property claims create NodeKind.PROPERTY nodes in the graph.
Functions defined inside (other than _) are NodeKind.SYMBOL children.
Unnamed ~property claims produce no graph nodes.
"""

from notlob import (
    parse, from_tree, build, enrich,
    NameGraph, NodeKind, EdgeKind,
    property_address,
)
from notlob.bindings.python import extract_symbols


def enriched(source: str) -> NameGraph:
    module = from_tree(parse(source))
    graph  = build(module)
    enrich(graph, module, extract_symbols)
    return graph


# ── property_address helper ───────────────────────────────────

class TestPropertyAddress:
    def test_module_level(self):
        assert (
            property_address("roman/numerals", "commutativity")
            == "roman/numerals#commutativity"
        )

    def test_subheading_level(self):
        assert (
            property_address("roman/numerals#Round-Trip", "identity")
            == "roman/numerals#Round-Trip#identity"
        )


# ── Named property nodes ──────────────────────────────────────

class TestNamedPropertyNodes:
    def test_named_property_creates_node(self):
        g = enriched("#T\n~property myp\n    @given()\n    def _(): pass\n")
        node = g.node("t#myp")
        assert node is not None
        assert node.kind == NodeKind.PROPERTY

    def test_named_property_label(self):
        g = enriched("#T\n~property myp\n    @given()\n    def _(): pass\n")
        assert g.node("t#myp").label == "myp"

    def test_unnamed_property_gets_ordinal_node(self):
        g = enriched("#T\n~property\n    @given()\n    def _(): pass\n")
        props = list(g.nodes(NodeKind.PROPERTY))
        assert len(props) == 1
        assert props[0].address == "t#property#1"

    def test_property_in_subheading(self):
        src = "#T\n##S\n~property myp\n    @given()\n    def _(): pass\n"
        g = enriched(src)
        node = g.node("t#S#myp")
        assert node is not None
        assert node.kind == NodeKind.PROPERTY

    def test_module_level_property_not_under_subheading(self):
        src = (
            "#T\n"
            "~property top\n    @given()\n    def _(): pass\n"
            "##S\n"
            "~property inner\n    @given()\n    def _(): pass\n"
        )
        g = enriched(src)
        assert g.node("t#top")    is not None
        assert g.node("t#S#inner") is not None
        assert g.node("t#inner")   is None
        assert g.node("t#S#top")   is None


# ── DEFINES edges ─────────────────────────────────────────────

class TestDefinesEdges:
    def test_module_defines_named_property(self):
        g = enriched("#T\n~property myp\n    @given()\n    def _(): pass\n")
        defined = {n.label for n in g.children("t", EdgeKind.DEFINES)}
        assert "myp" in defined

    def test_subheading_defines_named_property(self):
        src = "#T\n##S\n~property myp\n    @given()\n    def _(): pass\n"
        g = enriched(src)
        defined = {n.label for n in g.children("t#S", EdgeKind.DEFINES)}
        assert "myp" in defined


# ── Symbols under named properties ────────────────────────────

class TestPropertySymbols:
    def test_named_function_extracted(self):
        src = (
            "#T\n~property myp\n"
            "    @given()\n"
            "    def the_property(): pass\n"
        )
        g = enriched(src)
        node = g.node("t#myp#the_property")
        assert node is not None
        assert node.kind == NodeKind.SYMBOL

    def test_underscore_not_extracted(self):
        src = "#T\n~property myp\n    @given()\n    def _(): pass\n"
        g = enriched(src)
        assert g.node("t#myp#_") is None

    def test_property_defines_symbol(self):
        src = (
            "#T\n~property myp\n"
            "    @given()\n"
            "    def prop(): pass\n"
        )
        g = enriched(src)
        defined = {n.label for n in g.children("t#myp", EdgeKind.DEFINES)}
        assert "prop" in defined

    def test_no_symbols_for_unnamed_property(self):
        src = "#T\n~property\n    @given()\n    def named(): pass\n"
        g = enriched(src)
        # Named function, but property is unnamed so no property node
        # and no symbols under a property node
        assert g.node("t#named") is None

    def test_underscore_in_unnamed_property_not_extracted(self):
        src = "#T\n~property\n    @given()\n    def _(): pass\n"
        g = enriched(src)
        syms = list(g.nodes(NodeKind.SYMBOL))
        assert syms == []


# ── nodes() filtering ─────────────────────────────────────────

class TestNodeFiltering:
    def test_nodes_property_kind(self):
        src = (
            "#T\n"
            "~property p1\n    @given()\n    def _(): pass\n"
            "~property p2\n    @given()\n    def _(): pass\n"
        )
        g = enriched(src)
        props = {n.label for n in g.nodes(NodeKind.PROPERTY)}
        assert props == {"p1", "p2"}

    def test_code_block_symbols_unaffected(self):
        src = (
            "#T\n"
            "    def f(): pass\n"
            "~property myp\n"
            "    @given()\n"
            "    def prop(): pass\n"
        )
        g = enriched(src)
        # f is a module-level symbol; prop is under the property
        assert g.node("t#f") is not None
        assert g.node("t#f").kind == NodeKind.SYMBOL
        assert g.node("t#myp#prop") is not None
