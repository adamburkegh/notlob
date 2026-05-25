"""Tests for symbol enrichment in the name-graph.

enrich() adds SYMBOL nodes and DEFINES edges to a structural graph
using a language-specific extractor.  Covers symbol address
computation, module- vs subheading-scoped DEFINES edges, address
collision detection, and resolve() with symbol context.
"""

from pathlib import Path

import pytest

from notlob import (
    parse, parse_file, from_tree, build, enrich,
    NameGraph, NodeKind, EdgeKind,
    symbol_address,
)
from notlob.bindings.python import extract_symbols


def enriched(source: str) -> NameGraph:
    module = from_tree(parse(source))
    graph  = build(module)
    enrich(graph, module, extract_symbols)
    return graph


EXAMPLES = Path(__file__).parent.parent / "examples"


# ── Symbol address computation ───────────────────────────────

class TestSymbolAddress:
    def test_basic(self):
        assert (
            symbol_address("roman/numerals", "to_roman")
            == "roman/numerals#to_roman"
        )

    def test_constant(self):
        assert (
            symbol_address("roman/numerals", "NUMERALS")
            == "roman/numerals#NUMERALS"
        )


# ── Symbol nodes ─────────────────────────────────────────────

class TestSymbolNodes:
    def test_function_at_module_level(self):
        g = enriched("#T\n    def f(): pass\n")
        node = g.node("t#f")
        assert node is not None
        assert node.kind == NodeKind.SYMBOL
        assert node.label == "f"

    def test_constant_at_module_level(self):
        g = enriched("#T\n    X = 1\n")
        assert g.node("t#X") is not None

    def test_function_inside_subheading(self):
        src = "#T\n##Section\n    def f(): pass\n"
        g = enriched(src)
        node = g.node("t#f")
        assert node is not None
        assert node.kind == NodeKind.SYMBOL

    def test_symbol_address_is_module_scoped(self):
        # Even when defined inside a subheading, the symbol's
        # address is module-scoped, not subheading-scoped.
        src = "#T\n##Section\n    def f(): pass\n"
        g = enriched(src)
        assert g.node("t#f") is not None
        assert g.node("t#Section#f") is None

    def test_no_symbols_from_prose(self):
        g = enriched("#T\nJust prose.\n")
        syms = list(g.nodes(NodeKind.SYMBOL))
        assert syms == []

    def test_no_symbols_from_claims(self):
        g = enriched("#T\n~example\n    f() == 1\n")
        syms = list(g.nodes(NodeKind.SYMBOL))
        assert syms == []


# ── DEFINES edges ────────────────────────────────────────────

class TestDefinesEdges:
    def test_module_defines_toplevel_symbol(self):
        g = enriched("#T\n    def f(): pass\n")
        defined = list(g.children("t", EdgeKind.DEFINES))
        assert any(n.label == "f" for n in defined)

    def test_subheading_defines_symbol(self):
        src = "#T\n##Section\n    def f(): pass\n"
        g = enriched(src)
        defined = list(g.children("t#Section", EdgeKind.DEFINES))
        assert any(n.label == "f" for n in defined)

    def test_module_does_not_define_subheading_symbol(self):
        # Symbol defined inside a subheading has DEFINES edge
        # from the subheading, not from the module.
        src = "#T\n##Section\n    def f(): pass\n"
        g = enriched(src)
        module_defined = list(g.children("t", EdgeKind.DEFINES))
        assert not any(n.label == "f" for n in module_defined)

    def test_multiple_symbols_from_one_block(self):
        src = (
            "#T\n"
            "    def f(): pass\n"
            "    def g(): pass\n"
            "    X = 1\n"
        )
        g = enriched(src)
        defined = {n.label for n in g.children("t", EdgeKind.DEFINES)}
        assert defined == {"f", "g", "X"}


# ── Address collision ────────────────────────────────────────

class TestAddressCollision:
    def test_symbol_subheading_collision_raises(self):
        # A symbol named "Section" in a module that also has
        # ##Section is a namespace collision — an error.
        src = (
            "#T\n"
            "##Section\n"
            "    code\n"
            "    Section = 1\n"
        )
        with pytest.raises(ValueError, match="collision"):
            enriched(src)


# ── resolve() with symbols ───────────────────────────────────

class TestResolveWithSymbols:
    def test_resolves_symbol_in_context(self):
        g = enriched("#T\n    def f(): pass\n")
        node = g.resolve("f", context="t")
        assert node is not None
        assert node.kind == NodeKind.SYMBOL

    def test_symbol_takes_priority_in_resolution(self):
        # If both a symbol and a subheading existed with the same
        # label (normally a collision error), symbol wins.  Here we
        # test the priority via a symbol that doesn't collide.
        src = "#T\n##Alpha\n    code\n    def beta(): pass\n"
        g = enriched(src)
        # "beta" is a symbol, not a subheading
        node = g.resolve("beta", context="t")
        assert node is not None
        assert node.kind == NodeKind.SYMBOL

    def test_subheading_still_resolves(self):
        src = "#T\n##Alpha\n    def beta(): pass\n"
        g = enriched(src)
        node = g.resolve("Alpha", context="t")
        assert node is not None
        assert node.kind == NodeKind.SUBHEADING

    def test_unknown_label_returns_none(self):
        g = enriched("#T\n    def f(): pass\n")
        assert g.resolve("unknown", context="t") is None


# ── Integration: example files ───────────────────────────────

class TestExampleFiles:
    def _enrich(self, path):
        module = from_tree(parse_file(path))
        graph  = build(module)
        enrich(graph, module, extract_symbols)
        return graph

    def test_roman_numerals_symbols(self):
        g = self._enrich(EXAMPLES / "roman/roman/numerals.lob")
        assert g.node("roman/numerals#NUMERALS") is not None
        assert g.node("roman/numerals#to_roman") is not None
        assert g.node("roman/numerals#from_roman") is not None

    def test_to_roman_defined_by_module(self):
        # NUMERALS and to_roman are at module body level.
        g = self._enrich(EXAMPLES / "roman/roman/numerals.lob")
        defined = {
            n.label for n in
            g.children("roman/numerals", EdgeKind.DEFINES)
        }
        assert "NUMERALS" in defined
        assert "to_roman" in defined

    def test_from_roman_defined_by_subheading(self):
        # from_roman is defined inside ##Decoding.
        g = self._enrich(EXAMPLES / "roman/roman/numerals.lob")
        defined = {
            n.label for n in
            g.children("roman/numerals#Decoding", EdgeKind.DEFINES)
        }
        assert "from_roman" in defined

    def test_pricing_discounts_symbols(self):
        g = self._enrich(EXAMPLES / "retail/pricing/discounts.lob")
        assert g.node("pricing/discounts#apply_discount") is not None

    def test_resolve_symbol_in_example(self):
        g = self._enrich(EXAMPLES / "roman/roman/numerals.lob")
        node = g.resolve("to_roman", context="roman/numerals")
        assert node is not None
        assert node.kind == NodeKind.SYMBOL
