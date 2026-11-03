"""The view: a start, a depth and a rank over the tree, and the writers
that write it.

Rank is one scale, defined once in ``notlob/graph.py``: a column in
``KINDS`` and the same for the edge kinds. A named level is a preset of
it. The view gives the nodes, the edges and the bodies at or below its
rank; the writers take the view alone and decide nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import rdflib

from notlob import (
    EdgeKind, NodeKind, build, build_package, from_tree, parse,
)
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit
from notlob.graph import (
    EDGE_RANKS, KINDS, PRESETS, Rank, add_bodies, add_cites_edges,
    add_uses_edges, enrich,
)
from notlob.view import View, ViewEdge, ViewNode, level_view, view
from notlob.writers import write_json, write_text, write_turtle

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"
GOLDEN = Path(__file__).parent / "golden"
NS = "urn:notlob:ns:"
K = NodeKind

_PROJECTS = [
    ("roman", python_kit), ("retail", python_kit),
    ("gutenberg", python_kit), ("haskell-roman", haskell_kit),
    ("ts-media", typescript_kit),
]


def _project(name: str):
    kit = dict(_PROJECTS)[name]
    return build_package(
        EXAMPLES / name, kit.extract_symbols,
        call_extractor=kit.extract_calls, split_imports=kit.split_imports)


def _graph(source: str):
    """A module built from *source* as a project builds it."""
    module = from_tree(parse(source), source=source)
    graph = build(module, "m.lob")
    enrich(graph, module, python_kit.extract_symbols, python_kit.split_imports)
    add_cites_edges(graph)
    add_uses_edges(graph, python_kit.extract_calls)
    add_bodies(graph, module)
    return graph


SOURCE = """\
#M

See #Sec here
and #Sec again.

    def g():
        return 1

##Sec

Also #Sec2 now.

##Sec2

    def f():
        a = g()
        return g()

~example
    f() == 1
"""

TWO_PARAGRAPHS = "#M\n\n##A\n\nOne #T.\n\nTwo #T.\n\n##T\n\nx\n"


def _addresses(v: View) -> list[str]:
    return [n.address for n in v.nodes]


def _edges(v: View) -> list[tuple]:
    return [(e.source, e.target, e.kind, e.lines)
            for e in (*v.tree, *v.references)]


# ── Rank is defined once, beside the kinds ───────────────────

class TestRank:
    def test_the_named_ranks(self):
        assert (Rank.STRUCTURE, Rank.REFERENCES, Rank.BLOCK, Rank.BODY) == (
            1, 2, 3, 4)

    def test_every_kind_has_a_rank(self):
        assert set(KINDS) == set(K)
        assert all(isinstance(f.rank, int) and f.rank >= 1
                   for f in KINDS.values())

    def test_the_rank_of_each_kind(self):
        by_rank = {1: "MODULE SUBHEADING SYMBOL PROPERTY EXAMPLE RUN TEST "
                      "APPENDIX TESTS TEST_GROUP REFERENCES BINDING",
                   2: "DECLARATION EXTERNAL",
                   3: "PROSE CODE BULLETS TEST_LINES LISTING IMPORT "
                      "POST_TEXT"}
        wanted = {K[name]: rank for rank, names in by_rank.items()
                  for name in names.split()}
        assert {k: f.rank for k, f in KINDS.items()} == wanted

    def test_every_edge_kind_has_a_rank(self):
        assert set(EDGE_RANKS) == (
            {k.name for k in EdgeKind} | {"CONTAINS_INDIRECTLY"})

    def test_the_rank_of_each_edge_kind(self):
        assert EDGE_RANKS == {
            "CONTAINS": 1, "CONTAINS_INDIRECTLY": 1, "USES": 2, "CITES": 2,
            "IMPORTS": 2, "USES_EXTERNAL": 2}

    def test_the_presets_are_four_ranks(self):
        assert PRESETS == {"outline": 1, "index": 2, "block": 3, "full": 4}


# ── The view ─────────────────────────────────────────────────

class TestContainment:
    def test_a_view_hides_what_holds_a_node_and_says_so(self):
        v = view(_graph(SOURCE), rank=Rank.STRUCTURE)
        assert ("m", "m#g", "CONTAINS_INDIRECTLY", ()) in _edges(v)
        assert ("m#Sec2", "m#f", "CONTAINS_INDIRECTLY", ()) in _edges(v)
        assert ("m#Sec2", "m#Sec2#example#1", "CONTAINS", ()) in _edges(v)

    def test_a_view_that_hides_nothing_writes_the_tree_alone(self):
        v = view(_graph(SOURCE), rank=Rank.BLOCK)
        assert ("m", "m#code#1", "CONTAINS", ()) in _edges(v)
        assert ("m#code#1", "m#g", "CONTAINS", ()) in _edges(v)
        assert "CONTAINS_INDIRECTLY" not in {e.kind for e in v.tree}

    def test_nodes_and_their_edges_come_in_the_order_written(self):
        v = view(_graph(SOURCE), rank=Rank.STRUCTURE)
        assert _addresses(v) == [
            "m", "m#g", "m#Sec", "m#Sec2", "m#f", "m#Sec2#example#1"]
        assert [e.target for e in v.tree] == _addresses(v)[1:]

    def test_the_nodes_of_a_rank_are_the_nodes_of_the_one_below(self):
        graph = _graph(SOURCE)
        held = [set(_addresses(view(graph, rank=r))) for r in (1, 2, 3, 4)]
        for before, after in zip(held, held[1:]):
            assert before <= after


class TestReferences:
    def test_a_reference_starts_at_the_nearest_node_an_outline_shows(self):
        v = view(_graph(SOURCE), rank=Rank.REFERENCES)
        sources = {(e.source, e.target, e.kind) for e in v.references}
        assert sources == {("m", "m#Sec", "CITES"),
                           ("m#Sec", "m#Sec2", "CITES"),
                           ("m#f", "m#g", "USES"),
                           ("m#Sec2#example#1", "m#f", "USES")}

    def test_it_starts_there_at_every_rank_that_has_it(self):
        graph = _graph(SOURCE)
        held = [view(graph, rank=r).references for r in (2, 3, 4)]
        assert held[0] == held[1] == held[2]

    def test_an_outline_has_none(self):
        assert view(_graph(SOURCE), rank=Rank.STRUCTURE).references == ()

    def test_every_line_it_is_written_on(self):
        v = view(_graph(SOURCE), rank=Rank.REFERENCES)
        lines = {(e.source, e.target): e.lines for e in v.references}
        assert lines == {("m", "m#Sec"): (3, 4),
                         ("m#Sec", "m#Sec2"): (11,),
                         ("m#f", "m#g"): (16, 17),
                         ("m#Sec2#example#1", "m#f"): (20,)}

    def test_references_merged_on_a_source_join_their_lines(self):
        v = view(_graph(TWO_PARAGRAPHS), rank=Rank.REFERENCES)
        (edge,) = v.references
        assert (edge.source, edge.target, edge.kind, edge.lines) == (
            "m#A", "m#T", "CITES", (5, 7))

    def test_an_edge_is_in_the_view_only_if_both_its_ends_are(self):
        graph = _graph(SOURCE)
        v = view(graph, start="m#Sec2", rank=Rank.REFERENCES)
        assert [(e.source, e.target) for e in v.references] == [
            ("m#Sec2#example#1", "m#f")]

    def test_a_target_the_rank_hides_leaves_the_edge_out(self):
        v = view(_graph(SOURCE), rank=Rank.REFERENCES)
        assert all(e.target in _addresses(v) for e in v.references)


class TestStartAndDepth:
    def test_a_start_is_the_root_of_the_view(self):
        v = view(_graph(SOURCE), start="m#Sec2", rank=Rank.BLOCK)
        assert _addresses(v) == [
            "m#Sec2", "m#Sec2#code#1", "m#f", "m#Sec2#example#1"]

    def test_depth_counts_the_steps_the_view_shows(self):
        graph = _graph(SOURCE)
        assert _addresses(view(graph, depth=1, rank=Rank.BLOCK)) == [
            "m", "m#prose#1", "m#code#1", "m#Sec", "m#Sec2"]
        assert _addresses(view(graph, depth=1, rank=Rank.STRUCTURE)) == [
            "m", "m#g", "m#Sec", "m#Sec2"]

    def test_depth_nought_is_the_start_alone(self):
        v = view(_graph(SOURCE), depth=0, rank=Rank.BODY)
        assert _addresses(v) == ["m"]


class TestBodiesAndLevel:
    def test_bodies_come_with_the_last_rank(self):
        graph = _graph(SOURCE)
        for rank in (1, 2, 3):
            assert all(n.body is None for n in view(graph, rank=rank).nodes)
        v = view(graph, rank=Rank.BODY)
        assert {n.address: n.body for n in v.nodes}["m#Sec"] == "##Sec"
        assert {n.address: n.body for n in v.nodes}["m#g"] is None

    def test_a_view_has_no_level_of_its_own(self):
        assert view(_graph(SOURCE), rank=2).level is None

    def test_a_view_made_from_a_preset_carries_its_name(self):
        graph = _graph(SOURCE)
        for name, rank in PRESETS.items():
            v = level_view(graph, name)
            assert v.level == name
            assert (v.nodes, v.tree, v.references) == (
                view(graph, rank=rank).nodes, view(graph, rank=rank).tree,
                view(graph, rank=rank).references)

    def test_an_unknown_level_names_the_choices(self):
        with pytest.raises(ValueError, match="outline, index, block, full"):
            level_view(_graph(SOURCE), "everything")

    def test_only_a_file_s_root_has_the_file(self):
        v = view(_graph(SOURCE), rank=Rank.BLOCK)
        assert {n.address: n.file for n in v.nodes if n.file} == {
            "m": "m.lob"}


# ── The writers take the view alone ──────────────────────────

def _small(level: str | None = "index") -> View:
    return View(
        level=level,
        nodes=(ViewNode(address="m", name="M", kind=K.MODULE,
                        file="m.lob", start_line=1),
               ViewNode(address="m#g", name="g", kind=K.SYMBOL,
                        start_line=3)),
        tree=(ViewEdge("m", "m#g", "CONTAINS"),),
        references=(ViewEdge("m", "m#g", "USES", (4, 5)),))


class TestWritersTakeTheViewAlone:
    def test_json_writes_the_view(self):
        doc = json.loads(write_json(_small()))
        assert doc == {
            "version": 2, "level": "index",
            "nodes": [{"address": "m", "name": "M", "kind": "MODULE",
                       "file": "m.lob", "start_line": 1},
                      {"address": "m#g", "name": "g", "kind": "SYMBOL",
                       "start_line": 3}],
            "edges": [{"source": "m", "target": "m#g", "kind": "CONTAINS"},
                      {"source": "m", "target": "m#g", "kind": "USES",
                       "lines": [4, 5]}]}

    def test_json_writes_a_body_and_a_derived_node_has_none(self):
        v = View(level="full", nodes=(
            ViewNode(address="m", name="M", kind=K.MODULE, file="m.lob",
                     start_line=1, body="#M"),), tree=(), references=())
        assert json.loads(write_json(v))["nodes"][0]["body"] == "#M"

    def test_turtle_writes_every_edge_a_triple_and_its_lines_beside(self):
        g = rdflib.Graph()
        g.parse(data=write_turtle(_small()), format="turtle",
                publicID="http://example.test/")
        m, sym = (rdflib.URIRef(f"http://example.test/{a}")
                  for a in ("m", "m#g"))
        assert (m, rdflib.URIRef(NS + "contains"), sym) in g
        assert (m, rdflib.URIRef(NS + "uses"), sym) in g
        (statement,) = g.subjects(rdflib.RDF.type, rdflib.RDF.Statement)
        assert g.value(statement, rdflib.RDF.subject) == m
        assert g.value(statement, rdflib.RDF.predicate) == rdflib.URIRef(
            NS + "uses")
        assert g.value(statement, rdflib.RDF.object) == sym
        assert sorted(int(o) for o in g.objects(
            statement, rdflib.URIRef(NS + "lines"))) == [4, 5]

    def test_turtle_names_a_kind_as_a_class_and_a_field_in_camel_case(self):
        g = rdflib.Graph()
        g.parse(data=write_turtle(_small()), format="turtle",
                publicID="http://example.test/")
        m = rdflib.URIRef("http://example.test/m")
        assert (m, rdflib.RDF.type, rdflib.URIRef(NS + "Module")) in g
        assert g.value(m, rdflib.URIRef(NS + "startLine")).toPython() == 1
        assert str(g.value(m, rdflib.URIRef(NS + "file"))) == "m.lob"

    def test_text_is_a_file_its_lines_and_every_line_of_a_reference(self):
        assert write_text(_small()) == (
            "m.lob\n"
            "M" + " " * 12 + "1\n"
            "  g" + " " * 10 + "3\n"
            "  uses g  4, 5\n")

    def test_a_level_s_name_is_nothing_a_writer_reads_but_json(self):
        assert write_text(_small("full")) == write_text(_small(None))
        assert write_turtle(_small("full")) == write_turtle(_small(None))
        assert (json.loads(write_json(_small("full")))["level"] == "full")

    def test_text_at_a_view_with_bodies_is_the_file(self):
        v = View(level=None, nodes=(
            ViewNode(address="m", name="M", kind=K.MODULE, file="m.lob",
                     start_line=1, body="#M"),
            ViewNode(address="m#Sec", name="Sec", kind=K.SUBHEADING,
                     start_line=3, body="##Sec")),
            tree=(ViewEdge("m", "m#Sec", "CONTAINS"),), references=())
        assert write_text(v) == "m.lob\n#M\n\n##Sec\n"


# ── Text, exactly ────────────────────────────────────────────

def _golden(name: str) -> str:
    return (GOLDEN / name).read_text(encoding="utf-8")


class TestRomansNumeralsAsText:
    @pytest.mark.parametrize("level", ["outline", "index", "block"])
    def test_at_each_level_but_full(self, level):
        graph = _project("roman")
        text = write_text(level_view(graph, level, start="roman/numerals"))
        assert text == _golden(f"view_roman_{level}.txt")

    def test_at_full_it_is_the_file_under_its_path(self):
        graph = _project("roman")
        text = write_text(level_view(graph, "full", start="roman/numerals"))
        written = (EXAMPLES / "roman" / "roman" / "numerals.lob").read_text(
            encoding="utf-8")
        assert text == "roman/numerals.lob\n" + written.rstrip("\n") + "\n"


class TestRetailAsText:
    @pytest.mark.parametrize("level", ["index", "block"])
    def test_it_is_as_written(self, level):
        text = write_text(level_view(_project("retail"), level))
        assert text == _golden(f"view_retail_{level}.txt")


@pytest.mark.parametrize("name", [n for n, _ in _PROJECTS])
def test_the_text_of_an_example_at_full_is_its_files_each_under_its_path(
    name,
):
    graph = _project(name)
    files = [m.file for m in graph.nodes(K.MODULE)]
    wanted = "\n".join(
        f"{file}\n" + (EXAMPLES / name / file).read_text(
            encoding="utf-8").rstrip("\n") + "\n"
        for file in files)
    assert write_text(level_view(graph, "full")) == wanted
