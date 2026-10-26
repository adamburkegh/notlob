"""`notlob graph` prints the graph itself, at one of three levels.

`outline` is what is here and how it is connected: every node but the
anonymous leaves (paragraphs, code blocks, bullet lists), whose edges are
lifted to the section that holds them. `index` adds those leaves, the
references a paragraph holds, and a size for every node. `full` adds the
text of each node that holds text, once.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from notlob import (
    NodeKind, build, build_package, enrich, from_tree, parse,
)
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import extract_symbols, kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit
from notlob.graph import LEVELS, add_cites_edges, parse_level

EXAMPLES = Path(__file__).parent.parent / "examples"
SCHEMA = (
    Path(__file__).parent.parent / "notlob" / "schema" / "name_graph.json"
)

_LEAVES = {"PROSE", "CODE", "BULLETS", "LISTING", "IMPORT", "DECLARATION"}

#: A source with every kind of node in it.
_EVERYTHING = (
    "#M\n"                       # 1
    "\n"                         # 2
    "Intro, see #Sec and ##Sec.\n"  # 3
    "\n"                         # 4
    "* one\n"                    # 5
    "* two\n"                    # 6
    "\n"                         # 7
    "    def f():\n"             # 8
    "        return 1\n"         # 9
    "\n"                         # 10
    "~example\n"                 # 11
    "    f() == 1\n"             # 12
    "\n"                         # 13
    "~property p\n"              # 14
    "    @given()\n"             # 15
    "    def prop(n):\n"         # 16
    "        pass\n"             # 17
    "\n"                         # 18
    "~run on-load\n"             # 19
    "    boot()\n"               # 20
    "\n"                         # 21
    "##Sec\n"                    # 22
    "\n"                         # 23
    "Section text.\n"            # 24
    "\n"                         # 25
    "    def g():\n"             # 26
    "        return f()\n"       # 27
    "\n"                         # 28
    "---\n"                      # 29
    "\n"                         # 30
    "#Tests\n"                   # 31
    "\n"                         # 32
    "    f() == 1\n"             # 33
    "\n"                         # 34
    "Commentary.\n"              # 35
    "\n"                         # 36
    "##grp\n"                    # 37
    "    g() == 1\n"             # 38
    "\n"                         # 39
    "~test nm\n"                 # 40
    "    g() == 1\n"             # 41
    "\n"                         # 42
    "#Appendix Notes\n"          # 43
    "\n"                         # 44
    "Appendix text.\n"           # 45
)


def _graph(source: str):
    module = from_tree(parse(source))
    graph = build(module)
    enrich(graph, module, extract_symbols)
    add_cites_edges(graph)
    return graph


def _roman():
    from notlob import parse_file
    module = from_tree(parse_file(EXAMPLES / "roman/roman/numerals.lob"))
    graph = build(module, "roman/numerals.lob")
    enrich(graph, module, extract_symbols)
    return graph


_PROJECTS = [
    ("roman", python_kit), ("retail", python_kit),
    ("gutenberg", python_kit), ("haskell-roman", haskell_kit),
    ("ts-media", typescript_kit),
]


def _project(name, kit):
    return build_package(
        EXAMPLES / name, kit.extract_symbols,
        call_extractor=kit.extract_calls)


def _by_address(doc: dict) -> dict:
    return {n["address"]: n for n in doc["nodes"]}


class TestTheDocument:
    def test_it_says_its_version_and_level(self):
        for level in LEVELS:
            doc = _graph(_EVERYTHING).to_dict(level=level)
            assert doc["version"] == 2
            assert doc["level"] == level

    def test_the_default_is_the_outline(self):
        graph = _graph(_EVERYTHING)
        assert graph.to_dict() == graph.to_dict(level="outline")
        assert json.loads(graph.to_json())["level"] == "outline"

    def test_to_json_is_to_dict(self):
        graph = _graph(_EVERYTHING)
        for level in LEVELS:
            assert json.loads(graph.to_json(level=level)) == (
                graph.to_dict(level=level))

    def test_a_level_by_number_is_the_level_by_name(self):
        graph = _graph(_EVERYTHING)
        for number, name in enumerate(LEVELS, 1):
            assert graph.to_dict(level=number) == graph.to_dict(level=name)
            assert graph.to_dict(level=str(number)) == (
                graph.to_dict(level=name))

    @pytest.mark.parametrize("bad", ["detail", "0", 4, "", None])
    def test_an_unknown_level_names_the_choices(self, bad):
        with pytest.raises(ValueError) as raised:
            parse_level(bad)
        for choice in ("outline", "index", "full"):
            assert choice in str(raised.value)

    def test_no_defines_edges_and_no_content(self):
        for level in LEVELS:
            doc = _graph(_EVERYTHING).to_dict(level=level)
            assert "DEFINES" not in {e["kind"] for e in doc["edges"]}
            assert all("content" not in n for n in doc["nodes"])


class TestOutline:
    def test_every_node_but_the_anonymous_leaves(self):
        graph = _graph(_EVERYTHING)
        doc = graph.to_dict(level="outline")
        shown = {n.address for n in graph.nodes()
                 if n.kind.name not in _LEAVES}
        assert set(_by_address(doc)) == shown

    def test_the_kinds_it_shows(self):
        kinds = {n["kind"] for n in
                 _graph(_EVERYTHING).to_dict()["nodes"]}
        assert kinds == {
            "MODULE", "SUBHEADING", "SYMBOL", "EXAMPLE", "PROPERTY", "RUN",
            "POST_TEXT", "TESTS", "TEST_GROUP", "TEST", "APPENDIX"}

    def test_the_fields_of_a_node(self):
        nodes = _by_address(_graph(_EVERYTHING).to_dict())
        assert nodes["m#Sec"] == {
            "address": "m#Sec", "label": "Sec", "kind": "SUBHEADING",
            "named": True, "start_line": 22, "end_line": 27}
        assert nodes["m#f"]["start_line"] == 8
        assert nodes["m#f"]["end_line"] == 9

    def test_a_module_built_in_a_project_names_its_file(self):
        nodes = _by_address(_roman().to_dict())
        assert nodes["roman/numerals#to_roman"] == {
            "address": "roman/numerals#to_roman", "label": "to_roman",
            "kind": "SYMBOL", "file": "roman/numerals.lob",
            "start_line": 19, "end_line": 25}

    def test_named_is_where_the_document_gives_a_name(self):
        nodes = _by_address(_graph(_EVERYTHING).to_dict())
        assert nodes["m#p"]["named"] is True
        assert nodes["m#Tests#grp"]["named"] is True
        assert nodes["m#Tests#grp#nm"]["named"] is True
        assert "named" not in nodes["m#example#1"]
        assert "named" not in nodes["m#f"]
        assert "named" not in nodes["m#Tests#test#1"]

    def test_the_name_itself_is_never_printed_it_is_the_label(self):
        for level in LEVELS:
            doc = _graph(_EVERYTHING).to_dict(level=level)
            assert all("name" not in n for n in doc["nodes"])
        nodes = _by_address(_graph(_EVERYTHING).to_dict())
        assert nodes["m#p"]["label"] == "p"

    def test_a_run_has_its_mode_and_nothing_else_does(self):
        nodes = _by_address(_graph(_EVERYTHING).to_dict())
        assert nodes["m#run#1"]["mode"] == "on-load"
        assert [a for a, n in nodes.items() if "mode" in n] == ["m#run#1"]

    def test_nothing_it_leaves_out_is_there(self):
        for node in _graph(_EVERYTHING).to_dict()["nodes"]:
            assert not set(node) & {"size", "refs", "text"}

    def test_a_symbols_containment_is_lifted_to_its_section(self):
        edges = _graph(_EVERYTHING).to_dict()["edges"]
        assert {"source": "m", "target": "m#f", "kind": "CONTAINS"} in edges
        assert {"source": "m#Sec", "target": "m#g",
                "kind": "CONTAINS"} in edges
        assert not [e for e in edges if "#code#" in e["source"]
                    or "#code#" in e["target"]]

    def test_a_reference_is_lifted_to_the_section_that_holds_it(self):
        edges = _graph(_EVERYTHING).to_dict()["edges"]
        assert [e for e in edges if e["kind"] == "CITES"] == [
            {"source": "m", "target": "m#Sec", "kind": "CITES",
             "start_line": 3}]

    def test_two_references_from_one_section_merge_at_the_earlier_line(
        self,
    ):
        doc = _graph(
            "#M\n\n##S\n\nFirst #T.\n\nSecond #T.\n\n##T\n\nTarget.\n"
        ).to_dict()
        assert [e for e in doc["edges"] if e["kind"] == "CITES"] == [
            {"source": "m#S", "target": "m#T", "kind": "CITES",
             "start_line": 5}]

    def test_the_hidden_leaves_have_no_edges(self):
        doc = _graph(_EVERYTHING).to_dict()
        shown = {n["address"] for n in doc["nodes"]}
        for edge in doc["edges"]:
            assert edge["source"] in shown and edge["target"] in shown

    def test_containment_is_still_a_forest(self):
        doc = _graph(_EVERYTHING).to_dict()
        parents: dict[str, list[str]] = {}
        for edge in doc["edges"]:
            if edge["kind"] == "CONTAINS":
                parents.setdefault(edge["target"], []).append(
                    edge["source"])
        assert all(len(p) == 1 for p in parents.values())


class TestIndex:
    def test_every_node(self):
        graph = _graph(_EVERYTHING)
        doc = graph.to_dict(level="index")
        assert set(_by_address(doc)) == {n.address for n in graph.nodes()}

    def test_a_paragraph_holds_its_references(self):
        nodes = _by_address(_graph(_EVERYTHING).to_dict(level="index"))
        assert nodes["m#prose#1"]["refs"] == [
            {"label": "Sec", "sub": False, "start_line": 3},
            {"label": "Sec", "sub": True, "start_line": 3}]
        assert "refs" not in nodes["m#code#1"]

    def test_every_node_has_a_size(self):
        doc = _graph(_EVERYTHING).to_dict(level="index")
        assert all(isinstance(n["size"], int) for n in doc["nodes"])

    def test_size_is_the_text_held_at_or_under_a_node(self):
        graph = _graph(_EVERYTHING)
        nodes = _by_address(graph.to_dict(level="index"))
        assert nodes["m#prose#1"]["size"] == len(
            "Intro, see #Sec and ##Sec.")
        assert nodes["m#Sec"]["size"] == (
            nodes["m#Sec#prose#1"]["size"] + nodes["m#Sec#code#1"]["size"])

    def test_a_symbol_has_the_size_of_its_lines_and_adds_nothing(self):
        graph = _graph(_EVERYTHING)
        nodes = _by_address(graph.to_dict(level="index"))
        assert nodes["m#f"]["size"] == len(graph.text("m#f"))
        assert nodes["m#code#1"]["size"] == len(graph.text("m#code#1"))

    def test_a_modules_size_is_all_the_text_in_it(self):
        graph = _graph(_EVERYTHING)
        index = graph.to_dict(level="index")
        full = graph.to_dict(level="full")
        total = sum(len(n["text"]) for n in full["nodes"] if "text" in n)
        assert _by_address(index)["m"]["size"] == total


class TestFull:
    def test_text_is_on_each_node_that_holds_text(self):
        graph = _graph(_EVERYTHING)
        nodes = _by_address(graph.to_dict(level="full"))
        held = {n.address for n in graph.nodes()
                if n.text is not None and n.kind != NodeKind.SYMBOL}
        assert {a for a, n in nodes.items() if "text" in n} == held

    def test_a_symbol_has_no_text_its_lines_are_in_its_code(self):
        nodes = _by_address(_graph(_EVERYTHING).to_dict(level="full"))
        assert "text" not in nodes["m#f"]
        assert "def f" in nodes["m#code#1"]["text"]

    def test_a_containers_text_is_not_repeated(self):
        nodes = _by_address(_graph(_EVERYTHING).to_dict(level="full"))
        for address in ("m", "m#Sec", "m#Tests", "m#post-text",
                        "m#Tests#grp", "m#appendix#1"):
            assert "text" not in nodes[address], address

    def test_the_text_of_a_paragraph_and_a_claim(self):
        nodes = _by_address(_graph(_EVERYTHING).to_dict(level="full"))
        assert nodes["m#prose#1"]["text"] == "Intro, see #Sec and ##Sec."
        assert nodes["m#example#1"]["text"].strip() == "f() == 1"


@pytest.mark.parametrize("name,kit", _PROJECTS, ids=[p[0] for p in _PROJECTS])
class TestEveryExample:
    def test_each_piece_of_text_is_there_once(self, name, kit):
        doc = _project(name, kit).to_dict(level="full")
        with_text = [n for n in doc["nodes"] if "text" in n]
        assert len({n["address"] for n in with_text}) == len(with_text)
        assert not [n for n in with_text if n["kind"] == "SYMBOL"]
        assert {n["kind"] for n in with_text} <= {
            "PROSE", "CODE", "BULLETS", "EXAMPLE", "PROPERTY", "RUN", "TEST",
            "LISTING", "IMPORT", "DECLARATION"}

    def test_index_is_full_without_the_text(self, name, kit):
        graph = _project(name, kit)
        full = graph.to_dict(level="full")
        index = graph.to_dict(level="index")
        for node in full["nodes"]:
            node.pop("text", None)
        assert index == full | {"level": "index"}

    def test_outline_is_index_with_the_leaves_hidden_and_lifted(
        self, name, kit,
    ):
        graph = _project(name, kit)
        outline = graph.to_dict(level="outline")
        index = graph.to_dict(level="index")
        assert outline == _hidden(index)

    def test_every_level_conforms_to_the_schema(self, name, kit):
        graph = _project(name, kit)
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        for level in LEVELS:
            jsonschema.validate(graph.to_dict(level=level), schema)


def _hidden(index: dict) -> dict:
    """The outline of an `index` document, worked out from it alone: its
    nodes without the anonymous leaves, the fields only `index` has taken
    off, and their edges moved to the nearest node that is shown."""
    parent = {e["target"]: e["source"] for e in index["edges"]
              if e["kind"] == "CONTAINS"}
    hidden = {n["address"] for n in index["nodes"]
              if n["kind"] in _LEAVES}

    def shown(address: str) -> str:
        while address in hidden:
            address = parent[address]
        return address

    nodes = [{k: v for k, v in n.items() if k not in ("size", "refs")}
             for n in index["nodes"] if n["address"] not in hidden]
    merged: dict[tuple, dict] = {}
    for edge in index["edges"]:
        if edge["kind"] == "CONTAINS" and edge["target"] in hidden:
            continue
        key = (shown(edge["source"]), shown(edge["target"]), edge["kind"])
        lifted = {"source": key[0], "target": key[1], "kind": key[2]}
        if "start_line" in edge:
            lifted["start_line"] = edge["start_line"]
        if key not in merged:
            merged[key] = lifted
        elif "start_line" in lifted and (
                "start_line" not in merged[key]
                or lifted["start_line"] < merged[key]["start_line"]):
            merged[key]["start_line"] = lifted["start_line"]
    return {"version": 2, "level": "outline", "nodes": nodes,
            "edges": list(merged.values())}


class TestTheSchema:
    def _schema(self):
        return json.loads(SCHEMA.read_text(encoding="utf-8"))

    def test_it_is_a_json_schema(self):
        jsonschema.Draft7Validator.check_schema(self._schema())

    def test_a_document_of_every_level_validates(self):
        graph = _graph(_EVERYTHING)
        for level in LEVELS:
            jsonschema.validate(graph.to_dict(level=level), self._schema())

    def test_the_version_is_2_and_the_level_one_of_the_three(self):
        schema = self._schema()
        good = {"version": 2, "level": "outline", "nodes": [], "edges": []}
        jsonschema.validate(good, schema)
        for bad in ({**good, "version": 1}, {**good, "level": "detail"}):
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(bad, schema)

    def test_defines_is_not_an_edge_kind(self):
        edge = self._schema()["definitions"]["GraphEdge"]
        assert "DEFINES" not in edge["properties"]["kind"]["enum"]

    def test_node_kinds_are_the_real_kinds(self):
        node = self._schema()["definitions"]["GraphNode"]
        assert set(node["properties"]["kind"]["enum"]) == {
            k.name for k in NodeKind}

    def test_an_unknown_field_is_rejected(self):
        bad = {"version": 2, "level": "outline", "edges": [], "nodes": [
            {"address": "t", "label": "T", "kind": "MODULE", "extra": 1}]}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, self._schema())

    def test_content_is_gone(self):
        bad = {"version": 2, "level": "outline", "edges": [], "nodes": [
            {"address": "t", "label": "T", "kind": "MODULE",
             "content": {"prose": "x"}}]}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, self._schema())
