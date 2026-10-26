"""Tests for symbol enrichment in the name-graph.

enrich() adds SYMBOL nodes to a structural graph, each contained by the
code block it is written in, using a language-specific extractor.  Covers
symbol address computation, containment, address collision detection, and
resolve() with symbol context.
"""

from pathlib import Path

import pytest

from notlob import (
    parse, parse_file, from_tree, build, enrich,
    NameGraph, NodeKind,
    named_address,
)
from notlob.bindings import SymbolInfo
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import extract_symbols, kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit


def enriched(source: str) -> NameGraph:
    module = from_tree(parse(source))
    graph  = build(module)
    enrich(graph, module, extract_symbols)
    return graph


EXAMPLES = Path(__file__).parent.parent / "examples"


def written_in(graph: NameGraph, section: str) -> set[str]:
    """The labels of the symbols written in the code blocks of the module
    or section at *section*: each is contained by its code block."""
    return {
        symbol.label
        for code in graph.children(section) if code.kind == NodeKind.CODE
        for symbol in graph.children(code.address)
        if symbol.kind == NodeKind.SYMBOL
    }


# ── Symbol address computation ───────────────────────────────

class TestSymbolAddress:
    def test_basic(self):
        assert (
            named_address("roman/numerals", "to_roman")
            == "roman/numerals#to_roman"
        )

    def test_constant(self):
        assert (
            named_address("roman/numerals", "NUMERALS")
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


# ── Containment ──────────────────────────────────────────────

class TestSymbolContainment:
    def test_module_code_block_contains_toplevel_symbol(self):
        g = enriched("#T\n    def f(): pass\n")
        assert "f" in written_in(g, "t")

    def test_subheading_code_block_contains_symbol(self):
        src = "#T\n##Section\n    def f(): pass\n"
        g = enriched(src)
        assert "f" in written_in(g, "t#Section")

    def test_module_does_not_contain_subheading_symbol(self):
        # A symbol written inside a subheading is contained by that
        # subheading's code block, not by the module's.
        src = "#T\n##Section\n    def f(): pass\n"
        g = enriched(src)
        assert "f" not in written_in(g, "t")

    def test_multiple_symbols_from_one_block(self):
        src = (
            "#T\n"
            "    def f(): pass\n"
            "    def g(): pass\n"
            "    X = 1\n"
        )
        g = enriched(src)
        assert written_in(g, "t") == {"f", "g", "X"}
        assert [c.address for c in g.children("t")] == ["t#code#1"]


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


# ── Symbol lines ─────────────────────────────────────────────

def without_lines(lines):
    """A binding that does not say which lines a symbol occupies."""
    return [SymbolInfo(name=s.name, source=s.source)
            for s in extract_symbols(lines)]


class TestSymbolLines:
    def test_a_symbol_has_its_own_lines(self):
        src = "#T\n\nIntro.\n\n    X = 1\n\n    def f():\n        return 1\n"
        g = enriched(src)
        x, f = g.node("t#X"), g.node("t#f")
        assert (x.start_line, x.end_line) == (5, 5)
        assert (f.start_line, f.end_line) == (7, 8)

    def test_a_function_in_a_property_has_its_own_lines(self):
        src = ("#T\n\n~property p\n    @given(n=st.integers())\n"
               "    def prop(n):\n        assert n == n\n")
        node = enriched(src).node("t#p#prop")
        assert (node.start_line, node.end_line) == (5, 6)

    def test_a_symbol_in_a_subheading(self):
        g = enriched("#T\n\n##S\n\n    def f():\n        return 1\n")
        node = g.node("t#f")
        assert (node.start_line, node.end_line) == (5, 6)

    def test_a_symbol_holds_no_text_of_its_own(self):
        g = enriched("#T\n    def f(): pass\n")
        assert g.node("t#f").text is None

    def test_its_text_is_read_from_the_leaf_by_its_lines(self):
        src = "#T\n\n    X = 1\n\n    def f():\n        return 1\n"
        g = enriched(src)
        assert g.text("t#X") == "X = 1"
        assert g.text("t#f") == "def f():\n    return 1"

    def test_the_text_of_a_function_in_a_property(self):
        src = ("#T\n\n~property p\n    @given()\n"
               "    def prop(n):\n        assert n == n\n")
        assert enriched(src).text("t#p#prop") == (
            "def prop(n):\n    assert n == n")

    def test_the_text_of_a_leaf_is_its_own(self):
        g = enriched("#T\n\nSome prose.\n\n    X = 1\n")
        assert g.text("t#prose#1") == "Some prose."
        assert g.text("t#code#1") == "X = 1"

    def test_there_is_no_text_for_anything_else(self):
        g = enriched("#T\n\n##S\n\n    X = 1\n")
        assert g.text("t") is None
        assert g.text("t#S") is None
        assert g.text("no/such") is None


class TestSymbolsInAnAppendix:
    SRC = (
        "#T\n\n---\n\n#Appendix Notes\n\n"
        "    def helper():\n        return 1\n\n"
        "~property p\n    @given()\n    def prop():\n        pass\n\n"
        "##AppSub\n\n    def deeper():\n        return 2\n"
    )

    def test_symbols_written_in_an_appendix_are_in_the_graph(self):
        g = enriched(self.SRC)
        assert g.node("t#helper").kind == NodeKind.SYMBOL
        assert g.parent_of("t#helper").address == "t#appendix#1#code#1"
        assert g.module_of("t#helper") == "t"

    def test_and_in_an_appendix_subheading(self):
        g = enriched(self.SRC)
        assert g.parent_of("t#deeper").address == "t#AppSub#code#1"

    def test_with_their_own_lines_and_text(self):
        g = enriched(self.SRC)
        helper = g.node("t#helper")
        assert (helper.start_line, helper.end_line) == (7, 8)
        assert g.text("t#helper") == "def helper():\n    return 1"

    def test_a_property_in_an_appendix_has_its_functions(self):
        g = enriched(self.SRC)
        prop = g.node("t#p#prop")
        assert prop.kind == NodeKind.SYMBOL
        assert g.parent_of(prop.address).address == "t#p"

    def test_the_outline_shows_them(self):
        shown = {n["address"] for n in enriched(self.SRC).to_dict()["nodes"]}
        assert {"t#helper", "t#deeper", "t#p#prop"} <= shown


class TestEnrichReadsTheGraph:
    def test_the_module_is_for_its_address_only(self):
        from notlob.model import Module
        graph = build(from_tree(parse("#T\n\n    def f(): pass\n")))
        enrich(graph, Module(title="T", body=[]), extract_symbols)
        assert graph.node("t#f").kind == NodeKind.SYMBOL


class TestABindingWithoutLines:
    """A binding that leaves the lines unset keeps the symbol's source on
    its node, and the block's first line, as before."""

    def _graph(self):
        module = from_tree(parse("#T\n\nIntro.\n\n    def f():\n"
                                 "        return 1\n"))
        graph = build(module)
        enrich(graph, module, without_lines)
        return graph

    def test_the_node_keeps_the_source_and_the_blocks_line(self):
        node = self._graph().node("t#f")
        assert node.text == "def f():\n    return 1"
        assert node.start_line == 5

    def test_the_text_is_the_nodes_own(self):
        assert self._graph().text("t#f") == "def f():\n    return 1"


# Every code block of every example, with the binding its project uses.

_KITS = {
    "roman": python_kit, "retail": python_kit, "gutenberg": python_kit,
    "haskell-roman": haskell_kit, "ts-media": typescript_kit,
}


def _example_graphs(extractor_of):
    """(path, graph) for each .lob file of the examples, enriched with
    the extractor *extractor_of* makes of the project's binding."""
    for project, kit in _KITS.items():
        for path in sorted((EXAMPLES / project).rglob("*.lob")):
            module = from_tree(parse_file(path))
            graph = build(module)
            enrich(graph, module, extractor_of(kit))
            yield path, graph


class TestSymbolsInEveryExample:
    def test_the_examples_have_symbols(self):
        graphs = _example_graphs(lambda k: k.extract_symbols)
        count = sum(len(list(g.nodes(NodeKind.SYMBOL))) for _p, g in graphs)
        assert count > 20

    def test_no_symbol_holds_a_copy_of_its_text(self):
        for path, graph in _example_graphs(lambda k: k.extract_symbols):
            for node in graph.nodes(NodeKind.SYMBOL):
                assert node.text is None, (path.name, node)

    def test_the_lines_lie_within_the_leaf_that_holds_the_symbol(self):
        for path, graph in _example_graphs(lambda k: k.extract_symbols):
            for node in graph.nodes(NodeKind.SYMBOL):
                holder = graph.parent_of(node.address)
                assert node.start_line <= node.end_line, (path.name, node)
                assert holder.start_line <= node.start_line, (
                    path.name, node)
                assert node.end_line <= holder.end_line, (path.name, node)

    def test_the_text_by_its_lines_is_the_bindings_source(self):
        def source_only(kit):
            return lambda lines: [
                SymbolInfo(name=s.name, source=s.source)
                for s in kit.extract_symbols(lines)]

        by_lines = _example_graphs(lambda k: k.extract_symbols)
        by_source = _example_graphs(source_only)
        for (path, graph), (_path, copy) in zip(by_lines, by_source):
            for node in graph.nodes(NodeKind.SYMBOL):
                assert graph.text(node.address) == copy.node(
                    node.address).text, (path.name, node)


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

    def test_to_roman_written_in_the_module(self):
        # NUMERALS and to_roman are at module body level.
        g = self._enrich(EXAMPLES / "roman/roman/numerals.lob")
        written = written_in(g, "roman/numerals")
        assert "NUMERALS" in written
        assert "to_roman" in written

    def test_from_roman_written_in_the_subheading(self):
        # from_roman is written inside ##Decoding.
        g = self._enrich(EXAMPLES / "roman/roman/numerals.lob")
        assert "from_roman" in written_in(g, "roman/numerals#Decoding")

    def test_pricing_discounts_symbols(self):
        g = self._enrich(EXAMPLES / "retail/pricing/discounts.lob")
        assert g.node("pricing/discounts#apply_discount") is not None

    def test_resolve_symbol_in_example(self):
        g = self._enrich(EXAMPLES / "roman/roman/numerals.lob")
        node = g.resolve("to_roman", context="roman/numerals")
        assert node is not None
        assert node.kind == NodeKind.SYMBOL
