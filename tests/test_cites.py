"""The edge a prose `#Label` makes is `CITES`.

`#References` is the section that lists modules, and it makes `IMPORTS`
edges; the edge a paragraph makes to what its `#Label` names was called
`REFERENCES`, which contradicts that heading. A module *cites* what its
prose mentions. The section keeps its own names.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import notlob
import notlob.check
import notlob.cli as cli
import notlob.commands as commands
import notlob.graph as graph_module
import notlob.model
import notlob.parser
from notlob import EdgeKind, build, from_tree, parse
from notlob.graph import add_cites_edges, cited_by, cites_of

SCHEMAS = Path(notlob.__file__).parent / "schema"

_SOURCE = "#M\n\n##A\n\nSee ##B.\n\n##B\n\nText.\n"


def _graph():
    graph = build(from_tree(parse(_SOURCE)))
    add_cites_edges(graph)
    return graph


def _enums(node):
    """Every list under an ``enum`` key in a parsed schema."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "enum":
                yield value
            else:
                yield from _enums(value)
    elif isinstance(node, list):
        for item in node:
            yield from _enums(item)


class TestTheEdgeKind:
    def test_it_is_called_cites(self):
        assert "CITES" in EdgeKind.__members__
        assert "REFERENCES" not in EdgeKind.__members__

    def test_a_document_prints_it_so(self):
        edges = _graph().to_dict("index")["edges"]
        assert [e["kind"] for e in edges if e["source"] == "m#A#prose#1"
                ] == ["CITES"]

    def test_so_does_the_outline(self):
        edges = _graph().to_dict()["edges"]
        assert {"source": "m#A", "target": "m#B", "kind": "CITES",
                "start_line": 5} in edges
        assert "REFERENCES" not in {e["kind"] for e in edges}

    def test_so_does_turtle(self):
        turtle = _graph().to_turtle()
        assert "notlob:cites" in turtle
        assert "notlob:references" not in turtle


class TestTheOntologyAndSchemas:
    def test_the_ontology_declares_cites(self):
        text = (SCHEMAS / "notlob.ttl").read_text(encoding="utf-8")
        assert "notlob:cites a owl:ObjectProperty" in text
        assert "notlob:references" not in text

    @pytest.mark.parametrize("name", ["name_graph.json", "query_result.json"])
    def test_the_edge_enums_say_cites(self, name):
        schema = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
        edge_enums = [e for e in _enums(schema) if "CONTAINS" in e]
        assert edge_enums
        for values in edge_enums:
            assert "CITES" in values
            assert "REFERENCES" not in values


class TestTheFunctions:
    def test_the_old_names_are_gone(self):
        for name in ("add_references_edges", "references_of",
                     "referenced_by"):
            assert not hasattr(graph_module, name)
        for name in ("cmd_query_references", "cmd_query_referenced_by"):
            assert not hasattr(commands, name)

    def test_the_new_names_answer(self):
        graph = _graph()
        assert [n.address for n in cites_of(graph, "m#A")] == ["m#B"]
        assert [n.address for n in cited_by(graph, "m#B")] == ["m#A"]


class TestTheQueries:
    def _query(self, monkeypatch, *words):
        monkeypatch.setattr(sys, "argv", ["notlob", "query", *words])
        with pytest.raises(SystemExit) as raised:
            cli.main()
        return raised.value.code

    def test_cites_and_cited_by_exist(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            cli, "cmd_query_cites",
            lambda a, fmt: called.append(("cites", a)) or 0)
        monkeypatch.setattr(
            cli, "cmd_query_cited_by",
            lambda a, fmt: called.append(("cited-by", a)) or 0)
        assert self._query(monkeypatch, "cites", "m#A") == 0
        assert self._query(monkeypatch, "cited-by", "m#B") == 0
        assert called == [("cites", "m#A"), ("cited-by", "m#B")]

    @pytest.mark.parametrize("old", ["references", "referenced-by"])
    def test_the_old_queries_do_not(self, monkeypatch, old, capsys):
        assert self._query(monkeypatch, old, "m#A") == 2
        assert "invalid choice" in capsys.readouterr().err

    def test_children_offers_cites_as_an_edge_kind(self):
        assert "CITES" in commands.QUERY_EDGE_KINDS
        assert "REFERENCES" not in commands.QUERY_EDGE_KINDS


class TestTheSectionKeepsItsNames:
    """The `#References` section, its heading and its check are not the
    edge: they are not renamed."""

    def test_the_section_and_its_heading(self):
        assert hasattr(notlob.model, "ReferencesSection")
        assert "REFERENCES_HEAD" in notlob.parser.__dict__ or (
            "REFERENCES_HEAD" in Path(notlob.parser.__file__).read_text(
                encoding="utf-8"))

    def test_the_check(self):
        assert "references" in notlob.check.CHECK_NAMES
