"""The Turtle export (``notlob graph --format turtle``) and its ontology.

The vocabulary lives in ``notlob/schema/notlob.ttl`` under the informal
``urn:notlob:ns:`` namespace. These tests parse real output with rdflib
(the Turtle equivalent of validating JSON against its schema), check the
ontology covers exactly what the emitter can say, and check the few
constraints that matter (each node typed and labelled once, edges join
typed nodes). Plan and decisions:
meta/features/2026-10-18-output-schemas/design.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import rdflib
from rdflib import RDF, RDFS, OWL, XSD, Literal, URIRef

import notlob
from notlob import EdgeKind, NodeKind, build, enrich, from_tree, parse
from notlob.bindings.python import extract_calls, extract_symbols
from notlob.graph import _turtle_iri, _turtle_lit, _turtle_long_lit
from notlob.project import build_package

NS = "urn:notlob:ns:"
ONTOLOGY = Path(notlob.__file__).parent / "schema" / "notlob.ttl"
# Relative IRIs resolve against this when a document is parsed.
DOC = "http://example.test/doc/"


def _graph(source: str):
    mod = from_tree(parse(source))
    g = build(mod)
    enrich(g, mod, extract_symbols)
    return g


def _parse(text: str) -> rdflib.Graph:
    g = rdflib.Graph()
    g.parse(data=text, format="turtle", publicID=DOC)
    return g


def _ontology() -> rdflib.Graph:
    g = rdflib.Graph()
    g.parse(ONTOLOGY, format="turtle")
    return g


@pytest.fixture
def project_graph(tmp_path):
    """A real multi-module graph: imports, uses and references edges,
    bullets, claims and prose."""
    (tmp_path / "binding.lob").write_text(
        "#T\n\n---\n\n#Binding\n    ~language python\n", encoding="utf-8")
    (tmp_path / "alpha.lob").write_text(
        "#Alpha\n\nAn intro.\n\n* one\n* two\n\n"
        "    def helper():\n        return 1\n\n"
        "    def caller():\n        return helper()\n\n"
        "~example\n    caller() == 1\n", encoding="utf-8")
    (tmp_path / "beta.lob").write_text(
        "#Beta\n\nBuilds on #Alpha.\n\n"
        "    def use_it():\n        return caller()\n\n"
        "---\n\n#References\n    #Alpha\n", encoding="utf-8")
    return build_package(tmp_path, extract_symbols,
                         call_extractor=extract_calls)


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


# ── Real output ───────────────────────────────────────────────

class TestEmittedTurtle:
    def test_parses_with_and_without_content(self, project_graph):
        _parse(project_graph.to_turtle())
        _parse(project_graph.to_turtle(include_content=True))

    @pytest.mark.parametrize("source", [
        '#Plain\n\nText.\n',
        '#Quote\n\n##Say "hi" now\n\nText "ending in a quote"\n',
        '#Angle\n\n##A <b> tag\n\nBody.\n',
        '#Hash\n\n##C# notes\n\nBody.\n',
        '#Percent\n\n##100% done\n\nBody.\n',
        '#Foo: Bar\n\nBody.\n',
        '#Braces\n\n##Set {a|b}\n\nBody.\n',
        '#Unicode\n\n##日本語 Notes\n\nBody.\n',
        '#Backslash\n\nPath C:\\dir and "quotes".\n',
    ])
    def test_awkward_titles_and_prose_parse_and_round_trip(self, source):
        graph = _graph(source)
        text = graph.to_turtle(include_content=True)
        parsed = _parse(text)
        by_address = {
            str(o): s for s, o in parsed.subject_objects(
                URIRef(NS + "address"))}
        checked = 0
        for node in graph.nodes():
            assert node.address in by_address, node.address
            subject = by_address[node.address]
            assert str(parsed.value(subject, RDFS.label)) == node.label
            prose = graph.prose(node.address)
            if prose:
                checked += 1
                assert str(parsed.value(
                    subject, URIRef(NS + "prose"))) == prose
        assert checked, "no node had prose, so nothing was compared"

    def test_every_iri_is_valid_in_the_ways_that_matter(self, project_graph):
        parsed = _parse(project_graph.to_turtle(include_content=True))
        for s, _p, o in parsed:
            for term in (s, o):
                if isinstance(term, URIRef) and not str(term).startswith(
                        ("urn:notlob:ns:", DOC.rstrip("/"))):
                    continue
                if isinstance(term, URIRef) and str(term).startswith(DOC):
                    assert str(term).count("#") <= 1, term


class TestNamespaceAndBase:
    def test_vocabulary_is_the_urn_namespace(self, project_graph):
        text = project_graph.to_turtle()
        assert f"@prefix notlob: <{NS}> ." in text
        assert "notlob.dev" not in text

    def test_no_base_unless_given(self, project_graph):
        assert "@base" not in project_graph.to_turtle()

    def test_base_is_emitted_when_given(self, project_graph):
        text = project_graph.to_turtle(base="http://example.test/p/")
        assert "@base <http://example.test/p/> ." in text
        parsed = rdflib.Graph()
        parsed.parse(data=text, format="turtle")
        assert any(str(s).startswith("http://example.test/p/")
                   for s in parsed.subjects())


class TestGraphFidelity:
    def _address_of(self, parsed):
        return {s: str(o) for s, o in parsed.subject_objects(
            URIRef(NS + "address"))}

    def test_every_node_is_typed_labelled_and_addressed_once(
        self, project_graph,
    ):
        parsed = _parse(project_graph.to_turtle())
        addr = self._address_of(parsed)
        assert len(addr) == len(project_graph)
        for subject in addr:
            assert len(list(parsed.objects(subject, RDF.type))) == 1
            assert len(list(parsed.objects(subject, RDFS.label))) == 1
            assert len(list(parsed.objects(
                subject, URIRef(NS + "address")))) == 1

    def test_node_kinds_map_to_classes(self, project_graph):
        parsed = _parse(project_graph.to_turtle())
        addr = self._address_of(parsed)
        want = {n.address: URIRef(NS + n.kind.name.capitalize())
                for n in project_graph.nodes()}
        got = {addr[s]: parsed.value(s, RDF.type) for s in addr}
        assert got == want

    def test_edges_are_exactly_the_graphs_edges(self, project_graph):
        parsed = _parse(project_graph.to_turtle())
        addr = self._address_of(parsed)
        kinds = {k.name.lower() for k in EdgeKind}
        got = set()
        for s, p, o in parsed:
            local = str(p)[len(NS):] if str(p).startswith(NS) else None
            if local in kinds:
                got.add((addr[s], local, addr[o]))
        want = {(e["source"], e["kind"].lower(), e["target"])
                for e in project_graph.to_dict()["edges"]}
        assert got == want
        assert got  # guard: the project does have edges

    def test_edge_endpoints_are_typed_nodes(self, project_graph):
        parsed = _parse(project_graph.to_turtle())
        addr = self._address_of(parsed)
        for s, p, o in parsed:
            if str(p).startswith(NS) and str(p)[len(NS):] in {
                    k.name.lower() for k in EdgeKind}:
                assert s in addr and o in addr


# ── The ontology ──────────────────────────────────────────────

class TestOntology:
    def test_parses_and_is_declared(self):
        g = _ontology()
        assert (URIRef(NS), RDF.type, OWL.Ontology) in g

    def test_says_the_namespace_is_informal(self):
        text = ONTOLOGY.read_text(encoding="utf-8")
        assert "informal" in text.lower()

    def test_classes_are_exactly_the_node_kinds(self):
        g = _ontology()
        classes = {str(s)[len(NS):] for s in g.subjects(RDF.type, OWL.Class)
                   if str(s).startswith(NS)}
        assert classes == {k.name.capitalize() for k in NodeKind} | {"Node"}

    def test_every_kind_class_is_a_subclass_of_node(self):
        g = _ontology()
        for kind in NodeKind:
            cls = URIRef(NS + kind.name.capitalize())
            assert (cls, RDFS.subClassOf, URIRef(NS + "Node")) in g

    def test_object_properties_are_exactly_the_edge_kinds(self):
        g = _ontology()
        props = {str(s)[len(NS):]
                 for s in g.subjects(RDF.type, OWL.ObjectProperty)}
        assert props == {k.name.lower() for k in EdgeKind}

    def test_edge_properties_join_nodes(self):
        g = _ontology()
        node = URIRef(NS + "Node")
        for kind in EdgeKind:
            prop = URIRef(NS + kind.name.lower())
            assert (prop, RDFS.domain, node) in g
            assert (prop, RDFS.range, node) in g

    def test_datatype_properties(self):
        g = _ontology()
        props = {str(s)[len(NS):]
                 for s in g.subjects(RDF.type, OWL.DatatypeProperty)}
        assert props == {"address", "startLine", "prose", "code"}
        assert (URIRef(NS + "startLine"), RDFS.range, XSD.integer) in g
        assert (URIRef(NS + "address"), RDFS.range, XSD.string) in g

    def test_every_term_has_a_label_and_a_comment(self):
        g = _ontology()
        for s in set(g.subjects()):
            if isinstance(s, URIRef) and str(s).startswith(NS):
                assert g.value(s, RDFS.label), s
                assert g.value(s, RDFS.comment), s

    def test_emitter_uses_only_declared_terms(self, project_graph):
        """Drift guard: anything the emitter can say is in the ontology."""
        declared = {s for s in _ontology().subjects() if isinstance(
            s, URIRef) and str(s).startswith(NS)}
        parsed = _parse(project_graph.to_turtle(include_content=True))
        used = set()
        for s, p, o in parsed:
            for term in (p, o):
                if isinstance(term, URIRef) and str(term).startswith(NS):
                    used.add(term)
        assert used  # guard
        assert used <= declared, used - declared
