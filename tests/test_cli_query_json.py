"""The shape of ``notlob query ...`` output (stable machine-readable output).

Specified by ``notlob/schema/query_result.json``. The query commands read
the graph itself and print its nodes in the shape ``notlob graph`` prints
at ``outline``, so the two schemas carry identical definitions of a node
(and of a reference and an edge), and a test keeps them identical. Unlike
``test --json`` and ``check --json`` these outputs are bare JSON values
(an array, a node, or ``null``) or, for ``content`` with ``--format
json``, the subtree, nested.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

import notlob.commands as commands
import notlob.graph as graph_module
from notlob import EdgeKind, NodeKind
from notlob.commands import (
    cmd_query_callees, cmd_query_callers, cmd_query_children,
    cmd_query_content, cmd_query_imported_by, cmd_query_imports,
    cmd_query_cites, cmd_query_cited_by, cmd_query_resolve,
    cmd_query_search,
)

SCHEMA_DIR = Path(__file__).parent.parent / "notlob" / "schema"
EXAMPLES = Path(__file__).parent.parent / "examples"

_BINDING = "#Query Repro\n\n---\n\n#Binding\n    ~language python\n"

_ALPHA = (
    "#Alpha\n\n"
    "An intro with a list.\n\n"
    "* one\n* two\n\n"
    "    def helper():\n        return 1\n\n"
    "    def caller():\n        return helper()\n\n"
    "~example\n    caller() == 1\n"
)
_BETA = (
    "#Beta\n\n"
    "Builds on #Alpha.\n\n"
    "    def use_it():\n        return caller()\n\n"
    "---\n\n#References\n    #Alpha\n"
)
# Two paragraphs of one section, and one of the module, name Alpha.
_GAMMA = (
    "#Gamma\n\n"
    "Intro, see #Alpha.\n\n"
    "##S\n\n"
    "First, #Alpha.\n\n"
    "Second, #Alpha again.\n\n"
    "---\n\n#References\n    #Alpha\n"
)


def _write(root: Path, name: str, content: str) -> Path:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def project(tmp_path, monkeypatch):
    _write(tmp_path, "binding.lob", _BINDING)
    _write(tmp_path, "alpha.lob", _ALPHA)
    _write(tmp_path, "beta.lob", _BETA)
    _write(tmp_path, "gamma.lob", _GAMMA)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def roman(monkeypatch):
    monkeypatch.chdir(EXAMPLES / "roman")


def _schema(name: str = "query_result.json") -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _validate(doc, definition: str) -> None:
    schema = _schema()
    jsonschema.validate(doc, {
        "$schema": schema["$schema"],
        "definitions": schema["definitions"],
        "$ref": f"#/definitions/{definition}",
    })


def _run(capsys, func, *args):
    """Run a query command; return ``(exit_code, parsed_stdout)``.
    Parsing all of stdout as JSON is the 'only the document' check."""
    rc = func(*args)
    return rc, json.loads(capsys.readouterr().out)


def _addresses(doc) -> set[str]:
    return {n["address"] for n in doc}


def _in_order(doc) -> list[str]:
    return [n["address"] for n in doc]


def _flatten(node: dict) -> list[dict]:
    """The nodes of a nested ``content`` answer, parents first, in the
    order they are written."""
    found = [node]
    for child in node.get("children", []):
        found.extend(_flatten(child))
    return found


class TestNodeLists:
    """children, imports, imported-by, callers, callees, cites,
    cited-by and search each print an array of nodes."""

    def test_search(self, project, capsys):
        rc, doc = _run(capsys, cmd_query_search, "helper")
        assert rc == 0
        _validate(doc, "NodeList")
        assert "alpha#helper" in _addresses(doc)

    def test_search_with_kind(self, project, capsys):
        _rc, doc = _run(capsys, cmd_query_search, "helper", "SYMBOL")
        _validate(doc, "NodeList")
        assert {n["kind"] for n in doc} == {"SYMBOL"}

    def test_search_does_not_return_the_anonymous_leaves(
        self, project, capsys,
    ):
        _rc, doc = _run(capsys, cmd_query_search, "*")
        assert doc
        assert not {n["kind"] for n in doc} & {"PROSE", "CODE", "BULLETS"}
        assert not [n for n in doc if n["label"].startswith(
            ("prose#", "code#", "bullets#"))]

    def test_search_by_a_kind_that_outline_hides_is_an_error(
        self, project, capsys,
    ):
        assert cmd_query_search("*", "PROSE") == 1
        captured = capsys.readouterr()
        assert captured.out == "" and "PROSE" in captured.err

    def test_children_are_the_contained_nodes_leaves_included(
        self, project, capsys,
    ):
        rc, doc = _run(capsys, cmd_query_children, "alpha")
        assert rc == 0
        _validate(doc, "NodeList")
        assert _in_order(doc) == [
            "alpha#prose#1", "alpha#bullets#1", "alpha#code#1",
            "alpha#example#1",
        ]
        assert [n["kind"] for n in doc] == [
            "PROSE", "BULLETS", "CODE", "EXAMPLE"]

    def test_the_children_of_a_code_block_are_its_symbols(
        self, project, capsys,
    ):
        _rc, doc = _run(capsys, cmd_query_children, "alpha#code#1")
        assert _in_order(doc) == ["alpha#helper", "alpha#caller"]

    def test_children_by_another_edge_kind(self, project, capsys):
        _rc, doc = _run(capsys, cmd_query_children, "alpha#caller", "USES")
        _validate(doc, "NodeList")
        assert _in_order(doc) == ["alpha#helper"]

    def test_defines_is_not_an_edge_kind(self, project, capsys):
        assert cmd_query_children("alpha", "DEFINES") == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "DEFINES" in captured.err and "CONTAINS" in captured.err

    def test_children_of_a_section_in_roman(self, roman, capsys):
        _rc, doc = _run(capsys, cmd_query_children,
                        "roman/numerals#Decoding")
        assert [n["kind"] for n in doc] == ["PROSE", "CODE", "EXAMPLE"]

    def test_imports_and_imported_by(self, project, capsys):
        _rc, doc = _run(capsys, cmd_query_imports, "beta")
        _validate(doc, "NodeList")
        assert _addresses(doc) == {"alpha"}
        _rc, doc = _run(capsys, cmd_query_imported_by, "alpha")
        _validate(doc, "NodeList")
        assert _addresses(doc) == {"beta", "gamma"}

    def test_callers_and_callees(self, project, capsys):
        _rc, doc = _run(capsys, cmd_query_callers, "alpha#helper")
        _validate(doc, "NodeList")
        assert _addresses(doc) == {"alpha#caller"}
        _rc, doc = _run(capsys, cmd_query_callees, "alpha#caller")
        _validate(doc, "NodeList")
        assert _addresses(doc) == {"alpha#helper"}

    def test_cites_of_a_module(self, project, capsys):
        _rc, doc = _run(capsys, cmd_query_cites, "beta")
        _validate(doc, "NodeList")
        assert _in_order(doc) == ["alpha"]

    def test_the_cites_of_a_section_are_its_paragraphs(
        self, project, capsys,
    ):
        _rc, doc = _run(capsys, cmd_query_cites, "gamma#S")
        assert _in_order(doc) == ["alpha"]

    def test_a_paragraphs_own_cites(self, project, capsys):
        _rc, doc = _run(capsys, cmd_query_cites, "gamma#S#prose#2")
        assert _in_order(doc) == ["alpha"]

    def test_a_modules_cites_leave_out_its_sections(
        self, project, capsys,
    ):
        _write(project, "delta.lob",
               "#Delta\n\n##S\n\nSee #Alpha.\n\n---\n\n#References\n"
               "    #Alpha\n")
        _rc, doc = _run(capsys, cmd_query_cites, "delta")
        assert doc == []

    def test_cited_by_shows_the_section_that_holds_the_paragraph(
        self, project, capsys,
    ):
        _rc, doc = _run(capsys, cmd_query_cited_by, "alpha")
        _validate(doc, "NodeList")
        assert _in_order(doc) == ["beta", "gamma", "gamma#S"]

    def test_cited_by_names_each_source_once(self, project, capsys):
        _rc, doc = _run(capsys, cmd_query_cited_by, "alpha")
        assert len(doc) == len(_addresses(doc))

    def test_empty_result_is_an_empty_array(self, project, capsys):
        rc, doc = _run(capsys, cmd_query_search, "nothing_matches_this")
        assert rc == 0
        assert doc == []
        _validate(doc, "NodeList")

    def test_list_nodes_have_no_content(self, project, capsys):
        _rc, doc = _run(capsys, cmd_query_search, "Alpha")
        assert all("content" not in n for n in doc)


class TestSingleNode:
    def test_resolve(self, project, capsys):
        rc, doc = _run(capsys, cmd_query_resolve, "Alpha")
        assert rc == 0
        _validate(doc, "NodeOrNull")
        assert doc["address"] == "alpha"
        assert doc["kind"] == "MODULE"

    def test_resolve_miss_is_null_and_exit_one(self, project, capsys):
        rc, doc = _run(capsys, cmd_query_resolve, "Nonesuch")
        assert rc == 1
        assert doc is None
        _validate(doc, "NodeOrNull")

    def test_a_node_names_its_file_and_lines(self, project, capsys):
        _rc, doc = _run(capsys, cmd_query_resolve, "helper", "alpha")
        assert doc["file"] == "alpha.lob"
        assert (doc["start_line"], doc["end_line"]) == (8, 9)


class TestNamed:
    def test_named_is_printed_on_named_nodes_only(self, roman, capsys):
        _rc, doc = _run(capsys, cmd_query_children, "roman/numerals")
        named = {n["address"]: n.get("named") for n in doc}
        assert named["roman/numerals#Decoding"] is True
        assert named["roman/numerals#example#1"] is None
        assert all("name" not in n for n in doc)

    def test_the_name_is_never_printed_by_a_query(self, roman, capsys):
        """(`notlob graph` at every level is tested in test_graph_levels.)"""
        _rc, doc = _run(capsys, cmd_query_search, "*")
        assert all("name" not in n for n in doc)
        _rc, content = _run(capsys, cmd_query_content, "roman/numerals",
                            None, "json")
        assert all("name" not in n for n in _flatten(content))


class TestQueryContent:
    ROOT = "roman/numerals#Decoding"

    def _content(self, capsys, address=None, depth=None):
        rc, doc = _run(capsys, cmd_query_content, address or self.ROOT,
                       depth, "json")
        return rc, doc

    def test_the_whole_subtree_in_document_order(self, roman, capsys):
        rc, doc = self._content(capsys)
        assert rc == 0
        _validate(doc, "ContentOrNull")
        assert doc["address"] == self.ROOT
        assert _in_order(_flatten(doc)) == [
            self.ROOT, f"{self.ROOT}#prose#1", f"{self.ROOT}#code#1",
            "roman/numerals#from_roman", f"{self.ROOT}#example#1"]

    def test_each_leaf_has_its_text_once_and_a_symbol_has_none(
        self, roman, capsys,
    ):
        _rc, doc = self._content(capsys)
        nodes = {n["address"]: n for n in _flatten(doc)}
        assert "def from_roman" in nodes[f"{self.ROOT}#code#1"]["text"]
        assert "Decoding is the inverse" in nodes[
            f"{self.ROOT}#prose#1"]["text"]
        assert "from_roman('IV')" in nodes[f"{self.ROOT}#example#1"]["text"]
        assert "text" not in nodes["roman/numerals#from_roman"]
        assert "text" not in nodes[self.ROOT]

    def test_the_containment_is_the_nesting_and_there_are_no_edges(
        self, roman, capsys,
    ):
        _rc, doc = self._content(capsys)
        assert "edges" not in doc
        assert [c["address"] for c in doc["children"]] == [
            f"{self.ROOT}#prose#1", f"{self.ROOT}#code#1",
            f"{self.ROOT}#example#1"]
        assert [c["address"] for c in doc["children"][1]["children"]] == [
            "roman/numerals#from_roman"]

    def test_depth_zero_is_the_node_alone(self, roman, capsys):
        _rc, doc = self._content(capsys, self.ROOT, 0)
        _validate(doc, "ContentOrNull")
        assert _in_order(_flatten(doc)) == [self.ROOT]
        assert "children" not in doc

    def test_depth_one_adds_the_children(self, roman, capsys):
        _rc, doc = self._content(capsys, self.ROOT, 1)
        assert _in_order(_flatten(doc)) == [
            self.ROOT, f"{self.ROOT}#prose#1", f"{self.ROOT}#code#1",
            f"{self.ROOT}#example#1"]

    def test_a_symbol_alone_shows_its_code(self, roman, capsys):
        rc, node = self._content(capsys, "roman/numerals#to_roman")
        assert rc == 0
        _validate(node, "ContentOrNull")
        assert node["address"] == "roman/numerals#to_roman"
        assert node["text"].startswith("def to_roman(n: int) -> str:")
        assert "return result" in node["text"]
        assert (node["start_line"], node["end_line"]) == (19, 25)

    def test_a_symbols_text_is_there_when_its_code_block_is_not(
        self, project, capsys,
    ):
        _rc, doc = self._content(capsys, "alpha#helper")
        assert doc["text"] == "def helper():\n    return 1"

    def test_a_symbol_has_no_text_when_its_code_block_is(
        self, project, capsys,
    ):
        _rc, doc = self._content(capsys, "alpha#code#1")
        nodes = {n["address"]: n for n in _flatten(doc)}
        assert "def helper" in nodes["alpha#code#1"]["text"]
        assert "text" not in nodes["alpha#helper"]

    def test_a_property_holds_its_code_and_its_function_has_none(
        self, project, capsys,
    ):
        _write(project, "prop.lob",
               "#Prop\n\n~property p\n    @given()\n    def prop(): pass\n")
        _rc, doc = self._content(capsys, "prop#p")
        nodes = {n["address"]: n for n in _flatten(doc)}
        assert "def prop" in nodes["prop#p"]["text"]
        assert "text" not in nodes["prop#p#prop"]

    def test_a_modules_whole_subtree_holds_each_line_once(
        self, roman, capsys,
    ):
        _rc, doc = self._content(capsys, "roman/numerals")
        texts = [n["text"] for n in _flatten(doc) if "text" in n]
        assert sum(texts.count(t) for t in set(texts)) == len(texts)
        assert not [n for n in _flatten(doc)
                    if n["kind"] == "SYMBOL" and "text" in n]

    def test_an_unknown_address_is_null_and_exit_one(self, project, capsys):
        rc, doc = _run(capsys, cmd_query_content, "no/such#address",
                       None, "json")
        assert rc == 1
        assert doc is None
        _validate(doc, "ContentOrNull")

    def test_a_negative_depth_is_an_error(self, project, capsys):
        assert cmd_query_content("alpha", -1, "json") == 1
        assert "depth" in capsys.readouterr().err


class TestNothingReadsTheLayer:
    """Only Turtle still prints the layer."""

    def test_no_query_calls_it(self, project, capsys, monkeypatch):
        def forbidden(*_a, **_k):
            raise AssertionError("a query read the layer")

        monkeypatch.setattr(graph_module, "legacy_graph", forbidden,
                            raising=False)
        monkeypatch.setattr(commands, "legacy_graph", forbidden,
                            raising=False)
        calls = [
            (cmd_query_children, ("alpha",)),
            (cmd_query_children, ("alpha", "USES")),
            (cmd_query_resolve, ("Alpha",)),
            (cmd_query_search, ("helper",)),
            (cmd_query_imports, ("beta",)),
            (cmd_query_imported_by, ("alpha",)),
            (cmd_query_callers, ("alpha#helper",)),
            (cmd_query_callees, ("alpha#caller",)),
            (cmd_query_cites, ("beta",)),
            (cmd_query_cited_by, ("alpha",)),
            (cmd_query_content, ("alpha", None, "json")),
            (cmd_query_content, ("alpha", 1, "json")),
        ]
        for func, args in calls:
            assert func(*args) == 0
            json.loads(capsys.readouterr().out)

    def test_the_query_helper_that_wrapped_the_graph_is_gone(self):
        assert not hasattr(commands, "_require_query_graph")


class TestMcpTools:
    def _tool(self, name: str) -> dict:
        from notlob.mcp_server import TOOLS
        return next(t for t in TOOLS if t["name"] == name)["inputSchema"][
            "properties"]

    def test_children_kinds_have_no_defines(self):
        kinds = self._tool("notlob_query_children")["kind"]["enum"]
        assert set(kinds) == {k.name for k in EdgeKind} - {"DEFINES"}

    def test_search_kinds_are_those_outline_shows(self):
        kinds = self._tool("notlob_query_search")["kind"]["enum"]
        assert set(kinds) == {k.name for k in NodeKind} - {
            "PROSE", "CODE", "BULLETS", "LISTING", "IMPORT",
            "DECLARATION", "POST_TEXT"}

    def test_content_takes_a_depth(self):
        depth = self._tool("notlob_query_content")["depth"]
        assert depth["type"] == "integer" and depth["minimum"] == 0

    def test_content_depth_reaches_the_command(self, project):
        from notlob.mcp_server import _dispatch
        result = _dispatch("notlob_query_content",
                           {"address": "alpha", "depth": 0,
                            "format": "json"})
        document = json.loads(result["content"][0]["text"])
        assert _in_order(_flatten(document)) == ["alpha"]


class TestSchema:
    def test_schema_is_valid_json_schema(self):
        jsonschema.Draft7Validator.check_schema(_schema())

    def test_the_node_is_the_graphs_node(self):
        """One node shape, specified twice (the written schemas must each
        stand alone, so no cross-file $ref): the definitions must not
        drift apart. An answer stands on its own, so it keeps the `label`
        and `file` that the document keeps on its modules only."""
        mine, graph = _schema()["definitions"], _schema("name_graph.json")[
            "definitions"]
        assert (set(mine["Node"]["properties"])
                == set(graph["GraphNode"]["properties"]))
        for name, definition in graph["GraphNode"]["properties"].items():
            if name not in ("label", "file", "named"):
                assert mine["Node"]["properties"][name] == definition, name
        assert (mine["Node"]["properties"]["named"]["const"]
                == graph["GraphNode"]["properties"]["named"]["const"])
        assert mine["GraphRef"] == graph["GraphRef"]
        assert mine["Edge"] == graph["GraphEdge"]

    def test_kind_enums_are_the_real_kinds(self):
        """Adding a NodeKind or EdgeKind without updating the schemas must
        fail here."""
        for name, node in (("query_result.json", "Node"),
                           ("name_graph.json", "GraphNode")):
            kinds = _schema(name)["definitions"][node]["properties"][
                "kind"]["enum"]
            assert set(kinds) == {k.name for k in NodeKind}, name
        for name, edge in (("query_result.json", "Edge"),
                           ("name_graph.json", "GraphEdge")):
            kinds = _schema(name)["definitions"][edge]["properties"][
                "kind"]["enum"]
            assert set(kinds) == {k.name for k in EdgeKind} - {"DEFINES"}

    def test_a_node_without_an_address_is_rejected(self):
        with pytest.raises(jsonschema.ValidationError):
            _validate([{"label": "x", "kind": "MODULE"}], "NodeList")

    def test_content_is_not_a_field_of_a_node(self):
        with pytest.raises(jsonschema.ValidationError):
            _validate([{"address": "x", "label": "x", "kind": "MODULE",
                        "content": {"prose": "p"}}], "NodeList")

    def test_a_content_node_needs_its_address(self):
        with pytest.raises(jsonschema.ValidationError):
            _validate({"kind": "MODULE"}, "ContentOrNull")
