"""The Turtle writer (``notlob graph --format turtle``) and its ontology.

The vocabulary lives in ``notlob/schema/notlob.ttl`` under the informal
``urn:notlob:ns:`` namespace. These tests parse real output with rdflib (the
Turtle equivalent of validating JSON against its schema), and hold the
ontology to the writer both ways: every class and predicate the writer
writes, at every level of every example, is declared, and every
declaration is written somewhere. What the writer writes is also held to
the JSON document, in ``test_graph_document.py``.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
from pathlib import Path

import pytest
import rdflib
from rdflib import OWL, RDF, RDFS, XSD, URIRef

import notlob
from notlob import EdgeKind, NodeKind, build_package
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit
from notlob.commands import cmd_graph
from notlob.graph import PRESETS
from notlob.view import ViewNode, level_view
from notlob.writers import (
    _turtle_iri, _turtle_lit, _turtle_long_lit, turtle_class_name,
    turtle_field_name, write_turtle,
)
from test_graph_document import SMALL

NS = "urn:notlob:ns:"
ONTOLOGY = Path(notlob.__file__).parent / "schema" / "notlob.ttl"
EXAMPLES = Path(__file__).parent.parent / "examples"
# Relative IRIs resolve against this when a document is parsed.
DOC = "http://example.test/doc/"

_PROJECTS = [
    ("roman", python_kit), ("retail", python_kit),
    ("gutenberg", python_kit), ("haskell-roman", haskell_kit),
    ("ts-media", typescript_kit),
]


def _parse(text: str) -> rdflib.Graph:
    g = rdflib.Graph()
    g.parse(data=text, format="turtle", publicID=DOC)
    return g


def _ontology() -> rdflib.Graph:
    g = rdflib.Graph()
    g.parse(ONTOLOGY, format="turtle")
    return g


def _term(name: str) -> URIRef:
    return URIRef(NS + name)


def _graph(root: Path, kit):
    return build_package(
        root, kit.extract_symbols, call_extractor=kit.extract_calls,
        split_imports=kit.split_imports)


@pytest.fixture(scope="module")
def small(tmp_path_factory):
    root = tmp_path_factory.mktemp("small")
    for name, text in SMALL.items():
        (root / name).write_text(text, encoding="utf-8")
    return _graph(root, python_kit)


@pytest.fixture(scope="module")
def everything(small):
    """The graphs of the five examples and of a small project that has
    what they lack."""
    return [small] + [_graph(EXAMPLES / name, kit) for name, kit in _PROJECTS]


# ── The IRI and literal helpers ───────────────────────────────

class TestIri:
    def test_plain_address_is_unchanged(self):
        assert _turtle_iri("roman/numerals#Decoding") == (
            "<roman/numerals#Decoding>")

    def test_forbidden_characters_are_percent_encoded(self):
        iri = _turtle_iri('a b"c<d>e{f}g|h\\i^j`k')
        body = iri[1:-1]
        assert not set(' "<>{}|\\^`') & set(body)
        assert body.count("%") == 10

    def test_only_the_first_hash_is_a_fragment_separator(self):
        body = _turtle_iri("mod#Tests#group#name")[1:-1]
        assert body.count("#") == 1
        assert body == "mod#Tests%23group%23name"

    def test_a_literal_percent_is_encoded_so_it_is_reversible(self):
        assert _turtle_iri("100%")[1:-1] == "100%25"

    def test_colon_in_the_first_segment_is_encoded(self):
        """`foo:/bar` as a relative reference would be read as scheme
        `foo`."""
        body = _turtle_iri("foo:/bar")[1:-1]
        assert body == "foo%3A/bar"

    def test_colon_after_the_first_segment_is_kept(self):
        assert _turtle_iri("mod#a:b")[1:-1] == "mod#a:b"

    def test_non_ascii_is_kept(self):
        assert _turtle_iri("日本語#名前")[1:-1] == "日本語#名前"


class TestLiterals:
    @pytest.mark.parametrize("text", [
        'plain', 'say "hi"', 'back\\slash', 'line\nbreak', 'carriage\rreturn',
        'tab\there', '日本語', '', 'ends with a quote"',
    ])
    def test_short_literal_round_trips(self, text):
        g = _parse(f"<s> <p> {_turtle_lit(text)} .")
        assert [str(o) for o in g.objects()] == [text]

    @pytest.mark.parametrize("text", [
        'plain', 'ends with a quote"', 'ends with two""', '"""', 'a"""b',
        'back\\slash', 'ends with a backslash\\', 'line\nbreak\r\nwindows',
        '日本語 "quoted"',
    ])
    def test_long_literal_round_trips(self, text):
        g = _parse(f"<s> <p> {_turtle_long_lit(text)} .")
        assert [str(o) for o in g.objects()] == [text]

    @pytest.mark.parametrize("text", [
        'ends with a quote"', 'ends with two""', '"""', 'a"""b', 'a"b',
    ])
    def test_long_literal_has_no_unescaped_quote(self, text):
        """rdflib is lenient about a long literal that ends in a quote
        (making four in a row at the close) or holds three in a row;
        strict Turtle parsers are not. Escaping every quote is valid and
        unambiguous."""
        body = _turtle_long_lit(text)[3:-3]
        assert re.search(r'(?<!\\)"', body) is None

    def test_short_literal_has_no_raw_line_break(self):
        lit = _turtle_lit("a\nb\rc")
        assert "\n" not in lit and "\r" not in lit


class TestNames:
    @pytest.mark.parametrize("kind,name", [
        (NodeKind.MODULE, "Module"), (NodeKind.POST_TEXT, "PostText"),
        (NodeKind.TEST_GROUP, "TestGroup"), (NodeKind.TESTS, "Tests"),
    ])
    def test_a_class_is_upper_camel_case(self, kind, name):
        assert turtle_class_name(kind) == name

    def test_every_kind_has_a_class(self):
        names = [turtle_class_name(k) for k in NodeKind]
        assert len(set(names)) == len(NodeKind)
        assert all(re.fullmatch(r"[A-Z][A-Za-z]*", n) for n in names)

    @pytest.mark.parametrize("word,name", [
        ("start_line", "startLine"), ("USES_EXTERNAL", "usesExternal"),
        ("CONTAINS_INDIRECTLY", "containsIndirectly"), ("CITES", "cites"),
        ("body", "body"),
    ])
    def test_a_field_or_edge_is_camel_case(self, word, name):
        assert turtle_field_name(word) == name


# ── Real output ───────────────────────────────────────────────

class TestWrittenTurtle:
    @pytest.mark.parametrize("level", PRESETS)
    def test_it_parses_at_every_level(self, small, level):
        _parse(write_turtle(level_view(small, level)))

    def test_vocabulary_is_the_urn_namespace(self, small):
        text = write_turtle(level_view(small, "outline"))
        assert f"@prefix notlob: <{NS}> ." in text
        assert "notlob.dev" not in text and "@base" not in text

    def test_a_node_as_documented(self, small):
        text = write_turtle(level_view(small, "outline"))
        assert (
            "<hello#welcome> a notlob:Symbol ;\n"
            '    notlob:address "hello#welcome" ;\n'
            '    notlob:name "welcome" ;\n'
            "    notlob:startLine 8 ."
        ) in text

    @pytest.mark.parametrize("source", [
        '#Plain\n\nText.\n',
        '#Quote\n\n##Say "hi" now\n\nText "ending in a quote"\n',
        '#Angle\n\n##A <b> tag\n\nBody.\n',
        '#Hash\n\n##Notes\n\nC# and #5 in prose.\n',
        '#Percent\n\n##100% done\n\nBody.\n',
        '#Foo: Bar\n\nBody.\n',
        '#Braces\n\n##Set {a|b}\n\nBody.\n',
        '#Unicode\n\n##日本語 Notes\n\nBody.\n',
        '#Backslash\n\nPath C:\\dir and "quotes".\n',
    ])
    def test_awkward_titles_and_prose_round_trip(self, tmp_path, source):
        (tmp_path / "m.lob").write_text(source, encoding="utf-8")
        graph = _graph(tmp_path, python_kit)
        full = level_view(graph, "full")
        parsed = _parse(write_turtle(full))
        by_address = {str(o): s for s, o in
                      parsed.subject_objects(_term("address"))}
        for node in full.nodes:
            assert node.address in by_address, node.address
            subject = by_address[node.address]
            name = parsed.value(subject, _term("name"))
            assert (None if name is None else str(name)) == node.name
            body = parsed.value(subject, _term("body"))
            assert (None if body is None else str(body)) == node.body
        assert len(full.nodes) == len(list(graph.nodes()))

    def test_every_node_is_typed_and_addressed_once(self, small):
        for level in PRESETS:
            parsed = _parse(write_turtle(level_view(small, level)))
            addresses = list(parsed.subject_objects(_term("address")))
            assert len(addresses) == len(
                level_view(small, level).nodes)
            for subject, _ in addresses:
                assert len(list(parsed.objects(subject, RDF.type))) == 1


# ── The ontology ──────────────────────────────────────────────

def _fields() -> list[dataclasses.Field]:
    """The fields of a node that Turtle writes as literals: all but its
    kind, which is its class."""
    return [f for f in dataclasses.fields(ViewNode) if f.name != "kind"]


def _datatypes() -> dict[str, URIRef]:
    """The datatype property of each literal the writer writes, from the
    type of the field it is: an integer or a string."""
    found = {turtle_field_name(f.name): (
        XSD.integer if "int" in str(f.type) else XSD.string)
        for f in _fields()}
    found["lines"] = XSD.integer
    return found


def _used(graphs) -> set[URIRef]:
    """Every class and predicate the writer writes in the namespace, at
    every level of every graph of *graphs*."""
    used = set()
    for graph in graphs:
        for level in PRESETS:
            for s, p, o in _parse(write_turtle(level_view(graph, level))):
                for term in (p, o):
                    if isinstance(term, URIRef) and str(term).startswith(NS):
                        used.add(term)
    return used


class TestOntology:
    def test_parses_and_is_declared(self):
        assert (URIRef(NS), RDF.type, OWL.Ontology) in _ontology()

    def test_says_the_namespace_is_informal(self):
        text = ONTOLOGY.read_text(encoding="utf-8")
        assert "informal" in text.lower()

    def test_classes_are_exactly_the_node_kinds(self):
        g = _ontology()
        classes = {str(s)[len(NS):] for s in g.subjects(RDF.type, OWL.Class)
                   if str(s).startswith(NS)}
        assert classes == {turtle_class_name(k) for k in NodeKind} | {"Node"}

    def test_every_kind_class_is_a_subclass_of_node(self):
        g = _ontology()
        for kind in NodeKind:
            cls = _term(turtle_class_name(kind))
            assert (cls, RDFS.subClassOf, _term("Node")) in g

    def test_object_properties_are_the_edge_kinds(self):
        g = _ontology()
        props = {str(s)[len(NS):]
                 for s in g.subjects(RDF.type, OWL.ObjectProperty)}
        assert props == {turtle_field_name(k.name) for k in EdgeKind}

    def test_edge_properties_join_nodes(self):
        g = _ontology()
        node = _term("Node")
        for kind in EdgeKind:
            prop = _term(turtle_field_name(kind.name))
            assert (prop, RDFS.domain, node) in g
            assert (prop, RDFS.range, node) in g

    def test_datatype_properties_are_the_fields_a_node_carries(self):
        g = _ontology()
        props = {str(s)[len(NS):]
                 for s in g.subjects(RDF.type, OWL.DatatypeProperty)}
        assert props == set(_datatypes())
        for name, datatype in _datatypes().items():
            assert (_term(name), RDFS.range, datatype) in g, name

    def test_lines_are_said_of_a_statement(self):
        assert (_term("lines"), RDFS.domain, RDF.Statement) in _ontology()

    def test_every_term_has_a_label_and_a_comment(self):
        g = _ontology()
        for s in set(g.subjects()):
            if isinstance(s, URIRef) and str(s).startswith(NS):
                assert g.value(s, RDFS.label), s
                assert g.value(s, RDFS.comment), s

    @pytest.mark.parametrize("gone", [
        "size", "text", "ref", "sub", "uses_external", "defines", "prose",
        "code",
    ])
    def test_what_the_writer_no_longer_writes_is_not_declared(self, gone):
        assert (_term(gone), RDF.type, None) not in _ontology()

    def test_the_writer_writes_only_declared_terms(self, everything):
        """Drift guard: anything the writer can say is in the ontology, at
        every level of every example."""
        declared = {s for s in _ontology().subjects() if isinstance(
            s, URIRef) and str(s).startswith(NS)}
        used = _used(everything)
        assert used  # guard
        assert used <= declared, used - declared

    def test_nothing_is_declared_that_the_writer_never_writes(
        self, everything,
    ):
        """And each class and predicate the ontology declares is written
        somewhere, at some level of some example."""
        declared = {s for s in _ontology().subjects() if isinstance(
            s, URIRef) and str(s).startswith(NS)}
        # The ontology itself, and the superclass, are never written.
        declared -= {URIRef(NS), _term("Node")}
        used = _used(everything)
        assert declared <= used, declared - used


class TestTheLayerIsGone:
    def test_there_is_no_defines_edge_kind(self):
        assert "DEFINES" not in EdgeKind.__members__

    def test_a_node_has_no_content(self):
        assert "content" not in {
            f.name for f in dataclasses.fields(notlob.Node)}

    def test_graph_has_no_content_option(self):
        assert "include_content" not in inspect.signature(
            cmd_graph).parameters
