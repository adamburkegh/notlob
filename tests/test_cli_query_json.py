"""The shape of ``notlob query ...`` output (stable machine-readable output).

Specified by ``notlob/schema/query_result.json``. The query commands print
node summaries: the same ``Node`` (and ``Content``) as the name-graph
export, so the two schemas carry identical definitions and a test keeps
them identical. Unlike ``test --json`` and ``check --json`` these outputs
are bare JSON values (an array, a node, or ``null``), not versioned
objects; they follow the name-graph's node shape.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from notlob import EdgeKind, NodeKind
from notlob.commands import (
    cmd_query_callees, cmd_query_callers, cmd_query_children,
    cmd_query_content, cmd_query_imported_by, cmd_query_imports,
    cmd_query_references, cmd_query_referenced_by, cmd_query_resolve,
    cmd_query_search,
)

SCHEMA_DIR = Path(__file__).parent.parent / "notlob" / "schema"

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
    monkeypatch.chdir(tmp_path)
    return tmp_path


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


class TestNodeLists:
    """children, imports, imported-by, callers, callees, references,
    referenced-by and search each print an array of node summaries."""

    def test_search(self, project, capsys):
        rc, doc = _run(capsys, cmd_query_search, "helper")
        assert rc == 0
        _validate(doc, "NodeList")
        assert "alpha#helper" in _addresses(doc)

    def test_search_with_kind(self, project, capsys):
        _rc, doc = _run(capsys, cmd_query_search, "helper", "SYMBOL")
        _validate(doc, "NodeList")
        assert {n["kind"] for n in doc} == {"SYMBOL"}

    def test_children(self, project, capsys):
        rc, doc = _run(capsys, cmd_query_children, "alpha", "DEFINES")
        assert rc == 0
        _validate(doc, "NodeList")
        # DEFINES covers the symbols and the module's claim nodes.
        assert _addresses(doc) == {
            "alpha#helper", "alpha#caller", "alpha#example#1",
        }
        assert {n["kind"] for n in doc} == {"SYMBOL", "EXAMPLE"}

    def test_imports_and_imported_by(self, project, capsys):
        _rc, doc = _run(capsys, cmd_query_imports, "beta")
        _validate(doc, "NodeList")
        assert _addresses(doc) == {"alpha"}
        _rc, doc = _run(capsys, cmd_query_imported_by, "alpha")
        _validate(doc, "NodeList")
        assert _addresses(doc) == {"beta"}

    def test_callers_and_callees(self, project, capsys):
        _rc, doc = _run(capsys, cmd_query_callers, "alpha#helper")
        _validate(doc, "NodeList")
        assert _addresses(doc) == {"alpha#caller"}
        _rc, doc = _run(capsys, cmd_query_callees, "alpha#caller")
        _validate(doc, "NodeList")
        assert _addresses(doc) == {"alpha#helper"}

    def test_references_and_referenced_by(self, project, capsys):
        _rc, doc = _run(capsys, cmd_query_references, "beta")
        _validate(doc, "NodeList")
        assert "alpha" in _addresses(doc)
        _rc, doc = _run(capsys, cmd_query_referenced_by, "alpha")
        _validate(doc, "NodeList")
        assert "beta" in _addresses(doc)

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

    def test_content(self, project, capsys):
        rc, doc = _run(capsys, cmd_query_content, "alpha")
        assert rc == 0
        _validate(doc, "NodeOrNull")
        body = doc["content"]["body"]
        assert any("An intro with a list." in e["text"] for e in body
                   if e["kind"] == "prose")
        assert any("def helper" in e["text"] for e in body
                   if e["kind"] == "code")

    def test_content_has_each_section_text_once(self, project, capsys):
        """`query content` is the cheap way to read one section; it once
        printed every paragraph and code block twice (flat `prose` and
        `code` beside `body`)."""
        _rc, doc = _run(capsys, cmd_query_content, "alpha")
        dumped = json.dumps(doc)
        assert dumped.count("An intro with a list.") == 1
        assert dumped.count("def helper") == 1
        assert "prose" not in doc["content"]

    def test_content_carries_the_bullet_count(self, project, capsys):
        """Real content from a section with a bullet list. The shape
        `name_graph.json` once rejected."""
        _rc, doc = _run(capsys, cmd_query_content, "alpha")
        assert doc["content"]["bullet_block_count"] == 1

    def test_content_of_a_symbol_has_its_code(self, project, capsys):
        _rc, doc = _run(capsys, cmd_query_content, "alpha#helper")
        _validate(doc, "NodeOrNull")
        assert "return 1" in doc["content"]["code"]

    def test_content_miss_is_null_and_exit_one(self, project, capsys):
        rc, doc = _run(capsys, cmd_query_content, "no/such#address")
        assert rc == 1
        assert doc is None


class TestSchema:
    def test_schema_is_valid_json_schema(self):
        jsonschema.Draft7Validator.check_schema(_schema())

    def test_node_and_content_match_the_name_graph_schema(self):
        """One node shape, specified twice (the written schemas must each
        stand alone, so no cross-file $ref): the definitions must not
        drift apart."""
        mine, graph = _schema()["definitions"], _schema("name_graph.json")[
            "definitions"]
        shared = ("Node", "Content", "BodyItem", "ProseItem", "CodeItem",
                  "BulletsItem", "ClaimItem", "Ref", "Import")
        for name in shared:
            assert mine[name] == graph[name], name

    def test_kind_enums_are_the_real_kinds(self):
        """Adding a NodeKind or EdgeKind without updating the schemas must
        fail here."""
        for name in ("query_result.json", "name_graph.json"):
            kinds = _schema(name)["definitions"]["Node"]["properties"][
                "kind"]["enum"]
            assert set(kinds) == {k.name for k in NodeKind}, name
        edge_kinds = _schema("name_graph.json")["definitions"]["Edge"][
            "properties"]["kind"]["enum"]
        assert set(edge_kinds) == {k.name for k in EdgeKind}

    def test_a_node_without_an_address_is_rejected(self):
        with pytest.raises(jsonschema.ValidationError):
            _validate([{"label": "x", "kind": "MODULE"}], "NodeList")
