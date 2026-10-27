"""The graph document says each thing once.

A node carries its ``label`` and ``file`` only if it is a module: any
other node's follow from its address. The tree stays in ``edges``, as
``CONTAINS`` edges like the others, and ``nodes`` and those edges are in
the order the files are written. Turtle writes the same facts, its
``contains`` triples the ``CONTAINS`` edges. The answers to a query keep a
node's ``label`` and ``file``, as they stand on their own.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import jsonschema
import pytest
import rdflib

from notlob import NodeKind, build_package
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit
from notlob.graph import EdgeKind, KINDS, node_summary

EXAMPLES = Path(__file__).parent.parent / "examples"
SCHEMA = (Path(__file__).parent.parent / "notlob" / "schema"
          / "name_graph.json")

_KITS = {
    "roman": python_kit, "retail": python_kit, "gutenberg": python_kit,
    "haskell-roman": haskell_kit, "ts-media": typescript_kit,
}
_LEVELS = ("outline", "index", "full")
_NS = "urn:notlob:ns:"


@cache
def _graph(project: str):
    kit = _KITS[project]
    return build_package(
        EXAMPLES / project, kit.extract_symbols,
        call_extractor=kit.extract_calls,
        split_imports=kit.split_imports)


def _derived_label(node) -> str:
    """A node's label from its address alone."""
    facts = KINDS[node.kind]
    if node.name is not None or facts.segment is None:
        return node.address.rsplit("#", 1)[1]
    if facts.numbered:
        return "#".join(node.address.rsplit("#", 2)[-2:])
    return facts.segment


def _contains(doc: dict) -> list[dict]:
    return [e for e in doc["edges"] if e["kind"] == "CONTAINS"]


projects = pytest.mark.parametrize("project", sorted(_KITS))
levels = pytest.mark.parametrize("level", _LEVELS)


# ── Nothing said twice ───────────────────────────────────────

@projects
@levels
class TestNothingSaidTwice:
    def test_only_a_module_has_a_label_or_a_file(self, project, level):
        doc = _graph(project).to_dict(level)
        for entry in doc["nodes"]:
            if entry["kind"] == "MODULE":
                assert "label" in entry and "file" in entry, entry
            else:
                assert "label" not in entry, entry
                assert "file" not in entry, entry

    def test_the_label_follows_from_the_address(self, project, level):
        graph = _graph(project)
        shown = {e["address"] for e in graph.to_dict(level)["nodes"]}
        for node in graph.nodes():
            if node.address not in shown or node.kind in (
                    NodeKind.MODULE, NodeKind.EXTERNAL):
                continue
            assert node.label == _derived_label(node), node.address

    def test_no_node_has_a_parent_field(self, project, level):
        doc = _graph(project).to_dict(level)
        assert not [e for e in doc["nodes"] if "parent" in e]

    def test_it_validates(self, project, level):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        jsonschema.validate(_graph(project).to_dict(level), schema)


# ── The tree survives ────────────────────────────────────────

def _lifted_contains(graph, level: str) -> set[tuple[str, str]]:
    """The tree's edges as the level shows them, from the graph: each
    taken to the nearest node above that the level shows, and none into a
    node it leaves out."""
    def hidden(address: str) -> bool:
        return (level == "outline"
                and KINDS[graph.node(address).kind].hidden_at_outline)

    def shown(address: str) -> str:
        while hidden(address):
            address = graph.parent_of(address).address
        return address

    return {
        (shown(e.source), e.target)
        for e in graph.edges(EdgeKind.CONTAINS) if not hidden(e.target)
    }


@projects
@levels
class TestTheTreeSurvives:
    def test_each_node_but_a_root_has_one_contains_edge_into_it(
        self, project, level,
    ):
        doc = _graph(project).to_dict(level)
        into: dict[str, list[str]] = {}
        for edge in _contains(doc):
            into.setdefault(edge["target"], []).append(edge["source"])
        for entry in doc["nodes"]:
            if entry["kind"] in ("MODULE", "EXTERNAL"):
                assert entry["address"] not in into, entry
            else:
                assert len(into.get(entry["address"], [])) == 1, entry

    def test_the_edges_are_the_graphs_lifted_to_what_is_shown(
        self, project, level,
    ):
        graph = _graph(project)
        written = {(e["source"], e["target"])
                   for e in _contains(graph.to_dict(level))}
        assert written == _lifted_contains(graph, level)

    def test_an_edge_joins_nodes_the_level_shows(self, project, level):
        doc = _graph(project).to_dict(level)
        shown = {e["address"] for e in doc["nodes"]}
        for edge in doc["edges"]:
            assert edge["source"] in shown, edge
            assert edge["target"] in shown, edge


# ── The order ────────────────────────────────────────────────

def _preorder(doc: dict) -> list[str]:
    """The order a depth-first walk of the ``CONTAINS`` edges gives,
    taking each node's children in the order of the edges, and the roots
    in the order of *nodes*."""
    children: dict[str, list[str]] = {}
    for edge in _contains(doc):
        children.setdefault(edge["source"], []).append(edge["target"])
    order: list[str] = []

    def walk(address: str) -> None:
        order.append(address)
        for child in children.get(address, []):
            walk(child)

    for entry in doc["nodes"]:
        if entry["kind"] in ("MODULE", "EXTERNAL"):
            walk(entry["address"])
    return order


@projects
@levels
class TestWritingOrder:
    def test_nodes_are_a_depth_first_walk_of_the_tree(
        self, project, level,
    ):
        doc = _graph(project).to_dict(level)
        assert [e["address"] for e in doc["nodes"]] == _preorder(doc)

    def test_contains_edges_follow_the_order_of_nodes(
        self, project, level,
    ):
        doc = _graph(project).to_dict(level)
        roots = ("MODULE", "EXTERNAL")
        assert ([e["target"] for e in _contains(doc)]
                == [n["address"] for n in doc["nodes"]
                    if n["kind"] not in roots])

    def test_contains_edges_come_before_the_rest(self, project, level):
        kinds = [e["kind"] == "CONTAINS"
                 for e in _graph(project).to_dict(level)["edges"]]
        assert kinds == sorted(kinds, reverse=True)

    def test_a_nodes_children_are_in_the_order_written(
        self, project, level,
    ):
        doc = _graph(project).to_dict(level)
        line = {e["address"]: e.get("start_line", 0) for e in doc["nodes"]}
        last: dict[str, int] = {}
        for edge in _contains(doc):
            here = line[edge["target"]]
            assert here >= last.get(edge["source"], 0), edge
            last[edge["source"]] = here

    def test_modules_come_in_the_order_added_and_externals_last(
        self, project, level,
    ):
        graph = _graph(project)
        nodes = graph.to_dict(level)["nodes"]
        kinds = [e["kind"] for e in nodes]
        external = [i for i, k in enumerate(kinds) if k == "EXTERNAL"]
        assert external == list(range(len(kinds) - len(external),
                                      len(kinds)))
        assert ([e["address"] for e in nodes if e["kind"] == "MODULE"]
                == [n.address for n in graph.nodes(NodeKind.MODULE)])
        assert ([e["address"] for e in nodes if e["kind"] == "EXTERNAL"]
                == [n.address for n in graph.nodes(NodeKind.EXTERNAL)])


@levels
def test_roman_puts_a_symbol_after_its_section(level):
    doc = _graph("roman").to_dict(level)
    order = [e["address"] for e in doc["nodes"]]
    section = "roman/numerals#Decoding"
    symbol = "roman/numerals#from_roman"
    example = section + "#example#1"
    assert order.index(section) < order.index(symbol) < order.index(example)
    written = [e["target"] for e in _contains(doc)]
    assert (written.index(section) < written.index(symbol)
            < written.index(example))


# ── POST_TEXT ────────────────────────────────────────────────

@projects
class TestPostText:
    def test_it_is_hidden_at_outline_only(self, project):
        graph = _graph(project)
        has = any(graph.nodes(NodeKind.POST_TEXT))
        assert KINDS[NodeKind.POST_TEXT].hidden_at_outline
        for level in _LEVELS:
            kinds = {e["kind"] for e in graph.to_dict(level)["nodes"]}
            assert ("POST_TEXT" in kinds) == (has and level != "outline")

    @levels
    def test_its_children_are_contained_by_it_or_by_the_module(
        self, project, level,
    ):
        graph = _graph(project)
        doc = graph.to_dict(level)
        holder = {e["target"]: e["source"] for e in _contains(doc)}
        for node in graph.nodes():
            above = graph.parent_of(node.address)
            if (above is None or above.kind != NodeKind.POST_TEXT
                    or node.address not in holder):
                continue
            expected = (graph.parent_of(above.address).address
                        if level == "outline" else above.address)
            assert holder[node.address] == expected, node.address


# ── Turtle ───────────────────────────────────────────────────

def _turtle(graph, level: str) -> rdflib.Graph:
    g = rdflib.Graph()
    g.parse(data=graph.to_turtle(level=level), format="turtle",
            publicID="http://example.test/")
    return g


@projects
@levels
class TestTurtle:
    def test_the_same_nodes(self, project, level):
        graph = _graph(project)
        g = _turtle(graph, level)
        found = {str(o) for o in g.objects(None,
                                           rdflib.URIRef(_NS + "address"))}
        assert found == {e["address"]
                         for e in graph.to_dict(level)["nodes"]}

    def test_contains_triples_are_the_contains_edges(self, project, level):
        graph = _graph(project)
        g = _turtle(graph, level)
        address = rdflib.URIRef(_NS + "address")
        found = {(str(g.value(s, address)), str(g.value(o, address)))
                 for s, o in g.subject_objects(
                     rdflib.URIRef(_NS + "contains"))}
        expected = {(e["source"], e["target"])
                    for e in _contains(graph.to_dict(level))}
        assert found == expected

    def test_label_and_file_are_on_modules_only(self, project, level):
        g = _turtle(_graph(project), level)
        modules = set(g.subjects(rdflib.RDF.type,
                                 rdflib.URIRef(_NS + "Module")))
        file = rdflib.URIRef(_NS + "file")
        # a blank node is a reference in a paragraph, with a label of its own
        labelled = {s for s in g.subjects(rdflib.RDFS.label, None)
                    if isinstance(s, rdflib.URIRef)}
        assert labelled == modules
        assert set(g.subjects(file, None)) <= modules


# ── Queries keep their answers ───────────────────────────────

@projects
def test_a_query_answer_stands_on_its_own(project):
    graph = _graph(project)
    for node in graph.nodes():
        summary = node_summary(node)
        assert summary["label"] == node.label
        if node.file is not None:
            assert summary["file"] == node.file
        assert "parent" not in summary
