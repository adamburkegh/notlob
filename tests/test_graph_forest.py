"""The name-graph is the parse tree: every element of a module is a node.

Each file is one tree, joined by `CONTAINS`: a module holds its sections,
paragraphs, code blocks, bullet lists, claims, tests and appendices, each
at the first and last line it occupies, in the order it is written. Text
is held on the leaves.

The oracle below walks the model itself, independently of `build`, so
these tests are the check that nothing was lost: what the model says a
module holds equals what the graph holds.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from notlob import (
    AddressCollisionError, EdgeKind, NodeKind, build, build_package, enrich,
    from_tree, module_address, parse, parse_file,
)
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import extract_symbols, kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit
from notlob.model import (
    AppendixSection, BulletBlock, Claim, CodeBlock, NamedTest, ProseBlock,
    Subheading, TestGroup, TestsSection,
)

EXAMPLES = Path(__file__).parent.parent / "examples"


# ── The oracle: the model, walked independently ──────────────

def _claim_kind(claim: Claim) -> str:
    word = claim.sigil.split()[0]
    if word == "~example":
        return "EXAMPLE"
    return "RUN" if word == "~run" else "PROPERTY"


def _body(items: list) -> list:
    """The elements of a body: (kind, first line, last line, children)."""
    out = []
    for item in items:
        if isinstance(item, ProseBlock):
            out.append(("PROSE", item.start_line, item.end_line, []))
        elif isinstance(item, CodeBlock):
            out.append(("CODE", item.start_line, item.end_line, []))
        elif isinstance(item, BulletBlock):
            out.append(("BULLETS", item.start_line, item.end_line, []))
        elif isinstance(item, Claim):
            out.append((_claim_kind(item), item.start_line,
                        item.end_line, []))
        elif isinstance(item, Subheading):
            out.append(("SUBHEADING", item.start_line, item.end_line,
                        _body(item.body)))
    return out


def _assertions(items: list, offsets: dict) -> list:
    """The elements of #Tests or of a group. A run of bare assertion
    lines is consecutive bare lines (blank ones too) and spans its first
    to its last non-blank line; a run of only blank lines is nothing."""
    out = []
    i = 0
    while i < len(items):
        item = items[i]
        if isinstance(item, str):
            j = i
            while j < len(items) and isinstance(items[j], str):
                j += 1
            lit = [k for k in range(i, j) if items[k].strip()]
            if lit:
                out.append(("TEST", offsets[lit[0]], offsets[lit[-1]], []))
            i = j
            continue
        if isinstance(item, ProseBlock):
            out.append(("PROSE", item.start_line, item.end_line, []))
        elif isinstance(item, TestGroup):
            out.append(("TEST_GROUP", item.start_line, item.end_line,
                        _assertions(item.items, item.line_offsets or {})))
        elif isinstance(item, NamedTest):
            out.append(("TEST", item.start_line, item.end_line, []))
        i += 1
    return out


def expected(module) -> tuple:
    children = _body(module.body)
    post_text = module.post_text
    if post_text is not None:
        held = []
        for section in post_text.sections:
            if isinstance(section, AppendixSection):
                held.append(("APPENDIX", section.start_line,
                             section.end_line, _body(section.body)))
            elif isinstance(section, TestsSection):
                held.append(("TESTS", section.start_line, section.end_line,
                             _assertions(section.items,
                                         section.line_offsets or {})))
        children.append(("POST_TEXT", post_text.start_line,
                         post_text.end_line, held))
    return ("MODULE", module.start_line, module.end_line, children)


def actual(graph, address: str) -> tuple:
    node = graph.node(address)
    return (node.kind.name, node.start_line, node.end_line,
            [actual(graph, child.address)
             for child in graph.children(address)])


# ── Sources covering every place an element can be written ───

def _block(tag: str) -> str:
    return (
        f"Prose of the {tag}, with #Ref{tag} in it.\n"
        "A second line of the paragraph.\n\n"
        "* first point\n* second point\n\n"
        f"    def fn_{tag}():\n        return 1\n\n"
        "Prose between the code and the claims.\n\n"
        f"~example\n    fn_{tag}() == 1\n\n\n"
        f"~property named_{tag}\n"
        "    @given(n=st.integers())\n    def _(n):\n        pass\n\n"
        "~property\n    @given(n=st.integers())\n"
        "    def _(n):\n        pass\n\n"
        "~run\n    main()\n\n"
        "~run on-load\n    boot()\n\n"
        "~run on-invocation\n    go()\n\n"
    )


_TESTS = (
    "#Tests\n\n"
    "    top == 1\n"
    "    top == 2\n\n"
    "Commentary on the tests.\n\n"
    "##g\n"
    "    a == 1\n\n"
    "    b == 2\n\n"
    "Commentary on the group.\n\n"
    "~test nm\n"
    "    c == 3\n\n"
    "    d == 4\n\n"
    "##h\n"
    "    e == 5\n\n"
)

_SOURCES = {
    "body": "#Mod\n\nIntro.\n\n" + _block("body"),
    "subheading": "#Mod\n\nIntro.\n\n##Sub\n\n" + _block("sub"),
    "appendix": ("#Mod\n\nIntro.\n\n---\n\n#Appendix Notes\n\n"
                 + _block("appendix")),
    "appendix subheading": (
        "#Mod\n\nIntro.\n\n---\n\n#Appendix Notes\n\n##AppSub\n\n"
        + _block("appsub")),
    "tests": "#Mod\n\nIntro.\n\n---\n\n" + _TESTS,
    "empty sections": ("#Mod\n\n##Empty\n\n---\n\n#Tests\n\n"
                       "#Appendix\n\n#References\n"),
    "everything": (
        "#Mod\n\nIntro.\n\n" + _block("body") + "##Sub\n\n" + _block("sub")
        + "---\n\n" + _TESTS + "#Appendix Notes\n\n" + _block("appendix")
        + "##AppSub\n\n" + _block("appsub")
        + "#Appendix Second\n\nMore.\n\n"
        + "#References\n    import json\n"),
}


class TestTheGraphIsTheModel:
    @pytest.mark.parametrize("place", sorted(_SOURCES))
    def test_every_place_an_element_can_be_written(self, place):
        module = from_tree(parse(_SOURCES[place]))
        graph = build(module)
        assert actual(graph, module_address(module.title)) == expected(module)

    @pytest.mark.parametrize(
        "path", sorted(EXAMPLES.rglob("*.lob")),
        ids=lambda p: p.relative_to(EXAMPLES).as_posix())
    def test_every_example_file(self, path):
        module = from_tree(parse_file(path))
        graph = build(module)
        assert actual(graph, module_address(module.title)) == expected(module)

    def test_text_is_on_the_leaves_and_only_there(self):
        graph = build(from_tree(parse(_SOURCES["everything"])))
        holders = (NodeKind.MODULE, NodeKind.SUBHEADING, NodeKind.POST_TEXT,
                   NodeKind.APPENDIX, NodeKind.TESTS, NodeKind.TEST_GROUP)
        for node in graph.nodes():
            if node.kind in holders:
                assert node.text is None, node
        leaves = (NodeKind.PROSE, NodeKind.CODE, NodeKind.BULLETS)
        for node in graph.nodes():
            if node.kind in leaves:
                assert node.text, node

    def test_a_prose_leaf_holds_its_references(self):
        graph = build(from_tree(parse("#M\n\nSee #Foo and ##Bar.\n")))
        (leaf,) = graph.nodes(kind=NodeKind.PROSE)
        assert leaf.text == "See #Foo and ##Bar."
        assert [(r.label, r.sub, r.start_line) for r in leaf.refs] == [
            ("Foo", False, 3), ("Bar", True, 3)]

    def test_leaf_addresses_count_per_parent_and_kind(self):
        graph = build(from_tree(parse(
            "#M\n\nOne.\n\n    code a\n\nTwo.\n\n* b\n\n    code b\n\n"
            "##S\n\nThree.\n")))
        assert [n.address for n in graph.nodes()
                if n.kind in (NodeKind.PROSE, NodeKind.CODE,
                              NodeKind.BULLETS)] == [
            "m#prose#1", "m#code#1", "m#prose#2", "m#bullets#1",
            "m#code#2", "m#S#prose#1"]

    def test_appendices_are_numbered_in_order(self):
        graph = build(from_tree(parse(
            "#M\n\n---\n\n#Appendix One\n\nA.\n\n#Appendix Two\n\nB.\n")))
        apps = list(graph.nodes(kind=NodeKind.APPENDIX))
        assert [(a.address, a.label) for a in apps] == [
            ("m#appendix#1", "Appendix One"),
            ("m#appendix#2", "Appendix Two")]

    def test_the_tests_section_and_what_it_holds(self):
        graph = build(from_tree(parse(_SOURCES["tests"])))
        assert graph.node("mod#Tests").kind == NodeKind.TESTS
        assert [c.address for c in graph.children("mod#Tests")] == [
            "mod#Tests#test#1", "mod#Tests#prose#1",
            "mod#Tests#g", "mod#Tests#h"]
        assert [c.address for c in graph.children("mod#Tests#g")] == [
            "mod#Tests#g#test#1", "mod#Tests#g#prose#1",
            "mod#Tests#g#nm"]
        assert graph.node("mod#Tests#test#1").text == (
            "    top == 1\n    top == 2")

    def test_files_are_relative_to_the_project_root(self):
        module = from_tree(parse("#M\n\nText.\n"))
        graph = build(module, "pkg/m.lob")
        assert {n.file for n in graph.nodes()} == {"pkg/m.lob"}
        assert {n.file for n in build(module).nodes()} == {None}


# ── The claim kinds ──────────────────────────────────────────

class TestClaimKinds:
    SRC = (
        "#M\n\n~run\n    a()\n\n~run on-load\n    b()\n\n"
        "~run on-invocation\n    c()\n\n~property\n"
        "    @given(n=st.integers())\n    def _(n):\n        pass\n\n"
        "~example\n    a() == 1\n"
    )

    def test_every_run_is_a_run(self):
        module = from_tree(parse(self.SRC))
        graph = build(module)
        enrich(graph, module, extract_symbols)
        assert [(c.address, c.kind) for c in graph.claims("m")] == [
            ("m#run#1", NodeKind.RUN),
            ("m#run#2", NodeKind.RUN),
            ("m#run#3", NodeKind.RUN),
            ("m#property#1", NodeKind.PROPERTY),
            ("m#example#1", NodeKind.EXAMPLE),
        ]

    def test_a_run_records_its_mode(self):
        graph = build(from_tree(parse(self.SRC)))
        assert [(n.address, n.mode) for n in graph.nodes(NodeKind.RUN)] == [
            ("m#run#1", "on-invocation"),
            ("m#run#2", "on-load"),
            ("m#run#3", "on-invocation"),
        ]

    def test_only_a_run_has_a_mode(self):
        graph = build(from_tree(parse(self.SRC)))
        assert {n.mode for n in graph.nodes() if n.kind != NodeKind.RUN} == {
            None}

    def test_the_mode_is_not_part_of_what_makes_two_nodes_the_same(self):
        graph = build(from_tree(parse(self.SRC)))
        first, second = list(graph.nodes(NodeKind.RUN))[:2]
        assert first.mode != second.mode
        assert type(first)(first.address, first.label, first.kind) == first

    def test_claims_are_made_without_a_binding(self):
        graph = build(from_tree(parse(self.SRC)))
        assert len(graph.claims("m")) == 5

    def test_a_named_property_takes_its_name_but_counts(self):
        graph = build(from_tree(parse(
            "#M\n\n~property p\n    def _(): pass\n\n"
            "~property\n    def _(): pass\n")))
        assert [c.address for c in graph.claims("m")] == [
            "m#p", "m#property#2"]


# ── A name defined twice in one scope ────────────────────────

class TestRedefinition:
    """The last definition wins: one node, held by the leaf it is
    written in."""

    SRC = (
        "#M\n\n    def f():\n        return 1\n\n"
        "##S\n\n    def f():\n        return 2\n"
    )

    def _enriched(self, source):
        module = from_tree(parse(source))
        graph = build(module)
        enrich(graph, module, extract_symbols)
        return graph

    def test_one_node_holds_the_last_definition(self):
        graph = self._enriched(self.SRC)
        symbols = [n for n in graph.nodes(NodeKind.SYMBOL)]
        assert [n.address for n in symbols] == ["m#f"]
        assert "return 2" in graph.text("m#f")

    def test_only_the_last_definitions_leaf_contains_it(self):
        graph = self._enriched(self.SRC)
        holders = [e.source for e in graph.edges(EdgeKind.CONTAINS)
                   if e.target == "m#f"]
        assert holders == ["m#S#code#1"]
        assert graph.parent_of("m#f").address == "m#S#code#1"
        assert [n.address for n in graph.children("m#code#1")] == []

    def test_in_one_code_block_too(self):
        graph = self._enriched(
            "#M\n\n    def f():\n        return 1\n\n"
            "    def f():\n        return 2\n")
        holders = [e.source for e in graph.edges(EdgeKind.CONTAINS)
                   if e.target == "m#f"]
        assert holders == ["m#code#1"]
        assert "return 2" in graph.text("m#f")


# ── A document name restated in its scope ────────────────────

class TestDocumentNames:
    """A name written in a document (a heading, a `~property` or a `~test`
    name) is unique in its scope, as a name shared by two kinds already
    is: the second is an error, not a replacement of the first."""

    @pytest.mark.parametrize("source,address", [
        ("#M\n\n##Notes\n\nOne.\n\n##Notes\n\nTwo.\n", "m#Notes"),
        ("#M\n\n##Notes\n\nOne.\n\n---\n\n#Appendix\n\n##Notes\n\nTwo.\n",
         "m#Notes"),
        ("#M\n\n~property p\n    def _(): pass\n\n"
         "~property p\n    def _(): pass\n", "m#p"),
        ("#M\n\n##S\n\n~property p\n    def _(): pass\n\n"
         "~property p\n    def _(): pass\n", "m#p"),
        ("#M\n\n##A\n\n~property p\n    def _(): pass\n\n##B\n\n"
         "~property p\n    def _(): pass\n", "m#p"),
        ("#M\n\n---\n\n#Tests\n\n##g\n    a == 1\n\n##g\n    b == 2\n",
         "m#Tests#g"),
        ("#M\n\n---\n\n#Tests\n\n##g\n~test nm\n    a == 1\n\n"
         "~test nm\n    b == 2\n", "m#Tests#g#nm"),
    ], ids=["two headings", "body and appendix heading", "two properties",
            "two properties in a subheading",
            "two properties in two subheadings", "two groups",
            "two tests"])
    def test_a_second_is_an_error(self, source, address):
        with pytest.raises(AddressCollisionError) as raised:
            build(from_tree(parse(source)))
        error = raised.value
        assert error.address == address
        assert error.existing_kind == error.new_kind
        assert error.existing_line < error.new_line
        assert "namespace" in str(error)

    @pytest.mark.parametrize("source", [
        "#M\n\n---\n\n#Tests\n\n##g\n~test nm\n    a == 1\n\n"
        "##h\n~test nm\n    b == 2\n",
        "#M\n\n~property\n    def _(): pass\n\n~property\n"
        "    def _(): pass\n",
        "#M\n\n---\n\n#Appendix One\n\nA.\n\n#Appendix Two\n\nB.\n",
    ], ids=["test in two groups", "two unnamed properties",
            "two appendices"])
    def test_the_same_name_in_different_scopes_is_fine(self, source):
        build(from_tree(parse(source)))

    def test_symbols_still_keep_the_last_definition(self):
        module = from_tree(parse(
            "#M\n\n    def f():\n        return 1\n\n"
            "    def f():\n        return 2\n"))
        graph = build(module)
        enrich(graph, module, extract_symbols)
        assert "return 2" in graph.text("m#f")

    def test_it_can_be_collected_instead_of_raised(self):
        collected = []
        graph = build(from_tree(parse(
            "#M\n\n##Notes\n\nOne.\n\n##Notes\n\nTwo.\n")),
            collisions=collected)
        assert [e.address for e in collected] == ["m#Notes"]
        assert graph.node("m#Notes") is not None


# ── The post-text ────────────────────────────────────────────

class TestPostText:
    SRC = (
        "#M\n\nIntro.\n\n---\n\n#Tests\n\n##g\n    a == 1\n\n"
        "~test nm\n    b == 2\n\n#Appendix Notes\n\nNotes.\n\n"
        "##AppSub\n\nMore.\n\n#Appendix Second\n\nLast.\n"
    )

    def _graph(self, source=None):
        return build(from_tree(parse(source or self.SRC)), "m.lob")

    def test_the_sections_after_the_separator_hang_from_it(self):
        graph = self._graph()
        node = graph.node("m#post-text")
        assert (node.kind, node.label) == (NodeKind.POST_TEXT, "post-text")
        assert (node.start_line, node.end_line, node.file) == (
            5, 25, "m.lob")
        assert [(c.address, c.kind) for c in graph.children("m#post-text")] == [
            ("m#Tests", NodeKind.TESTS),
            ("m#appendix#1", NodeKind.APPENDIX),
            ("m#appendix#2", NodeKind.APPENDIX),
        ]
        assert graph.parent_of("m#post-text").address == "m"

    def test_what_hangs_from_it_keeps_its_address(self):
        graph = self._graph()
        for address in ("m#Tests", "m#Tests#g", "m#Tests#g#test#1",
                        "m#Tests#g#nm", "m#appendix#1",
                        "m#appendix#1#prose#1", "m#AppSub",
                        "m#AppSub#prose#1", "m#appendix#2#prose#1"):
            assert graph.node(address) is not None, address
        assert graph.parent_of("m#Tests").address == "m#post-text"
        assert graph.parent_of("m#appendix#1").address == "m#post-text"
        assert graph.module_of("m#Tests#g#nm") == "m"

    def test_the_module_holds_the_post_text_after_its_body(self):
        graph = self._graph()
        assert [c.address for c in graph.children("m")] == [
            "m#prose#1", "m#post-text"]

    def test_a_module_without_a_separator_has_none(self):
        graph = self._graph("#M\n\nIntro.\n")
        assert graph.node("m#post-text") is None
        assert list(graph.nodes(kind=NodeKind.POST_TEXT)) == []

    def test_a_bare_separator_is_a_post_text_with_nothing_in_it(self):
        graph = self._graph("#M\n\nIntro.\n\n---\n")
        node = graph.node("m#post-text")
        assert (node.start_line, node.end_line) == (5, 5)
        assert list(graph.children("m#post-text")) == []

    def test_binding_and_references_are_not_nodes(self):
        graph = self._graph(
            "#M\n\n---\n\n#Binding\n    ~language python\n\n"
            "#References\n    import json\n")
        assert list(graph.children("m#post-text")) == []

    def test_the_sections_of_a_module_still_include_the_appendices(self):
        graph = self._graph(
            "#M\n\n##S\n\nx\n\n---\n\n#Appendix\n\n##AppSub\n\ny\n")
        assert [s.address for s in graph.sections("m")] == [
            "m#S", "m#appendix#1", "m#AppSub"]


# ── The kinds in #Tests ──────────────────────────────────────

class TestTestKinds:
    def _graph(self, tests):
        return build(from_tree(parse("#M\n\n---\n\n#Tests\n" + tests)))

    def test_a_group_a_named_test_and_an_anonymous_one(self):
        graph = self._graph(
            "    top == 1\n\n##g\n    a == 1\n\n~test nm\n    b == 2\n")
        kinds = {n.address: n.kind for n in graph.children("m#Tests")}
        assert kinds == {
            "m#Tests#test#1": NodeKind.TEST,
            "m#Tests#g": NodeKind.TEST_GROUP,
        }
        assert {n.address: n.kind for n in graph.children("m#Tests#g")} == {
            "m#Tests#g#test#1": NodeKind.TEST,
            "m#Tests#g#nm": NodeKind.TEST,
        }

    def test_no_node_is_a_group_unless_it_holds_the_tests_of_a_group(self):
        graph = self._graph("##g\n    a == 1\n\n##h\n    b == 2\n")
        assert [n.address for n in graph.nodes(kind=NodeKind.TEST_GROUP)] == [
            "m#Tests#g", "m#Tests#h"]

    @pytest.mark.parametrize("tests", [
        "##g\n~test test#1\n    b == 2\n",
        "##g\n    a == 1\n\n~test test#2\n    b == 2\n",
    ], ids=["alone", "after a run"])
    def test_a_test_named_like_an_ordinal_is_still_a_named_test(self, tests):
        from notlob.graph import claims_to_run
        graph = self._graph(tests)
        name = "test#1" if "test#1" in tests else "test#2"
        named = graph.node(f"m#Tests#g#{name}")
        assert named.kind == NodeKind.TEST and named.name == name
        reported = [(c.address, c.name) for c in claims_to_run(graph, "m")]
        assert reported == (
            [("m#Tests#g#test#1", "test#1")] if name == "test#1" else
            [("m#Tests#g#test#1", None), ("m#Tests#g#test#2", "test#2")])


# ── The forest ───────────────────────────────────────────────

_PROJECTS = [
    ("roman", python_kit), ("retail", python_kit),
    ("gutenberg", python_kit), ("haskell-roman", haskell_kit),
    ("ts-media", typescript_kit),
]
_TREE_EDGES = {EdgeKind.CONTAINS, EdgeKind.USES, EdgeKind.REFERENCES,
               EdgeKind.IMPORTS, EdgeKind.USES_EXTERNAL}


class TestForest:
    @pytest.fixture(params=_PROJECTS, ids=lambda p: p[0])
    def project(self, request):
        name, kit = request.param
        graph = build_package(
            EXAMPLES / name, kit.extract_symbols,
            call_extractor=kit.extract_calls)
        parents: dict[str, list[str]] = {}
        for edge in graph.edges(EdgeKind.CONTAINS):
            parents.setdefault(edge.target, []).append(edge.source)
        return graph, parents

    def test_each_node_but_a_module_has_exactly_one_parent(self, project):
        graph, parents = project
        for node in graph.nodes():
            if node.kind in (NodeKind.MODULE, NodeKind.EXTERNAL):
                assert node.address not in parents, node
            else:
                assert len(parents.get(node.address, [])) == 1, node

    def test_every_node_reaches_its_module_without_a_cycle(self, project):
        graph, parents = project
        for node in graph.nodes():
            if node.kind == NodeKind.EXTERNAL:
                continue
            seen = set()
            current = node
            while current.kind != NodeKind.MODULE:
                assert current.address not in seen, node
                seen.add(current.address)
                (parent,) = parents[current.address]
                current = graph.node(parent)
            assert graph.module_of(node.address) == current.address

    def test_contains_is_the_only_edge_that_makes_a_tree(self, project):
        graph, _parents = project
        assert {e.kind for e in graph.edges()} <= _TREE_EDGES

    def test_external_nodes_have_no_contains_edge(self, project):
        graph, _parents = project
        externals = {n.address for n in graph.nodes(kind=NodeKind.EXTERNAL)}
        for edge in graph.edges(EdgeKind.CONTAINS):
            assert edge.source not in externals
            assert edge.target not in externals

    def test_every_node_from_a_file_names_its_file(self, project):
        graph, _parents = project
        for node in graph.nodes():
            if node.kind == NodeKind.EXTERNAL:
                assert node.file is None
            else:
                assert node.file and node.file.endswith(".lob"), node


# ── What a node is, is its kind ──────────────────────────────

#: The one helper that says how an anonymous test is told from a named
#: one.
_MAY_TELL_BY_SHAPE = {"_is_anonymous_test"}
_STRING_TESTS = {"fullmatch", "match", "search", "endswith", "startswith",
                 "split", "rsplit", "partition", "rpartition"}


class TestNothingTellsKindsApartByAddressOrLabel:
    """A node's kind says what it is. Code that matches a pattern against
    an address or a label to find out breaks when a name happens to look
    like the pattern, so none outside the one helper may."""

    def _functions(self):
        import ast
        import notlob.graph as graph_module
        tree = ast.parse(Path(graph_module.__file__).read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield node

    def _reads_an_address_or_label(self, call) -> bool:
        import ast
        return any(
            isinstance(part, ast.Attribute)
            and part.attr in ("address", "label")
            for part in ast.walk(call))

    def _offences(self) -> list[str]:
        import ast
        found = []
        for function in self._functions():
            if function.name in _MAY_TELL_BY_SHAPE:
                continue
            for call in ast.walk(function):
                if (isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Attribute)
                        and call.func.attr in _STRING_TESTS
                        and self._reads_an_address_or_label(call)):
                    found.append(f"{function.name}: line {call.lineno}")
        return found

    def test_graph_py_does_not_decide_a_kind_from_an_address_or_label(self):
        assert self._offences() == []

    def test_the_guard_sees_what_it_guards_against(self):
        """The guard finds the 2c helper's pattern match, so it would have
        caught it."""
        import ast
        source = (
            "def is_run(node):\n"
            "    return re.fullmatch(r'test#\\d+', node.label)\n")
        (function,) = ast.parse(source).body
        (call,) = [c for c in ast.walk(function) if isinstance(c, ast.Call)]
        assert call.func.attr in _STRING_TESTS
        assert self._reads_an_address_or_label(call)
