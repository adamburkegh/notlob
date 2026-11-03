"""The organising abstraction, held to what ``notlob graph`` writes.

These are the lines at the top of ``DESIGN.md`` as a program sees them,
against the target, ``notlob/schema/name_graph_next.json``: a document is
a tree of nodes; each written line of a file is in one node's body; every
node of a kind has one rank, so a kind shows whole or not at all; each
level holds the one before, and a ``CONTAINS`` edge is the tree's, with
``CONTAINS_INDIRECTLY`` where a view hides what lies between; a
reference starts at the nearest node an
``outline`` shows; and a formatter writes the view it is given. They
test the output, not the code, and they name no rank: which kinds show
at which level is defined once, in ``notlob/graph.py``.

Until the swap, ``_output`` runs ``notlob.graph_next``, the view and its
writers beside the old path; the swap points it back at ``notlob
graph``. Each first holds the document to the target schema.
``_output`` is the one place they run notlob. The text format is held
only to being the same each time: a reader's outline has no parser here.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from functools import cache
from pathlib import Path

import jsonschema
import pytest
import rdflib

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"
SCHEMA = json.loads((ROOT / "notlob" / "schema" / "name_graph_next.json")
                    .read_text(encoding="utf-8"))
LEVELS = ("outline", "index", "block", "full")
NS = "urn:notlob:ns:"
TREE = ("CONTAINS", "CONTAINS_INDIRECTLY")

# ── A small project, for what the examples lack ──────────────

GREETER = """\
#Greeter

    def greet(name):
        return 'Hello, ' + name

---

#Binding
    ~language python
    ~external data.txt
"""

HELLO = """\
#Hello

The greeting is in #Usage, and its words are greet's.

* short
* polite

    def welcome(name):
        return greet(name) + '!'

~run on-load
    welcome('world')

##Usage

    def shout(name):
        return welcome(name).upper()

~example
    shout('a') == 'HELLO, A!'

---

#Tests

##welcoming
    welcome('a') == 'Hello, a!'

~test welcome_b
    welcome('b') == 'Hello, b!'

#References
    #Greeter

#Appendix Glossary

A greeting is what greet returns.

#Appendix

Notes, with no title.
"""

SMALL = {"binding.lob": GREETER, "hello.lob": HELLO, "data.txt": "x\n"}


def _line(text: str, words: str) -> int:
    """The number of the one line of *text* that holds *words*."""
    found = [n for n, line in enumerate(text.split("\n"), 1)
             if words in line]
    assert len(found) == 1, (words, found)
    return found[0]


@pytest.fixture(scope="session")
def small(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("small")
    for name, text in SMALL.items():
        (root / name).write_text(text, encoding="utf-8")
    return root


@pytest.fixture(params=["gutenberg", "haskell-roman", "retail", "roman",
                        "ts-media", "small"])
def root(request, small) -> Path:
    if request.param == "small":
        return small
    return EXAMPLES / request.param


@pytest.fixture(params=LEVELS)
def level(request) -> str:
    return request.param


# ── What notlob writes ───────────────────────────────────────

@cache
def _output(root: Path, fmt: str, level: str, seed: str = "0") -> str:
    """What the writers write for the project at *root*."""
    done = subprocess.run(
        [sys.executable, "-c",
         "from notlob.graph_next import main; main()",
         str(root), fmt, level],
        capture_output=True, encoding="utf-8",
        env={**os.environ, "PYTHONHASHSEED": seed})
    assert done.returncode == 0, done.stderr
    return done.stdout


def _document(root: Path, level: str) -> dict:
    """The JSON document, which every test holds to the target first."""
    doc = json.loads(_output(root, "json", level))
    jsonschema.validate(doc, SCHEMA)
    return doc


def _addresses(doc: dict) -> list[str]:
    return [n["address"] for n in doc["nodes"]]


def _contains(doc: dict) -> dict[str, list[str]]:
    """Each node's children, directly or not, in the order of the edges."""
    children: dict[str, list[str]] = {}
    for edge in doc["edges"]:
        if edge["kind"] in TREE:
            children.setdefault(edge["source"], []).append(edge["target"])
    return children


def _references(doc: dict) -> dict[tuple[str, str, str], dict]:
    found: dict[tuple[str, str, str], dict] = {}
    for edge in doc["edges"]:
        if edge["kind"] not in TREE:
            key =(edge["source"], edge["target"], edge["kind"])
            assert key not in found, f"two edges for {key}"
            found[key] = edge
    return found


def _below(doc: dict, address: str) -> list[dict]:
    """The node at *address* and every node under it, as written."""
    nodes = {n["address"]: n for n in doc["nodes"]}
    children = _contains(doc)
    found: list[dict] = []

    def walk(at: str) -> None:
        found.append(nodes[at])
        for child in children.get(at, []):
            walk(child)

    walk(address)
    return found


# ── A tree of nodes ──────────────────────────────────────────

class TestTheDocument:
    def test_each_edge_joins_two_of_its_nodes(self, root, level):
        doc = _document(root, level)
        shown = set(_addresses(doc))
        for edge in doc["edges"]:
            assert {edge["source"], edge["target"]} <= shown, edge

    def test_its_nodes_are_a_walk_of_its_trees(self, root, level):
        doc = _document(root, level)
        walked = [n["address"]
                  for top in doc["nodes"]
                  if top["kind"] in ("MODULE", "EXTERNAL")
                  for n in _below(doc, top["address"])]
        assert walked == _addresses(doc)


# ── Each line in one body ────────────────────────────────────

class TestTheBodies:
    def test_the_bodies_of_a_file_are_the_file(self, root):
        doc = _document(root, "full")
        for module in doc["nodes"]:
            if module["kind"] != "MODULE":
                continue
            placed: dict[int, str] = {}
            for node in _below(doc, module["address"]):
                lines = node["body"].split("\n") if "body" in node else []
                for number, text in enumerate(lines, node.get("start_line")):
                    assert number not in placed, (node["address"], number)
                    placed[number] = text
            file = module["file"]
            written = (root / file).read_text(encoding="utf-8")
            for number, text in enumerate(written.split("\n"), 1):
                held = placed.pop(number, None)
                if held is None:
                    assert not text.strip(), f"{file}:{number} in no body"
                else:
                    assert held == text, f"{file}:{number}"
            assert not placed, f"a body in {file} runs past its end"

    def test_only_a_derived_node_has_none(self, root):
        for node in _document(root, "full")["nodes"]:
            derived = node["kind"] in ("SYMBOL", "EXTERNAL")
            assert ("body" in node) != derived, node["address"]

    @pytest.mark.parametrize("before", LEVELS[:-1])
    def test_no_level_before_full_has_them(self, root, before):
        nodes = _document(root, before)["nodes"]
        assert not [n for n in nodes if "body" in n]


# ── One rank for each kind, and levels that nest ─────────────

class TestRank:
    def test_a_kind_shows_whole_or_not_at_all(self, root, level):
        def count(doc: dict) -> dict[str, int]:
            kinds: dict[str, int] = {}
            for node in doc["nodes"]:
                kinds[node["kind"]] = kinds.get(node["kind"], 0) + 1
            return kinds

        every = count(_document(root, "full"))
        for kind, n in count(_document(root, level)).items():
            assert n == every[kind], kind

    def test_each_level_holds_the_nodes_of_the_one_before(self, root):
        held = [set(_addresses(_document(root, lv))) for lv in LEVELS]
        for before, after in zip(held, held[1:]):
            assert before <= after

    def test_full_adds_bodies_not_nodes(self, root):
        assert (_addresses(_document(root, "block"))
                == _addresses(_document(root, "full")))


# ── CONTAINS is the tree's, CONTAINS_INDIRECTLY the view's ───

class TestContainment:
    def test_block_writes_the_tree_alone(self, root):
        kinds = {e["kind"] for e in _document(root, "block")["edges"]}
        assert "CONTAINS_INDIRECTLY" not in kinds

    def test_each_level_holds_the_edges_of_the_one_before(self, root):
        def edges(level: str) -> set[tuple[str, str, str]]:
            return {(e["source"], e["target"], e["kind"])
                    for e in _document(root, level)["edges"]
                    if e["kind"] != "CONTAINS_INDIRECTLY"}

        held = [edges(lv) for lv in LEVELS]
        for before, after in zip(held, held[1:]):
            assert before <= after

    def test_an_indirect_edge_passes_only_what_its_level_hides(
        self, root, level,
    ):
        doc = _document(root, level)
        shown = set(_addresses(doc))
        parent = {e["target"]: e["source"]
                  for e in _document(root, "block")["edges"]
                  if e["kind"] == "CONTAINS"}
        for edge in doc["edges"]:
            if edge["kind"] != "CONTAINS_INDIRECTLY":
                continue
            between, above = [], parent[edge["target"]]
            while above != edge["source"]:
                between.append(above)
                above = parent[above]
            assert between and not shown.intersection(between), edge


# ── References are edges from what an outline shows ──────────

class TestReferences:
    def test_an_outline_has_none(self, root):
        assert not _references(_document(root, "outline"))

    def test_each_level_after_has_the_same(self, root):
        found = [_references(_document(root, lv)) for lv in LEVELS[1:]]
        assert found[0] == found[1] == found[2]

    def test_each_starts_at_a_node_an_outline_shows(self, root, level):
        shown = set(_addresses(_document(root, "outline")))
        for source, _target, _kind in _references(_document(root, level)):
            assert source in shown, source

    def test_its_lines_are_in_order_once_each(self, root, level):
        for edge in _references(_document(root, level)).values():
            lines = edge.get("lines", [])
            assert lines == sorted(set(lines)), edge


# ── Names ────────────────────────────────────────────────────

class TestNames:
    def test_an_address_ends_in_its_name(self, root, level):
        for node in _document(root, level)["nodes"]:
            if "name" in node and node["kind"] != "MODULE":
                assert node["address"].rsplit("#", 1)[-1] == node["name"]


# ── A formatter writes the view ──────────────────────────────

def _camel(word: str) -> str:
    first, *rest = word.lower().split("_")
    return first + "".join(part.title() for part in rest)


class TestTurtle:
    """Turtle names a field as JSON does, in camelCase. An edge is a
    triple with its kind, in camelCase, for the predicate; one with lines
    also has an ``rdf:Statement`` about that triple, which carries them as
    ``notlob:lines``, one value a line (RDF 1.1 reification: Adam,
    2026-11-03)."""

    KINDS = {_camel(k): k for k in
             SCHEMA["definitions"]["GraphEdge"]["properties"]["kind"]["enum"]}

    def _read(self, root, level):
        g = rdflib.Graph()
        g.parse(data=_output(root, "turtle", level), format="turtle",
                publicID="http://example.test/")
        address = {s: str(o) for s, o in
                   g.subject_objects(rdflib.URIRef(NS + "address"))}
        return g, address

    def _kind(self, predicate) -> str | None:
        word = str(predicate)
        return (self.KINDS.get(word[len(NS):]) if word.startswith(NS)
                else None)

    def test_it_writes_the_same_nodes_and_bodies(self, root, level):
        doc = _document(root, level)
        g, address = self._read(root, level)
        assert sorted(address.values()) == sorted(_addresses(doc))
        body = {address[s]: str(o) for s, o in
                g.subject_objects(rdflib.URIRef(NS + "body"))}
        assert body == {n["address"]: n["body"]
                        for n in doc["nodes"] if "body" in n}

    def test_an_edge_is_a_triple(self, root, level):
        doc = _document(root, level)
        g, address = self._read(root, level)
        edges = {(address[s], address[o], self._kind(p))
                 for s, p, o in g if self._kind(p) and o in address}
        assert edges == {(e["source"], e["target"], e["kind"])
                         for e in doc["edges"]}

    def test_its_lines_are_said_of_the_triple(self, root, level):
        doc = _document(root, level)
        g, address = self._read(root, level)
        lines = {}
        for s in g.subjects(rdflib.RDF.type, rdflib.RDF.Statement):
            key = (address[g.value(s, rdflib.RDF.subject)],
                   address[g.value(s, rdflib.RDF.object)],
                   self._kind(g.value(s, rdflib.RDF.predicate)))
            assert key not in lines, key
            lines[key] = sorted(int(o) for o in g.objects(
                s, rdflib.URIRef(NS + "lines")))
        assert lines == {(e["source"], e["target"], e["kind"]): e["lines"]
                         for e in doc["edges"] if "lines" in e}


# ── The same project gives the same document ─────────────────

@pytest.mark.parametrize("fmt", ["text", "json", "turtle"])
def test_it_is_the_same_each_time(root, fmt):
    assert (_output(root, fmt, "full", seed="0")
            == _output(root, fmt, "full", seed="1"))


# ── The small project's own cases ────────────────────────────

class TestTheSmallProject:
    def test_an_appendix_is_named_by_its_title(self, small):
        shown = set(_addresses(_document(small, "outline")))
        assert {"hello#Glossary", "hello#Appendix"} <= shown

    def test_post_text_references_start_at_their_section(self, small):
        found = _references(_document(small, "index"))
        assert ("hello#References", "greeter", "IMPORTS") in found
        assert [key for key in found if key[2] == "USES_EXTERNAL"] == [
            ("greeter#Binding", "data.txt", "USES_EXTERNAL")]

    def test_a_call_starts_at_its_symbol_with_its_lines(self, small):
        found = _references(_document(small, "index"))
        uses = found["hello#welcome", "greeter#greet", "USES"]
        assert uses["lines"] == [_line(HELLO, "return greet(name)")]

    def test_a_citation_starts_at_its_section(self, small):
        found = _references(_document(small, "index"))
        cites = found["hello", "hello#Usage", "CITES"]
        assert cites["lines"] == [_line(HELLO, "is in #Usage")]

    def test_a_named_test_shows_in_an_outline_and_its_lines_do_not(
        self, small,
    ):
        doc = _document(small, "outline")
        named = [n for n in doc["nodes"] if n.get("name") == "welcome_b"]
        assert len(named) == 1
        group = [n for n in doc["nodes"] if n.get("name") == "welcoming"]
        assert [n for n in _below(doc, group[0]["address"])
                if "name" not in n] == []
