"""The Turtle export (``notlob graph --format turtle``) and its ontology.

The vocabulary lives in ``notlob/schema/notlob.ttl`` under the informal
``urn:notlob:ns:`` namespace. Turtle comes at the same three levels as the
JSON document and writes the same nodes and edges. These tests parse real
output with rdflib (the Turtle equivalent of validating JSON against its
schema), check it agrees with the JSON at each level, check the ontology
declares exactly what the emitter writes, and check the few constraints
that matter (each node typed and labelled once, edges join typed nodes).
Plan and decisions: meta/features/2026-10-18-output-schemas/design.md.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import re
from pathlib import Path

import pytest
import rdflib
from rdflib import RDF, RDFS, OWL, XSD, URIRef

import notlob
import notlob.graph as graph_module
from notlob import (
    Edge, EdgeKind, Node, NodeKind, build, enrich, from_tree, parse,
    parse_file,
)
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import (
    extract_calls, extract_symbols, kit as python_kit,
)
from notlob.bindings.typescript import kit as typescript_kit
from notlob.commands import cmd_graph
from notlob.graph import (
    LEVELS, _turtle_iri, _turtle_lit, _turtle_long_lit, add_references_edges,
    add_uses_edges, turtle_class_name,
)
from notlob.project import build_package

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


def _term(name: str) -> URIRef:
    return URIRef(NS + name)


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


#: A source with a node of every kind but an external file, a reference
#: and a named node of each sort.
_EVERYTHING = (
    "#M\n\n"
    "Intro, see #Sec and ##Sec.\n\n"
    "* one\n* two\n\n"
    "    def f():\n        return 1\n\n"
    "~example\n    f() == 1\n\n"
    "~property p\n    @given()\n    def prop(n):\n        pass\n\n"
    "~run on-load\n    boot()\n\n"
    "##Sec\n\nSection text.\n\n    def g():\n        return f()\n\n"
    "---\n\n#Tests\n\n    f() == 1\n\nCommentary.\n\n"
    "##grp\n    g() == 1\n\n~test nm\n    g() == 1\n\n"
    "#Appendix Notes\n\nAppendix text.\n"
)


def _everything_graph():
    """A graph with every kind of node and edge."""
    module = from_tree(parse(_EVERYTHING))
    graph = build(module, "m.lob")
    enrich(graph, module, extract_symbols)
    add_references_edges(graph)
    add_uses_edges(graph, extract_calls)
    graph.add_node(Node(address="index.html", label="index.html",
                        kind=NodeKind.EXTERNAL))
    graph.add_node(Node(address="n", label="N", kind=NodeKind.MODULE))
    graph.add_edge(Edge(source="m", target="n", kind=EdgeKind.IMPORTS))
    graph.add_edge(Edge(source="n", target="index.html",
                        kind=EdgeKind.USES_EXTERNAL))
    return graph


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


class TestClassNames:
    @pytest.mark.parametrize("kind,name", [
        (NodeKind.MODULE, "Module"), (NodeKind.POST_TEXT, "PostText"),
        (NodeKind.TEST_GROUP, "TestGroup"), (NodeKind.TESTS, "Tests"),
    ])
    def test_upper_camel_case(self, kind, name):
        assert turtle_class_name(kind) == name

    def test_every_kind_has_one(self):
        names = [turtle_class_name(k) for k in NodeKind]
        assert len(set(names)) == len(NodeKind)
        assert all(re.fullmatch(r"[A-Z][A-Za-z]*", n) for n in names)


# ── Real output ───────────────────────────────────────────────

class TestEmittedTurtle:
    @pytest.mark.parametrize("level", LEVELS)
    def test_parses_at_every_level(self, project_graph, level):
        _parse(project_graph.to_turtle(level=level))

    def test_the_default_is_the_outline(self, project_graph):
        assert project_graph.to_turtle() == project_graph.to_turtle(
            level="outline")

    def test_a_level_by_number_is_the_level_by_name(self, project_graph):
        for number, name in enumerate(LEVELS, 1):
            assert project_graph.to_turtle(level=number) == (
                project_graph.to_turtle(level=name))

    def test_an_unknown_level_is_an_error(self, project_graph):
        with pytest.raises(ValueError):
            project_graph.to_turtle(level="detail")

    def test_the_example_node_as_documented(self):
        text = _graph(
            "#T\n    def to_roman(n):\n        return n\n"
        ).to_turtle()
        assert (
            "<t#to_roman> a notlob:Symbol ;\n"
            '    rdfs:label "to_roman" ;\n'
            '    notlob:address "t#to_roman" ;\n'
            "    notlob:startLine 2 ;\n"
            "    notlob:endLine 3 ."
        ) in text

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
        parsed = _parse(graph.to_turtle(level="full"))
        by_address = {
            str(o): s for s, o in parsed.subject_objects(
                _term("address"))}
        for node in graph.nodes():
            assert node.address in by_address, node.address
            subject = by_address[node.address]
            assert str(parsed.value(subject, RDFS.label)) == node.label
            if node.kind == NodeKind.PROSE:
                assert str(parsed.value(subject, _term("text"))) == (
                    node.text)

    def test_every_iri_is_valid_in_the_ways_that_matter(self, project_graph):
        parsed = _parse(project_graph.to_turtle(level="full"))
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


# ── The same nodes and edges as the JSON ──────────────────────

def _agreement(graph, level: str) -> None:
    """The Turtle of *graph* at *level* says what the JSON does."""
    doc = graph.to_dict(level=level)
    parsed = _parse(graph.to_turtle(level=level))
    subjects = {str(o): s for s, o in parsed.subject_objects(
        _term("address"))}
    assert set(subjects) == {n["address"] for n in doc["nodes"]}
    for node in doc["nodes"]:
        subject = subjects[node["address"]]
        words = [w.capitalize() for w in node["kind"].split("_")]
        assert parsed.value(subject, RDF.type) == _term("".join(words))
        assert str(parsed.value(subject, RDFS.label)) == node["label"]
        for field, prop in (
                ("file", "file"), ("start_line", "startLine"),
                ("end_line", "endLine"), ("size", "size"),
                ("mode", "mode"), ("text", "text"), ("named", "named")):
            value = parsed.value(subject, _term(prop))
            if field in node:
                assert value is not None, (node["address"], field)
                assert value.toPython() == node[field], (
                    node["address"], field)
            else:
                assert value is None, (node["address"], field)
        written = sorted(
            (str(parsed.value(ref, RDFS.label)),
             parsed.value(ref, _term("sub")).toPython(),
             getattr(parsed.value(ref, _term("startLine")), "value", None))
            for ref in parsed.objects(subject, _term("ref")))
        held = sorted((r["label"], r["sub"], r["start_line"])
                      for r in node.get("refs", []))
        assert written == held, node["address"]
    kinds = {k.name.lower() for k in EdgeKind}
    edges = set()
    for s, p, o in parsed:
        local = str(p)[len(NS):] if str(p).startswith(NS) else None
        if local in kinds:
            edges.add((str(parsed.value(s, _term("address"))), local,
                       str(parsed.value(o, _term("address")))))
    assert edges == {(e["source"], e["kind"].lower(), e["target"])
                     for e in doc["edges"]}


@pytest.mark.parametrize("level", LEVELS)
class TestAgreesWithTheJson:
    def test_a_small_project(self, project_graph, level):
        _agreement(project_graph, level)

    def test_every_kind_of_node_and_edge(self, level):
        _agreement(_everything_graph(), level)

    @pytest.mark.parametrize("name,kit", _PROJECTS,
                             ids=[p[0] for p in _PROJECTS])
    def test_every_example_project(self, name, kit, level):
        graph = build_package(
            EXAMPLES / name, kit.extract_symbols,
            call_extractor=kit.extract_calls)
        _agreement(graph, level)


class TestWhatIsWritten:
    def test_outline_lifts_a_symbols_containment_to_its_section(self):
        parsed = _parse(_graph(
            "#T\n\n##S\n\n    def f(): pass\n").to_turtle())
        subjects = {str(o): s for s, o in parsed.subject_objects(
            _term("address"))}
        assert (subjects["t#S"], _term("contains"),
                subjects["t#f"]) in parsed
        assert "t#S#code#1" not in subjects

    def test_index_has_the_leaf_and_its_references_as_a_blank_node(self):
        graph = _graph("#T\n\nSee #S.\n\n##S\n")
        parsed = _parse(graph.to_turtle(level="index"))
        leaf = next(parsed.subjects(_term("address"),
                                    rdflib.Literal("t#prose#1")))
        (ref,) = parsed.objects(leaf, _term("ref"))
        assert isinstance(ref, rdflib.BNode)
        assert str(parsed.value(ref, RDFS.label)) == "S"
        assert parsed.value(ref, _term("sub")).toPython() is False
        assert parsed.value(ref, _term("startLine")).toPython() == 3

    def test_text_only_at_full(self):
        graph = _graph("#T\n\nSome text.\n")
        assert not list(_parse(graph.to_turtle(level="index")).triples(
            (None, _term("text"), None)))
        assert list(_parse(graph.to_turtle(level="full")).triples(
            (None, _term("text"), None)))

    def test_named_and_mode(self):
        graph = _graph("#T\n\n##S\n\n~run on-load\n    boot()\n")
        parsed = _parse(graph.to_turtle())
        named = {str(parsed.value(s, _term("address")))
                 for s in parsed.subjects(_term("named"), None)}
        assert named == {"t#S"}
        (run,) = parsed.subjects(_term("mode"), None)
        assert str(parsed.value(run, _term("mode"))) == "on-load"

    def test_there_is_no_defines_prose_or_code(self, project_graph):
        text = project_graph.to_turtle(level="full")
        for gone in ("notlob:defines", "notlob:prose", "notlob:code"):
            assert gone not in text


class TestGraphFidelity:
    def _address_of(self, parsed):
        return {s: str(o) for s, o in parsed.subject_objects(
            _term("address"))}

    @pytest.mark.parametrize("level", LEVELS)
    def test_every_node_is_typed_labelled_and_addressed_once(
        self, project_graph, level,
    ):
        parsed = _parse(project_graph.to_turtle(level=level))
        addr = self._address_of(parsed)
        assert len(addr) == len(project_graph.to_dict(level=level)["nodes"])
        for subject in addr:
            assert len(list(parsed.objects(subject, RDF.type))) == 1
            assert len(list(parsed.objects(subject, RDFS.label))) == 1
            assert len(list(parsed.objects(subject, _term("address")))) == 1

    @pytest.mark.parametrize("level", LEVELS)
    def test_edge_endpoints_are_typed_nodes(self, project_graph, level):
        parsed = _parse(project_graph.to_turtle(level=level))
        addr = self._address_of(parsed)
        kinds = {k.name.lower() for k in EdgeKind}
        for s, p, o in parsed:
            if str(p).startswith(NS) and str(p)[len(NS):] in kinds:
                assert s in addr and o in addr


# ── The ontology ──────────────────────────────────────────────

_DATATYPES = {
    "address": XSD.string, "file": XSD.string, "startLine": XSD.integer,
    "endLine": XSD.integer, "named": XSD.boolean, "mode": XSD.string,
    "size": XSD.integer, "text": XSD.string, "sub": XSD.boolean,
}


def _used_terms(graph) -> set[URIRef]:
    used = set()
    for level in LEVELS:
        for s, p, o in _parse(graph.to_turtle(level=level)):
            for term in (p, o):
                if isinstance(term, URIRef) and str(term).startswith(NS):
                    used.add(term)
    return used


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
        assert classes == {turtle_class_name(k) for k in NodeKind} | {"Node"}

    def test_every_kind_class_is_a_subclass_of_node(self):
        g = _ontology()
        for kind in NodeKind:
            cls = _term(turtle_class_name(kind))
            assert (cls, RDFS.subClassOf, _term("Node")) in g

    def test_object_properties_are_the_edge_kinds_and_the_reference(self):
        g = _ontology()
        props = {str(s)[len(NS):]
                 for s in g.subjects(RDF.type, OWL.ObjectProperty)}
        assert props == {k.name.lower() for k in EdgeKind} | {"ref"}

    def test_edge_properties_join_nodes(self):
        g = _ontology()
        node = _term("Node")
        for kind in EdgeKind:
            prop = _term(kind.name.lower())
            assert (prop, RDFS.domain, node) in g
            assert (prop, RDFS.range, node) in g

    def test_datatype_properties(self):
        g = _ontology()
        props = {str(s)[len(NS):]
                 for s in g.subjects(RDF.type, OWL.DatatypeProperty)}
        assert props == set(_DATATYPES)
        for name, datatype in _DATATYPES.items():
            assert (_term(name), RDFS.range, datatype) in g, name

    def test_every_term_has_a_label_and_a_comment(self):
        g = _ontology()
        for s in set(g.subjects()):
            if isinstance(s, URIRef) and str(s).startswith(NS):
                assert g.value(s, RDFS.label), s
                assert g.value(s, RDFS.comment), s

    def test_defines_prose_and_code_are_gone(self):
        g = _ontology()
        for gone in ("defines", "prose", "code"):
            assert (_term(gone), RDF.type, None) not in g

    @pytest.mark.parametrize("where", ["project", "everything"])
    def test_emitter_uses_only_declared_terms(self, project_graph, where):
        """Drift guard: anything the emitter can say is in the ontology,
        at every level."""
        declared = {s for s in _ontology().subjects() if isinstance(
            s, URIRef) and str(s).startswith(NS)}
        graph = project_graph if where == "project" else (
            _everything_graph())
        used = _used_terms(graph)
        assert used  # guard
        assert used <= declared, used - declared

    def test_nothing_is_declared_that_the_emitter_never_writes(self):
        """Over a graph with every kind of node and edge, at every level,
        each class and property the ontology declares is written."""
        declared = {s for s in _ontology().subjects() if isinstance(
            s, URIRef) and str(s).startswith(NS)}
        # The ontology itself, and the superclass, are never written.
        declared -= {URIRef(NS), _term("Node")}
        used = _used_terms(_everything_graph())
        assert declared <= used, declared - used


# ── The layer is gone ─────────────────────────────────────────

class TestTheLayerIsGone:
    GONE = (
        "legacy_graph", "legacy_dict", "_legacy_content", "_print_node",
        "_print_tests", "_print_definitions", "_reference_holder",
        "_group_code", "_tests_code", "_printed_source", "_earliest_uses",
        "_node_content",
    )

    @pytest.mark.parametrize("name", GONE)
    def test_the_name_no_longer_exists(self, name):
        assert not hasattr(graph_module, name)

    def test_there_is_no_defines_edge_kind(self):
        assert "DEFINES" not in EdgeKind.__members__

    def test_a_node_has_no_content(self):
        assert "content" not in {
            f.name for f in dataclasses.fields(Node)}

    def test_a_graph_has_no_layer_flag(self):
        assert not hasattr(notlob.NameGraph(), "_legacy")

    def test_no_module_imports_it(self):
        offences = []
        for path in sorted(Path(notlob.__file__).parent.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text("utf-8"))):
                if isinstance(node, ast.ImportFrom):
                    names = [node.module or "", *(a.name for a in node.names)]
                elif isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                else:
                    continue
                if any("legacy" in name for name in names):
                    offences.append(f"{path.name}: {names}")
        assert offences == []

    def test_graph_has_no_content_option(self):
        assert "include_content" not in inspect.signature(
            cmd_graph).parameters
        assert "include_content" not in inspect.signature(
            notlob.NameGraph.to_turtle).parameters


class TestTheCommand:
    @pytest.mark.parametrize("level", LEVELS)
    def test_turtle_takes_a_level(self, tmp_path, capsys, level):
        path = tmp_path / "t.lob"
        path.write_text("#T\n\nSome text.\n    def f(): pass\n",
                        encoding="utf-8")
        assert cmd_graph(path, fmt="turtle", level=level) == 0
        out = capsys.readouterr().out
        assert out == _graph_text(path, level)

    def test_an_unknown_level_is_an_error_for_turtle_too(
        self, tmp_path, capsys,
    ):
        path = tmp_path / "t.lob"
        path.write_text("#T\n", encoding="utf-8")
        assert cmd_graph(path, fmt="turtle", level="detail") == 1
        assert "outline" in capsys.readouterr().err


def _graph_text(path: Path, level: str) -> str:
    module = from_tree(parse_file(path))
    graph = build(module)
    enrich(graph, module, extract_symbols)
    return graph.to_turtle(level=level) + "\n"
