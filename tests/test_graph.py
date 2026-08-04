"""Tests for the structural name-graph.

Covers address computation, node and edge construction, graph
queries, merge, and integration against the example files.
"""

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from notlob import (
    parse, parse_file, from_tree, build,
    NameGraph, NodeKind, Edge, EdgeKind,
    module_address, subheading_address,
)
from notlob.graph import add_uses_edges, enrich
from notlob.bindings.python.symbols import extract_calls, extract_symbols


def graph_of(source: str) -> NameGraph:
    return build(from_tree(parse(source)))


EXAMPLES = Path(__file__).parent.parent / "examples"


# ── Address computation ──────────────────────────────────────

class TestModuleAddress:
    def test_single_word(self):
        assert module_address("Roman") == "roman"

    def test_two_words(self):
        assert module_address("Roman Numerals") == "roman/numerals"

    def test_multi_word(self):
        assert module_address("Pricing Discounts") == "pricing/discounts"

    def test_lowercase(self):
        assert module_address("HTTP Client") == "http/client"

    @given(st.text(
        alphabet=st.sampled_from("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz "),
        min_size=1, max_size=40,
    ))
    def test_always_lowercase(self, title):
        assert module_address(title) == module_address(title).lower()

    @given(st.text(
        alphabet=st.sampled_from("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz "),
        min_size=1, max_size=40,
    ))
    def test_no_spaces_in_address(self, title):
        assert " " not in module_address(title)

    @given(st.text(
        alphabet=st.sampled_from("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz "),
        min_size=1, max_size=40,
    ))
    def test_deterministic(self, title):
        assert module_address(title) == module_address(title)

    @given(st.text(
        alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz/"),
        min_size=1, max_size=40,
    ))
    def test_stable_on_own_output(self, addr):
        assert module_address(addr) == addr


class TestSubheadingAddress:
    def test_basic(self):
        assert subheading_address(
            "roman/numerals", "Decoding"
        ) == "roman/numerals#Decoding"

    def test_label_preserved_as_is(self):
        # Label is NOT lowercased or slash-separated — it is a
        # human-readable fragment, not a path segment.
        assert subheading_address(
            "pricing/discounts", "Stacking Discounts"
        ) == "pricing/discounts#Stacking Discounts"


# ── Node construction ────────────────────────────────────────

class TestNodes:
    def test_module_node_present(self):
        g = graph_of("#Roman Numerals\n")
        node = g.node("roman/numerals")
        assert node is not None
        assert node.kind == NodeKind.MODULE
        assert node.label == "Roman Numerals"

    def test_module_address_from_title(self):
        g = graph_of("#Pricing Discounts\n")
        assert g.node("pricing/discounts") is not None

    def test_subheading_node_present(self):
        g = graph_of("#T\n##Decoding\n    code\n")
        node = g.node("t#Decoding")
        assert node is not None
        assert node.kind == NodeKind.SUBHEADING
        assert node.label == "Decoding"

    def test_no_subheadings_in_empty_body(self):
        g = graph_of("#T\n")
        subs = list(g.nodes(NodeKind.SUBHEADING))
        assert subs == []

    def test_multiple_subheadings(self):
        g = graph_of("#T\n##A\n    a\n##B\n    b\n")
        assert g.node("t#A") is not None
        assert g.node("t#B") is not None


# ── Edges ────────────────────────────────────────────────────

class TestEdges:
    def test_contains_edge_module_to_subheading(self):
        g = graph_of("#T\n##Sub\n    code\n")
        children = list(g.children("t"))
        assert len(children) == 1
        assert children[0].address == "t#Sub"

    def test_no_children_for_plain_module(self):
        g = graph_of("#T\nSome prose.\n")
        assert list(g.children("t")) == []

    def test_children_ordered(self):
        g = graph_of("#T\n##A\n    a\n##B\n    b\n##C\n    c\n")
        labels = [n.label for n in g.children("t")]
        assert labels == ["A", "B", "C"]


# ── Graph queries ────────────────────────────────────────────

class TestQueries:
    def test_len_counts_nodes(self):
        g = graph_of("#T\n##A\n    a\n##B\n    b\n")
        assert len(g) == 3   # module + 2 subheadings

    def test_nodes_all(self):
        g = graph_of("#T\n##A\n    a\n")
        kinds = {n.kind for n in g.nodes()}
        assert NodeKind.MODULE in kinds
        assert NodeKind.SUBHEADING in kinds

    def test_nodes_filtered_by_kind(self):
        g = graph_of("#T\n##A\n    a\n##B\n    b\n")
        mods = list(g.nodes(NodeKind.MODULE))
        subs = list(g.nodes(NodeKind.SUBHEADING))
        assert len(mods) == 1
        assert len(subs) == 2


# ── Resolution ───────────────────────────────────────────────

class TestResolve:
    def test_resolve_subheading_in_context(self):
        g = graph_of("#Roman Numerals\n##Decoding\n    code\n")
        node = g.resolve("Decoding", context="roman/numerals")
        assert node is not None
        assert node.address == "roman/numerals#Decoding"

    def test_resolve_module_by_label(self):
        g = graph_of("#Roman Numerals\n")
        node = g.resolve("Roman Numerals")
        assert node is not None
        assert node.kind == NodeKind.MODULE

    def test_resolve_unknown_returns_none(self):
        g = graph_of("#T\n")
        assert g.resolve("Unknown", context="t") is None

    def test_resolve_imported_module_in_context(self):
        # Step 3: resolve a module that the context module imports.
        # Requires an explicit IMPORTS edge (package graph layer).
        g = graph_of("#My Module\n##Sub\n    code\n")
        g2 = graph_of("#Other\n")
        g.merge(g2)
        g.add_edge(Edge(
            source="my/module",
            target="other",
            kind=EdgeKind.IMPORTS,
        ))
        node = g.resolve("Other", context="my/module")
        assert node is not None
        assert node.kind == NodeKind.MODULE

    def test_resolve_unimported_module_not_visible_in_context(self):
        # A module present in the graph but not declared as an import
        # is invisible to resolve() when a context is given.
        g = graph_of("#My Module\n")
        g2 = graph_of("#Other\n")
        g.merge(g2)
        # No IMPORTS edge — "Other" should not be found
        assert g.resolve("Other", context="my/module") is None

    def test_resolve_module_without_context_full_scan(self):
        # Without context, resolve() scans all MODULE nodes.
        g = graph_of("#My Module\n")
        g2 = graph_of("#Other\n")
        g.merge(g2)
        node = g.resolve("Other")
        assert node is not None
        assert node.kind == NodeKind.MODULE


# ── Merge ────────────────────────────────────────────────────

class TestMerge:
    def test_merge_combines_nodes(self):
        g1 = graph_of("#Roman Numerals\n##Decoding\n    code\n")
        g2 = graph_of("#Pricing Discounts\n##Stacking Discounts\n    c\n")
        g1.merge(g2)
        assert g1.node("roman/numerals") is not None
        assert g1.node("pricing/discounts") is not None
        assert g1.node(
            "pricing/discounts#Stacking Discounts"
        ) is not None

    def test_merge_preserves_edges(self):
        g1 = graph_of("#T\n##A\n    a\n")
        g2 = graph_of("#U\n##B\n    b\n")
        g1.merge(g2)
        assert list(g1.children("t"))
        assert list(g1.children("u"))


# ── Integration: example files ───────────────────────────────

class TestExampleFiles:
    def test_roman_numerals_nodes(self):
        g = build(from_tree(parse_file(
            EXAMPLES / "roman/roman/numerals.lob"
        )))
        assert g.node("roman/numerals") is not None
        assert g.node("roman/numerals#Decoding") is not None
        assert g.node("roman/numerals#Round-Trip") is not None

    def test_roman_numerals_children(self):
        g = build(from_tree(parse_file(
            EXAMPLES / "roman/roman/numerals.lob"
        )))
        labels = [n.label for n in g.children("roman/numerals")]
        assert "Decoding" in labels
        assert "Round-Trip" in labels

    def test_pricing_discounts(self):
        g = build(from_tree(parse_file(
            EXAMPLES / "retail/pricing/discounts.lob"
        )))
        assert g.node("pricing/discounts") is not None
        assert g.node(
            "pricing/discounts#Stacking Discounts"
        ) is not None

    def test_binding_lob_is_package_node(self):
        # binding.lob title is the package name, not the file name.
        g = build(from_tree(parse_file(
            EXAMPLES / "retail/binding.lob"
        )))
        assert g.node("pricing") is not None
        assert g.node("pricing").kind == NodeKind.MODULE


# ── add_uses_edges ────────────────────────────────────────────

def _enriched(source: str) -> NameGraph:
    """Build and enrich a single-module graph from lob source."""
    module = from_tree(parse(source))
    g = build(module)
    enrich(g, module, extract_symbols)
    return g


def _uses_edges(g: NameGraph) -> list[dict]:
    return [e for e in g.to_dict()["edges"] if e["kind"] == "USES"]


class TestAddUsesEdges:
    def test_intra_module_uses_edge(self):
        src = (
            "#M\n"
            "    def caller():\n"
            "        return callee()\n"
            "\n"
            "    def callee():\n"
            "        return 1\n"
        )
        g = _enriched(src)
        add_uses_edges(g, extract_calls)
        uses = _uses_edges(g)
        sources = {e["source"] for e in uses}
        targets = {e["target"] for e in uses}
        assert "m#caller" in sources
        assert "m#callee" in targets

    def test_no_edge_for_unresolved_name(self):
        src = "#M\n    def f():\n        return unknown_external()\n"
        g = _enriched(src)
        add_uses_edges(g, extract_calls)
        assert all(e["target"] != "m#unknown_external" for e in _uses_edges(g))

    def test_deduplicates_multiple_calls(self):
        src = (
            "#M\n"
            "    def caller():\n"
            "        return callee() + callee()\n"
            "\n"
            "    def callee():\n"
            "        return 1\n"
        )
        g = _enriched(src)
        add_uses_edges(g, extract_calls)
        uses = [e for e in _uses_edges(g)
                if e["source"] == "m#caller" and e["target"] == "m#callee"]
        assert len(uses) == 1

    def test_no_uses_edges_without_call_extractor(self):
        src = "#M\n    def f():\n        return g()\n    def g():\n        return 1\n"
        g = _enriched(src)
        # add_uses_edges not called — no USES edges
        assert _uses_edges(g) == []

    def test_cross_module_uses_edge(self):
        mod_a = from_tree(parse("#A\n    def caller():\n        return callee()\n"))
        mod_b = from_tree(parse("#B\n    def callee():\n        return 1\n"))
        g = NameGraph()
        for mod in (mod_a, mod_b):
            sub = build(mod)
            enrich(sub, mod, extract_symbols)
            g.merge(sub)
        add_uses_edges(g, extract_calls)
        uses = _uses_edges(g)
        assert any(e["source"] == "a#caller" and e["target"] == "b#callee"
                   for e in uses)

    def test_uses_edge_has_start_line(self):
        # caller starts on line 2 (#M is line 1), callee() call is line 3
        src = (
            "#M\n"
            "    def caller():\n"
            "        return callee()\n"
            "\n"
            "    def callee():\n"
            "        return 1\n"
        )
        g = _enriched(src)
        add_uses_edges(g, extract_calls)
        edge = next(
            e for e in _uses_edges(g)
            if e["source"] == "m#caller" and e["target"] == "m#callee"
        )
        assert "start_line" in edge
        assert edge["start_line"] == 3  # line 2 (caller) + offset 1 (return callee())

    def test_uses_edge_first_call_site(self):
        # callee called on lines 2 and 3 of caller's body — first wins
        src = (
            "#M\n"
            "    def caller():\n"
            "        x = callee()\n"
            "        return callee() + x\n"
            "\n"
            "    def callee():\n"
            "        return 1\n"
        )
        g = _enriched(src)
        add_uses_edges(g, extract_calls)
        edge = next(
            e for e in _uses_edges(g)
            if e["source"] == "m#caller" and e["target"] == "m#callee"
        )
        assert edge["start_line"] == 3  # first call site
