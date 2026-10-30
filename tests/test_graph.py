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
    module_address, named_address,
)
from notlob.graph import Node, add_uses_edges, add_cites_edges, enrich
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
        assert named_address(
            "roman/numerals", "Decoding"
        ) == "roman/numerals#Decoding"

    def test_label_preserved_as_is(self):
        # Label is NOT lowercased or slash-separated — it is a
        # human-readable fragment, not a path segment.
        assert named_address(
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

    def test_a_plain_module_holds_only_its_paragraph(self):
        g = graph_of("#T\nSome prose.\n")
        assert [n.kind for n in g.children("t")] == [NodeKind.PROSE]
        assert g.sections("t") == []

    def test_children_ordered(self):
        g = graph_of("#T\n##A\n    a\n##B\n    b\n##C\n    c\n")
        labels = [n.label for n in g.children("t")]
        assert labels == ["A", "B", "C"]


# ── Graph queries ────────────────────────────────────────────

class TestQueries:
    def test_len_counts_nodes(self):
        g = graph_of("#T\n##A\n    a\n##B\n    b\n")
        # the module, 2 subheadings and the code block in each
        assert len(g) == 5

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
    return [e for e in g.to_dict("index")["edges"] if e["kind"] == "USES"]


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


class TestUsesLines:
    """A USES edge is at the line of the use in the file, whatever holds
    the code. Read here from the graph, as it is before printing."""

    def _uses(self, source: str) -> dict[tuple[str, str], int]:
        g = _enriched(source)
        add_uses_edges(g, extract_calls)
        return {(e.source, e.target): e.start_line
                for e in g.edges(EdgeKind.USES)}

    def test_a_call_on_the_second_line_of_a_symbol(self):
        src = ("#M\n\n    def g():\n        return 1\n\n"
               "    def f():\n        x = 1\n        return g()\n")
        assert self._uses(src) == {("m#f", "m#g"): 8}

    def test_a_claim_with_blank_lines_before_its_first_assertion(self):
        src = ("#M\n\n    def f():\n        return 1\n\n"
               "~example\n\n\n    f() == 1\n")
        assert self._uses(src) == {("m#example#1", "m#f"): 9}

    def test_a_claim_on_the_line_after_its_sigil(self):
        src = "#M\n\n    def f():\n        return 1\n\n~example\n    f() == 1\n"
        assert self._uses(src) == {("m#example#1", "m#f"): 7}

    def test_a_property(self):
        src = ("#M\n\n    def f():\n        return 1\n\n~property\n"
               "    @given()\n    def _(n):\n        assert f() == n\n")
        assert self._uses(src) == {("m#property#1", "m#f"): 9}

    _TESTS = ("#M\n\n    def f():\n        return 1\n\n---\n\n#Tests\n")

    def test_a_named_test_of_several_indented_lines(self):
        src = self._TESTS + "\n##g\n~test nm\n    x = 1\n    f() == x\n"
        assert self._uses(src) == {("m#Tests#g#nm", "m#f"): 13}

    def test_a_run_of_assertions_in_a_group(self):
        src = self._TESTS + "\n##g\n    1 == 1\n    f() == 1\n"
        assert self._uses(src) == {("m#Tests#g#test#1", "m#f"): 12}

    def test_a_run_after_commentary(self):
        src = self._TESTS + "\nCommentary.\n\n    f() == 1\n"
        assert self._uses(src) == {("m#Tests#test#1", "m#f"): 12}

    def test_every_run_is_scanned_on_its_own(self):
        src = (self._TESTS
               + "\n##g\n    1 == 1\n\nCommentary.\n\n    f() == 1\n")
        assert self._uses(src) == {("m#Tests#g#test#2", "m#f"): 15}

    def test_a_group_and_the_tests_section_are_not_scanned(self):
        src = self._TESTS + "\n    f() == 1\n\n##g\n    f() == 2\n"
        sources = {s for s, _t in self._uses(src)}
        assert sources == {"m#Tests#test#1", "m#Tests#g#test#1"}


# ── add_cites_edges ──────────────────────────────────────

def _refs_edges(g: NameGraph) -> list[dict]:
    return [e for e in g.to_dict("index")["edges"] if e["kind"] == "CITES"]


def _module_graph(source: str):
    """Build a structural graph AND return both graph and module."""
    module = from_tree(parse(source))
    g = build(module)
    return g, module


class TestAddCitesEdges:
    def test_module_prose_ref_to_subheading(self):
        src = (
            "#M\n"
            "See #Section here.\n"
            "##Section\n"
            "    code\n"
        )
        g, module = _module_graph(src)
        add_cites_edges(g)
        refs = _refs_edges(g)
        assert any(e["source"] == "m#prose#1" and e["target"] == "m#Section"
                   for e in refs)

    def test_the_edge_is_made_from_the_paragraph_that_holds_the_reference(
        self,
    ):
        """The graph holds the edge from the paragraph, and the document
        prints it so from `index` on."""
        g, _module = _module_graph(
            "#M\nSee #Section here.\n##Section\n    code\n")
        add_cites_edges(g)
        edges = [(e.source, e.target, e.start_line)
                 for e in g.edges(EdgeKind.CITES)]
        assert edges == [("m#prose#1", "m#Section", 2)]

    def test_subheading_prose_ref_to_other_subheading(self):
        src = (
            "#M\n"
            "##Alpha\n"
            "See #Beta below.\n"
            "##Beta\n"
            "    code\n"
        )
        g, module = _module_graph(src)
        add_cites_edges(g)
        refs = _refs_edges(g)
        assert any(e["source"] == "m#Alpha#prose#1"
                   and e["target"] == "m#Beta" for e in refs)

    def test_unresolved_ref_emits_no_edge(self):
        src = "#M\nSee #Phantom here.\n"
        g, module = _module_graph(src)
        add_cites_edges(g)
        assert _refs_edges(g) == []

    def test_deduplicates_repeated_ref(self):
        src = (
            "#M\n"
            "See #Section and #Section again.\n"
            "##Section\n"
            "    code\n"
        )
        g, module = _module_graph(src)
        add_cites_edges(g)
        refs = [e for e in _refs_edges(g)
                if e["source"] == "m#prose#1" and e["target"] == "m#Section"]
        assert len(refs) == 1

    def test_ref_edge_carries_start_line(self):
        src = (
            "#M\n"                   # line 1
            "See #Section here.\n"  # line 2
            "##Section\n"
            "    code\n"
        )
        g, module = _module_graph(src)
        add_cites_edges(g)
        refs = [e for e in _refs_edges(g)
                if e["source"] == "m#prose#1" and e["target"] == "m#Section"]
        assert len(refs) == 1
        assert refs[0].get("start_line") == 2

    def test_multiple_modules(self):
        mod_a = from_tree(parse("#A\nSee #B here.\n"))
        mod_b = from_tree(parse("#B\n    code\n"))
        g = NameGraph()
        g.merge(build(mod_a))
        g.merge(build(mod_b))
        g.add_edge(Edge(source="a", target="b", kind=EdgeKind.IMPORTS))
        add_cites_edges(g)
        refs = _refs_edges(g)
        assert any(e["source"] == "a#prose#1" and e["target"] == "b"
                   for e in refs)


# ── Accessors ────────────────────────────────────────────────
#
# What the checks read the graph through. Each answers a question about a
# node without the caller knowing how the graph holds the answer.

class TestModuleOf:
    def test_a_node_belongs_to_its_module(self):
        g = _enriched(
            "#Mod\n    def f(): pass\n\n##Sub\n\n~example\n    f() == 1\n")
        for address in ("mod", "mod#f", "mod#Sub", "mod#Sub#example#1"):
            assert g.module_of(address) == "mod"

    def test_a_nested_module_address(self):
        g = _enriched("#Pricing Discounts\n    def apply(): pass\n")
        assert g.module_of("pricing/discounts") == "pricing/discounts"
        assert g.module_of("pricing/discounts#apply") == "pricing/discounts"

    def test_an_unknown_address_has_no_module(self):
        assert _enriched("#Mod\n").module_of("no/such#thing") is None

    def test_an_external_node_has_no_module(self):
        g = _enriched("#Mod\n")
        g.add_node(Node(address="index.html", label="index.html",
                        kind=NodeKind.EXTERNAL))
        assert g.module_of("index.html") is None


class TestEdgesAccessor:
    EDGES = [
        ("a", "b", EdgeKind.USES),
        ("a", "c", EdgeKind.CONTAINS),
        ("b", "c", EdgeKind.USES),
        ("c", "a", EdgeKind.CITES),
        ("a", "b", EdgeKind.CONTAINS),
    ]

    def _graph(self) -> NameGraph:
        g = NameGraph()
        for address in "abc":
            g.add_node(Node(address=address, label=address,
                            kind=NodeKind.SYMBOL))
        for source, target, kind in self.EDGES:
            g.add_edge(Edge(source, target, kind))
        return g

    def test_every_edge_in_insertion_order(self):
        listed = [(e.source, e.target, e.kind) for e in self._graph().edges()]
        assert listed == self.EDGES

    def test_edges_of_one_kind(self):
        g = self._graph()
        uses = [(e.source, e.target) for e in g.edges(EdgeKind.USES)]
        assert uses == [("a", "b"), ("b", "c")]
        contains = [(e.source, e.target) for e in g.edges(EdgeKind.CONTAINS)]
        assert contains == [("a", "c"), ("a", "b")]

    def test_no_edges_of_a_kind_the_graph_lacks(self):
        assert list(self._graph().edges(EdgeKind.IMPORTS)) == []


class TestSections:
    def test_subheadings_in_document_order(self):
        g = _enriched("#Mod\n\n##Beta\n\nx\n\n##Alpha\n\ny\n")
        sections = g.sections("mod")
        assert [s.label for s in sections] == ["Beta", "Alpha"]
        assert all(s.kind == NodeKind.SUBHEADING for s in sections)

    def test_a_module_without_sections(self):
        assert _enriched("#Mod\n\nText.\n").sections("mod") == []

    def test_a_section_has_no_sections_of_its_own(self):
        assert _enriched("#Mod\n\n##A\n\nx\n").sections("mod#A") == []

    def test_an_unknown_address(self):
        assert _enriched("#Mod\n").sections("no/such") == []


class TestProse:
    SRC = "#Mod\n\nTop prose.\n\n##Sub\n\nSub prose.\n"

    def test_prose_written_directly_in_a_module(self):
        assert _enriched(self.SRC).prose("mod") == "Top prose."

    def test_a_modules_prose_leaves_out_its_sections(self):
        assert "Sub prose." not in _enriched(self.SRC).prose("mod")

    def test_prose_written_in_a_section(self):
        assert _enriched(self.SRC).prose("mod#Sub") == "Sub prose."

    def test_paragraphs_and_bullet_items_a_blank_line_apart(self):
        g = _enriched("#Mod\n\nIntro.\n\n* one\n* two\n\nOutro.\n")
        assert g.prose("mod") == "Intro.\n\none\ntwo\n\nOutro."

    def test_references_keep_their_sigils(self):
        g = _enriched("#Mod\n\nSee #Foo and ##Bar.\n\n##Bar\n\nx\n")
        assert g.prose("mod") == "See #Foo and ##Bar."

    def test_no_prose_is_the_empty_string(self):
        g = _enriched("#Mod\n    def f(): pass\n")
        assert g.prose("mod") == ""
        assert g.prose("mod#f") == ""
        assert g.prose("no/such") == ""


class TestBulletListCount:
    def test_two_lists_in_a_section(self):
        g = _enriched("#Mod\n\n##S\n\n* a\n\n* b\n")
        assert g.bullet_list_count("mod#S") == 2

    def test_one_list_in_a_module(self):
        g = _enriched("#Mod\n\n* a\n* b\n")
        assert g.bullet_list_count("mod") == 1

    def test_a_modules_count_leaves_out_its_sections(self):
        g = _enriched("#Mod\n\n##S\n\n* a\n")
        assert g.bullet_list_count("mod") == 0

    def test_no_lists_is_zero(self):
        g = _enriched("#Mod\n\nText.\n")
        assert g.bullet_list_count("mod") == 0
        assert g.bullet_list_count("no/such") == 0


class TestClaims:
    SRC = (
        "#Mod\n    def f(): pass\n\n"
        "~example\n    f() == 1\n\n"
        "~property p\n    def _(): pass\n\n"
        "~run\n    f()\n\n"
        "~example\n    f() == 2\n\n"
        "##Sub\n\n~example\n    f() == 3\n"
    )

    def test_claims_in_document_order(self):
        claims = _enriched(self.SRC).claims("mod")
        assert [(c.address, c.kind) for c in claims] == [
            ("mod#example#1", NodeKind.EXAMPLE),
            ("mod#p", NodeKind.PROPERTY),
            ("mod#run#1", NodeKind.RUN),
            ("mod#example#2", NodeKind.EXAMPLE),
        ]

    def test_a_sections_claims_are_its_own(self):
        g = _enriched(self.SRC)
        assert [c.address for c in g.claims("mod#Sub")] == [
            "mod#Sub#example#1"]

    def test_symbols_and_tests_are_not_claims(self):
        g = _enriched(
            "#Mod\n    def f(): pass\n\n~example\n    f() == 1\n\n"
            "---\n\n#Tests\n\n##g\n    f() == 1\n")
        assert [c.address for c in g.claims("mod")] == ["mod#example#1"]

    def test_no_claims_is_an_empty_list(self):
        g = _enriched("#Mod\n\nText.\n")
        assert g.claims("mod") == []
        assert g.claims("no/such") == []
