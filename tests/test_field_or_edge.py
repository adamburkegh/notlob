"""A value that is a node of the graph is an edge; any other value is a
field of its node, and a field with several values is a list.

``notlob/schema/notlob.ttl`` states the rule in OWL: an edge kind is an
``owl:ObjectProperty`` whose range is ``notlob:Node``, and a field an
``owl:DatatypeProperty``. These tests hold the JSON schema and every
example document to it.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import pytest
import rdflib
from rdflib import OWL, RDF, RDFS, URIRef

import notlob
from notlob import build_package
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit
from notlob.graph import PRESETS
from notlob.view import level_view
from notlob.writers import turtle_field_name, write_json

NS = "urn:notlob:ns:"
SCHEMAS = Path(notlob.__file__).parent / "schema"
EXAMPLES = Path(__file__).parent.parent / "examples"

_KITS = {
    "roman": python_kit, "retail": python_kit, "gutenberg": python_kit,
    "haskell-roman": haskell_kit, "ts-media": typescript_kit,
}


def _term(field: str) -> str:
    """The ontology term a field of the document is written as in Turtle:
    its name in camelCase, and for a node's kind the class it is of."""
    return str(RDF.type) if field == "kind" else NS + turtle_field_name(field)


@cache
def _ontology() -> rdflib.Graph:
    g = rdflib.Graph()
    g.parse(SCHEMAS / "notlob.ttl", format="turtle")
    return g


@cache
def _schema() -> dict:
    return json.loads(
        (SCHEMAS / "name_graph.json").read_text(encoding="utf-8"))


def _edge_terms() -> set[str]:
    """The ontology's edges: object properties whose range is a node."""
    g = _ontology()
    node = URIRef(NS + "Node")
    return {str(s) for s in g.subjects(RDF.type, OWL.ObjectProperty)
            if (s, RDFS.range, node) in g}


def _declared_fields() -> set[str]:
    """The ontology's fields: the datatype properties, and the object
    properties that are not edges."""
    g = _ontology()
    declared = set(map(str, g.subjects(RDF.type, OWL.DatatypeProperty)))
    declared |= set(map(str, g.subjects(RDF.type, OWL.ObjectProperty)))
    return declared - _edge_terms()


# ── The schema agrees with the ontology ──────────────────────

class TestSchemaAgreesWithOntology:
    def test_edge_kinds_are_the_ontologys_edges(self):
        kinds = _schema()["definitions"]["GraphEdge"]["properties"][
            "kind"]["enum"]
        assert {_term(k) for k in kinds} == _edge_terms()

    def test_the_ontology_has_edges(self):
        assert _edge_terms()

    def test_every_node_property_is_a_field(self):
        properties = _schema()["definitions"]["GraphNode"]["properties"]
        for name in properties:
            term = _term(name)
            assert term not in _edge_terms(), name
            if term.startswith(NS):
                assert term in _declared_fields(), name

    def test_an_edge_property_with_lines_is_a_field_too(self):
        properties = _schema()["definitions"]["GraphEdge"]["properties"]
        assert "lines" in properties
        assert _term("lines") in _declared_fields()


# ── Every document keeps the rule ────────────────────────────

@cache
def _graph(project: str):
    kit = _KITS[project]
    return build_package(
        EXAMPLES / project, kit.extract_symbols,
        call_extractor=kit.extract_calls,
        split_imports=kit.split_imports)


def _strings(value):
    """Every string a field holds, at any depth."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


projects = pytest.mark.parametrize("project", sorted(_KITS))
levels = pytest.mark.parametrize("level", list(PRESETS))


@projects
@levels
class TestDocumentsKeepTheRule:
    def _document(self, project, level) -> dict:
        return json.loads(write_json(level_view(_graph(project), level)))

    def test_an_edge_joins_two_nodes_of_the_document(self, project, level):
        doc = self._document(project, level)
        addresses = {n["address"] for n in doc["nodes"]}
        for edge in doc["edges"]:
            assert edge["source"] in addresses, edge
            assert edge["target"] in addresses, edge

    def test_no_field_holds_the_address_of_a_node(self, project, level):
        """A guard against a node's address smuggled into a string field.
        Three fields are not held to it: ``name``, which a one-word module
        title could equal; ``body``, which is the lines as written; and a
        DECLARATION's ``value``, which is the declared string as written,
        where an EXTERNAL's address is that same string verbatim. The two
        coincide by design, and the ``USES_EXTERNAL`` edge is the
        resolution."""
        doc = self._document(project, level)
        addresses = {n["address"] for n in doc["nodes"]}
        for node in doc["nodes"]:
            for name, value in node.items():
                if name in ("address", "name", "body"):
                    continue
                if name == "value" and node["kind"] == "DECLARATION":
                    continue
                held = addresses & set(_strings(value))
                assert not held, (node["address"], name, held)
