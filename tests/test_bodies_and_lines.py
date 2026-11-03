"""A written node holds its own lines, and a reference every line it is on.

A node's ``body`` is the lines of its span that no node under it holds,
as they are in the file, less blank lines at either end; a ``SYMBOL`` and
an ``EXTERNAL`` are derived and have none. An ``Edge`` has ``lines``, a
tuple of every line a reference is written on, in order and each once: one
edge for each source, target and kind.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

import notlob.commands as commands
from notlob import (
    EdgeKind, NodeKind, build, build_package, from_tree, parse,
)
from notlob.bindings import ClaimResult, Status
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit
from notlob.graph import add_bodies, add_cites_edges, add_uses_edges, enrich
from notlob.model import AppendixSection

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"

_PROJECTS = [
    ("roman", python_kit), ("retail", python_kit),
    ("gutenberg", python_kit), ("haskell-roman", haskell_kit),
    ("ts-media", typescript_kit),
]

K = NodeKind


@pytest.fixture(scope="module", params=_PROJECTS, ids=lambda p: p[0])
def example(request):
    name, kit = request.param
    root = EXAMPLES / name
    graph = build_package(
        root, kit.extract_symbols, call_extractor=kit.extract_calls,
        split_imports=kit.split_imports)
    return root, graph


@pytest.fixture(scope="module")
def roman():
    root = EXAMPLES / "roman"
    graph = build_package(
        root, python_kit.extract_symbols,
        call_extractor=python_kit.extract_calls,
        split_imports=python_kit.split_imports)
    return root, graph


def _graph(source: str, kit=python_kit):
    """A module built from *source* with its symbols, uses and bodies."""
    module = from_tree(parse(source), source=source)
    graph = build(module)
    enrich(graph, module, kit.extract_symbols, kit.split_imports)
    add_cites_edges(graph)
    add_uses_edges(graph, kit.extract_calls)
    add_bodies(graph, module)
    return graph


def _only(graph, kind: K):
    (node,) = graph.nodes(kind)
    return node


# ── Each line of a file is in one body ───────────────────────

class TestTheBodiesAreTheFile:
    def test_each_line_that_is_not_blank_is_in_one_body(self, example):
        root, graph = example
        for module in graph.nodes(K.MODULE):
            placed: dict[int, str] = {}
            for node in graph.nodes():
                if node.file != module.file or node.body is None:
                    continue
                at = node.start_line
                for number, text in enumerate(node.body.split("\n"), at):
                    assert number not in placed, (node.address, number)
                    placed[number] = text
            written = (root / module.file).read_text(encoding="utf-8")
            for number, text in enumerate(written.split("\n"), 1):
                held = placed.pop(number, None)
                if held is None:
                    assert not text.strip(), (
                        f"{module.file}:{number} is in no body")
                else:
                    assert held == text, f"{module.file}:{number}"
            assert not placed, f"a body runs past the end of {module.file}"

    def test_a_derived_node_has_none_and_a_written_one_has_one(
        self, example,
    ):
        _root, graph = example
        for node in graph.nodes():
            derived = node.kind in (K.SYMBOL, K.EXTERNAL)
            assert (node.body is None) == derived, node.address

    def test_a_body_does_not_start_or_end_on_a_blank_line(self, example):
        _root, graph = example
        for node in graph.nodes():
            if node.body is not None:
                assert node.body.split("\n")[0].strip(), node.address
                assert node.body.split("\n")[-1].strip(), node.address


class TestRomansBodies:
    def test_a_heading_is_its_line(self, roman):
        _root, graph = roman
        (heading,) = [n for n in graph.nodes(K.SUBHEADING)
                      if n.name == "Decoding"]
        assert heading.body == "##Decoding"

    def test_the_post_text_is_its_separator(self, roman):
        _root, graph = roman
        post = _only_in(graph, K.POST_TEXT, "roman/numerals")
        assert post.body == "---"

    def test_a_module_is_its_title_line(self, roman):
        _root, graph = roman
        assert graph.node("roman/numerals").body == "#Roman Numerals"

    def test_a_claim_is_its_sigil_line_and_the_lines_under_it(self, roman):
        _root, graph = roman
        example = _first_in(graph, K.EXAMPLE, "roman/numerals")
        assert example.body == (
            "~example\n"
            "    to_roman(4)    == 'IV'\n"
            "    to_roman(9)    == 'IX'\n"
            "    to_roman(2024) == 'MMXXIV'")

    def test_a_test_group_is_its_heading_line(self, roman):
        _root, graph = roman
        (group,) = [n for n in graph.nodes(K.TEST_GROUP)
                    if n.name == "encoding"]
        assert group.body == "##encoding"

    def test_the_decoding_section_nodes_with_their_bodies(self, roman):
        _root, graph = roman
        section = graph.node("roman/numerals#Decoding")
        held = [(n.kind.name, n.body) for n in graph.children(
            section.address)]
        assert [kind for kind, _ in held] == [
            "PROSE", "CODE", "EXAMPLE"]
        assert held[0][1].startswith("Decoding is the inverse of encoding.")
        assert held[1][1].startswith("    def from_roman(s: str) -> int:")
        assert held[2][1].startswith("~example\n    from_roman('IV')")


def _first_in(graph, kind: K, module: str):
    return next(n for n in graph.nodes(kind)
                if graph.module_of(n.address) == module)


def _only_in(graph, kind: K, module: str):
    (node,) = [n for n in graph.nodes(kind)
               if graph.module_of(n.address) == module]
    return node


class TestBodiesFromTheFile:
    def test_a_blank_line_inside_a_code_block_stays(self):
        graph = _graph(
            "#M\n\n    def f():\n        a = 1\n\n        return a\n")
        code = _only(graph, K.CODE)
        assert code.body == (
            "    def f():\n        a = 1\n\n        return a")
        assert graph.node("m#f").body is None

    def test_indent_is_as_written(self):
        graph = _graph("#M\n\n~example\n        1 == 1\n    2 == 2\n")
        assert _only(graph, K.EXAMPLE).body == (
            "~example\n        1 == 1\n    2 == 2")

    def test_a_blank_line_between_two_nodes_is_in_neither(self):
        graph = _graph("#M\n\nOne.\n\n\n\nTwo.\n")
        assert [n.body for n in graph.nodes(K.PROSE)] == ["One.", "Two."]

    def test_a_module_built_without_its_source_has_no_bodies(self):
        module = from_tree(parse("#M\n\nOne.\n"))
        graph = build(module)
        add_bodies(graph, module)
        assert all(n.body is None for n in graph.nodes())

    def test_a_run_of_test_lines_is_its_lines(self):
        graph = _graph(
            "#M\n\n---\n\n#Tests\n\n##g\n    1 == 1\n\n    2 == 2\n")
        assert _only(graph, K.TEST_LINES).body == (
            "    1 == 1\n\n    2 == 2")

    def test_an_import_is_its_lines_and_the_section_the_rest(self):
        graph = _graph(
            "#M\n\n---\n\n#References\n    import os\n    import sys\n")
        refs = _only(graph, K.REFERENCES)
        assert refs.body == "#References"
        assert [n.body for n in graph.nodes(K.IMPORT)] == [
            "    import os", "    import sys"]

    def test_an_appendix_is_its_heading(self):
        graph = _graph("#M\n\n---\n\n#Appendix Notes\n\nA note.\n")
        assert _only(graph, K.APPENDIX).body == "#Appendix Notes"


# ── An edge has every line a reference is on ─────────────────

def _edge(graph, kind: EdgeKind, source: str, target: str):
    (edge,) = [e for e in graph.edges(kind)
               if (e.source, e.target) == (source, target)]
    return edge


class TestUsesLines:
    def test_python_gives_every_line(self):
        graph = _graph(
            "#M\n\n    def g():\n        return 1\n\n    def f():\n"
            "        a = g()\n        return g() + g()\n")
        assert _edge(graph, EdgeKind.USES, "m#f", "m#g").lines == (7, 8)

    def test_haskell_gives_every_line(self):
        graph = _graph(
            "#M\n\n    g x = x + 1\n\n    f x = g x\n        + g (g x)\n",
            haskell_kit)
        assert _edge(graph, EdgeKind.USES, "m#f", "m#g").lines == (5, 6)

    def test_typescript_gives_every_line(self):
        graph = _graph(
            "#M\n\n    function g(n: number) { return n; }\n\n"
            "    function f(n: number) {\n      const a = g(n);\n"
            "      return g(g(n));\n    }\n", typescript_kit)
        assert _edge(graph, EdgeKind.USES, "m#f", "m#g").lines == (6, 7)

    def test_a_name_twice_on_one_line_is_that_line_once(self):
        graph = _graph(
            "#M\n\n    def g():\n        return 1\n\n    def f():\n"
            "        return g() + g()\n")
        assert _edge(graph, EdgeKind.USES, "m#f", "m#g").lines == (7,)

    def test_a_claim_uses_a_symbol_on_every_line_it_is_on(self):
        graph = _graph(
            "#M\n\n    def g():\n        return 1\n\n~example\n"
            "    g() == 1\n    g() + g() == 2\n")
        assert _edge(graph, EdgeKind.USES, "m#example#1", "m#g").lines == (
            7, 8)

    def test_there_is_one_edge_for_a_source_and_target(self):
        graph = _graph(
            "#M\n\n    def g():\n        return 1\n\n    def f():\n"
            "        a = g()\n        return g() + g()\n")
        pairs = [(e.source, e.target) for e in graph.edges(EdgeKind.USES)]
        assert len(pairs) == len(set(pairs))


class TestCitesLines:
    def test_a_paragraph_citing_on_two_lines_has_one_edge_with_both(self):
        graph = _graph(
            "#M\n\nIt cites #Sec here\nand again #Sec there.\n\n##Sec\n\n"
            "Body.\n")
        edge = _edge(graph, EdgeKind.CITES, "m#prose#1", "m#Sec")
        assert edge.lines == (3, 4)

    def test_a_name_twice_on_one_line_is_that_line_once(self):
        graph = _graph(
            "#M\n\nBoth #Sec and #Sec.\n\n##Sec\n\nBody.\n")
        edge = _edge(graph, EdgeKind.CITES, "m#prose#1", "m#Sec")
        assert edge.lines == (3,)


class TestOtherEdgesHaveOneLine:
    def test_an_imports_edge_has_its_listing_line(self):
        graph = build_package(
            EXAMPLES / "gutenberg", python_kit.extract_symbols,
            call_extractor=python_kit.extract_calls)
        imports = list(graph.edges(EdgeKind.IMPORTS))
        assert imports
        for edge in imports:
            listing = graph.node(edge.source)
            assert edge.lines == (listing.start_line,)

    def test_a_uses_external_edge_has_its_declaration_line(self):
        graph = build_package(
            EXAMPLES / "ts-media", typescript_kit.extract_symbols,
            call_extractor=typescript_kit.extract_calls)
        found = list(graph.edges(EdgeKind.USES_EXTERNAL))
        assert found
        for edge in found:
            declaration = graph.node(edge.source)
            assert edge.lines == (declaration.start_line,)

    def test_a_contains_edge_has_none(self, roman):
        _root, graph = roman
        assert all(e.lines == () for e in graph.edges(EdgeKind.CONTAINS))

    def test_each_edge_has_its_lines_in_order_and_once(self, example):
        _root, graph = example
        for edge in graph.edges():
            assert list(edge.lines) == sorted(set(edge.lines)), edge


# ── The appendix's name comes from the grammar ───────────────

def _appendices(source: str) -> list[AppendixSection]:
    module = from_tree(parse(source))
    return [s for s in module.post_text.sections
            if isinstance(s, AppendixSection)]


class TestAppendixName:
    def test_a_titled_appendix_carries_its_name(self):
        (appendix,) = _appendices("#M\n\n---\n\n#Appendix Glossary\n\nA.\n")
        assert appendix.name == "Glossary"

    def test_a_name_of_several_words_is_whole(self):
        (appendix,) = _appendices(
            "#M\n\n---\n\n#Appendix Notes on Words\n\nA.\n")
        assert appendix.name == "Notes on Words"

    def test_a_bare_appendix_has_none(self):
        (appendix,) = _appendices("#M\n\n---\n\n#Appendix\n\nA.\n")
        assert appendix.name is None

    def test_the_graphs_names_are_as_they_were(self):
        graph = build(from_tree(parse(
            "#M\n\n---\n\n#Appendix Glossary\n\nA.\n\n#Appendix\n\nB.\n")))
        named = {n.address: n.name for n in graph.nodes(K.APPENDIX)}
        assert named == {"m#Glossary": "Glossary", "m#Appendix": "Appendix"}


# ── A test result is of a test collected ─────────────────────

class TestAResultIsOfACollectedTest:
    def test_a_result_that_matches_no_test_raises(
        self, tmp_path, monkeypatch,
    ):
        (tmp_path / "binding.lob").write_text(
            "#B\n\n---\n\n#Binding\n    ~language python\n",
            encoding="utf-8")
        path = tmp_path / "m.lob"
        path.write_text(
            "#M\n\n---\n\n#Tests\n\n##g\n    1 == 1\n", encoding="utf-8")

        def stray(*_args, **_kwargs):
            return [ClaimResult("m#nowhere", "1 == 1", Status.PASS)]

        fake = dataclasses.replace(python_kit, run_tests=stray)
        monkeypatch.setattr(
            commands, "_get_binding_kit",
            lambda _language: (fake, python_kit.extract_symbols))
        monkeypatch.chdir(tmp_path)
        with pytest.raises(Exception, match="m#nowhere"):
            commands.cmd_test(path, fmt="json")
