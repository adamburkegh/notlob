"""A value that is a node of the graph is an edge; any other value is a
field of its node, and a field with several values is a list.

``notlob/schema/notlob.ttl`` states the rule in OWL: an edge kind is an
``owl:ObjectProperty`` whose range is ``notlob:Node``, and a field an
``owl:DatatypeProperty`` or, for a reference in a paragraph, an
``ObjectProperty`` to a blank node. These tests hold the JSON schema and
every example document to it.
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

NS = "urn:notlob:ns:"
SCHEMAS = Path(notlob.__file__).parent / "schema"
EXAMPLES = Path(__file__).parent.parent / "examples"

_KITS = {
    "roman": python_kit, "retail": python_kit, "gutenberg": python_kit,
    "haskell-roman": haskell_kit, "ts-media": typescript_kit,
}
_LEVELS = ("outline", "index", "full")

#: The ontology term each field of the document is written as in Turtle:
#: restated from ``graph._turtle_node``, which keeps the mapping inline.
_NODE_FIELDS = {
    "address": NS + "address", "label": str(RDFS.label),
    "kind": str(RDF.type), "named": NS + "named", "mode": NS + "mode",
    "declares": NS + "declares", "value": NS + "value",
    "file": NS + "file", "start_line": NS + "startLine",
    "size": NS + "size", "refs": NS + "ref", "text": NS + "text",
}
_REF_FIELDS = {
    "label": str(RDFS.label), "sub": NS + "sub",
    "start_line": NS + "startLine",
}


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
        assert {NS + k.lower() for k in kinds} == _edge_terms()

    def test_the_ontology_has_edges(self):
        assert _edge_terms()

    def test_every_node_property_is_a_field(self):
        properties = _schema()["definitions"]["GraphNode"]["properties"]
        unplaced = set(properties) - set(_NODE_FIELDS)
        assert not unplaced, f"place these in the ontology: {unplaced}"
        for name in properties:
            term = _NODE_FIELDS[name]
            assert term not in _edge_terms(), name
            if term.startswith(NS):
                assert term in _declared_fields(), name

    def test_the_mapping_names_no_property_the_schema_lacks(self):
        properties = _schema()["definitions"]["GraphNode"]["properties"]
        assert set(_NODE_FIELDS) == set(properties)

    def test_every_ref_property_is_a_field(self):
        properties = _schema()["definitions"]["GraphRef"]["properties"]
        unplaced = set(properties) - set(_REF_FIELDS)
        assert not unplaced, f"place these in the ontology: {unplaced}"
        assert set(_REF_FIELDS) == set(properties)
        for name in properties:
            term = _REF_FIELDS[name]
            assert term not in _edge_terms(), name
            if term.startswith(NS):
                assert term in _declared_fields(), name

    def test_a_reference_is_not_a_node(self):
        """``notlob:ref`` is an object property, but its range is not a
        node: a reference is a structured value, so a field."""
        g = _ontology()
        ref = URIRef(NS + "ref")
        assert (ref, RDF.type, OWL.ObjectProperty) in g
        assert (ref, RDFS.range, URIRef(NS + "Node")) not in g
        assert str(ref) in _declared_fields()


# ── Every document keeps the rule ────────────────────────────

@cache
def _graph(project: str):
    kit = _KITS[project]
    return build_package(
        EXAMPLES / project, kit.extract_symbols,
        call_extractor=kit.extract_calls,
        split_imports=kit.split_imports)


def _strings(value, skip: str = "label"):
    """Every string a field holds, at any depth, but those under a key
    named *skip*: a module titled with one word could equal its own
    address."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item, skip)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key != skip:
                yield from _strings(item, skip)


projects = pytest.mark.parametrize("project", sorted(_KITS))
levels = pytest.mark.parametrize("level", _LEVELS)


@projects
@levels
class TestDocumentsKeepTheRule:
    def test_an_edge_joins_two_nodes_of_the_document(self, project, level):
        doc = _graph(project).to_dict(level)
        addresses = {n["address"] for n in doc["nodes"]}
        for edge in doc["edges"]:
            assert edge["source"] in addresses, edge
            assert edge["target"] in addresses, edge

    def test_no_field_holds_the_address_of_a_node(self, project, level):
        """A guard against a node's address smuggled into a string field.
        Two fields are not held to it: ``label``, which a one-word module
        title could equal, and a DECLARATION's ``value``, which is the
        declared string as written, where an EXTERNAL's address is that
        same string verbatim (D9). The two coincide by design, and the
        ``USES_EXTERNAL`` edge is the resolution."""
        doc = _graph(project).to_dict(level)
        addresses = {n["address"] for n in doc["nodes"]}
        for node in doc["nodes"]:
            for name, value in node.items():
                if name in ("address", "label"):
                    continue
                if name == "value" and node["kind"] == "DECLARATION":
                    continue
                held = addresses & set(_strings(value))
                assert not held, (node["address"], name, held)
