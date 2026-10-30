"""`notlob query content` answers with the source.

The default answer is text: a header line, the address and the span, then
the node's own lines from its file, as written. The `.lob` syntax carries
the kinds, so nothing else is added. `--format json` is the subtree,
nested and narrow: no edges, labels, sizes or references, and the file and
last line on the root only. The cost of asking for one section is what
the section is, and that is tested here, for every section of every
example project.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

import notlob.commands as commands
import notlob.graph as graph_module
from notlob import NodeKind, build_package
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit
from notlob.commands import cmd_query_content
from notlob.graph import KINDS, content_tree

EXAMPLES = Path(__file__).parent.parent / "examples"
SCHEMAS = Path(__file__).parent.parent / "notlob" / "schema"

ROMAN = EXAMPLES / "roman"
FILE = ROMAN / "roman" / "numerals.lob"
SECTION = "roman/numerals#Decoding"

_KITS = {
    "roman": python_kit, "retail": python_kit, "gutenberg": python_kit,
    "haskell-roman": haskell_kit, "ts-media": typescript_kit,
}


@pytest.fixture
def roman(monkeypatch):
    monkeypatch.chdir(ROMAN)


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _answer(capsys, address: str, *rest) -> tuple[int, str, str]:
    rc = cmd_query_content(address, *rest)
    out = capsys.readouterr()
    return rc, out.out, out.err


def _expected(address: str, file: str, first: int, last: int) -> str:
    lines = _lines(ROMAN / file)[first - 1:last]
    return f"{address}  {file}:{first}-{last}\n" + "\n".join(lines) + "\n"


# ── The text: the header and exactly the node's lines ─────────

class TestText:
    def test_a_section(self, roman, capsys):
        rc, out, err = _answer(capsys, SECTION)
        assert (rc, err) == (0, "")
        assert out == _expected(
            SECTION, "roman/numerals.lob", 40, 60)
        assert out.splitlines()[1] == "##Decoding"

    def test_a_symbol(self, roman, capsys):
        rc, out, _err = _answer(capsys, "roman/numerals#to_roman")
        assert rc == 0
        assert out == _expected(
            "roman/numerals#to_roman", "roman/numerals.lob", 19, 25)
        assert out.splitlines()[1] == "    def to_roman(n: int) -> str:"

    def test_a_claim_with_its_sigil(self, roman, capsys):
        rc, out, _err = _answer(capsys, "roman/numerals#example#1")
        assert rc == 0
        assert out == _expected(
            "roman/numerals#example#1", "roman/numerals.lob", 27, 30)
        assert out.splitlines()[1] == "~example"

    def test_a_module_is_its_whole_file(self, roman, capsys):
        rc, out, _err = _answer(capsys, "roman/numerals")
        assert rc == 0
        body = out.split("\n", 1)[1].rstrip("\n").split("\n")
        assert body == _lines(FILE)[:len(body)]
        assert body[0] == "#Roman Numerals"
        assert "#References" in body[-1] or body[-1].strip() == ""
        assert out.splitlines()[0].startswith(
            "roman/numerals  roman/numerals.lob:1-")

    def test_a_section_in_the_tests(self, roman, capsys):
        rc, out, _err = _answer(capsys, "roman/numerals#Tests#encoding")
        assert rc == 0
        assert out.splitlines()[1] == "##encoding"

    def test_nothing_is_added_inside(self, roman, capsys):
        _rc, out, _err = _answer(capsys, SECTION)
        assert "#prose#" not in out and "#code#" not in out

    def test_the_header_names_the_file_relative_to_the_project(
        self, roman, capsys,
    ):
        _rc, out, _err = _answer(capsys, SECTION)
        assert out.splitlines()[0] == f"{SECTION}  roman/numerals.lob:40-60"


# ── The claim the teaser makes, executable ───────────────────

def _graph(project: str):
    kit = _KITS[project]
    root = EXAMPLES / project
    return root, build_package(
        root, kit.extract_symbols, call_extractor=kit.extract_calls,
        split_imports=kit.split_imports)


@pytest.mark.parametrize("project", sorted(_KITS))
class TestTheAnswerCostsWhatTheSectionIs:
    def test_every_section_is_no_longer_than_its_lines_and_header(
        self, project,
    ):
        root, graph = _graph(project)
        sections = [n for n in graph.nodes() if KINDS[n.kind].section]
        assert sections, project
        for node in sections:
            text = commands._content_text(graph, root, node.address)
            lines = _lines(root / node.file)[
                node.start_line - 1:node.end_line]
            header = text.split("\n", 1)[0]
            assert text == header + "\n" + "\n".join(lines) + "\n", (
                node.address)
            assert len(text) <= len(header) + 1 + len(
                "\n".join(lines)) + 1

    def test_and_shorter_than_its_file(self, project):
        root, graph = _graph(project)
        for node in graph.nodes():
            if not KINDS[node.kind].section:
                continue
            text = commands._content_text(graph, root, node.address)
            whole = (root / node.file).read_text(encoding="utf-8")
            assert len(text) < len(whole), node.address


# ── A node's lines are what the graph holds as its text ──────

def _squeeze(text: str) -> str:
    return "".join(text.split())


@pytest.mark.parametrize("project", sorted(_KITS))
def test_the_lines_of_a_node_match_its_text_in_the_graph(project):
    """A span that points at the wrong lines is a bug in the graph, not a
    formatting matter: every leaf's lines are the text it holds, up to
    how the graph writes it (dedented, without a list marker or a
    sigil)."""
    root, graph = _graph(project)
    checked = 0
    for node in graph.nodes():
        if node.file is None or node.start_line is None:
            continue
        text = graph.text(node.address)
        if text is None or node.kind == NodeKind.MODULE:
            continue
        lines = _lines(root / node.file)[node.start_line - 1:node.end_line]
        if KINDS[node.kind].claim or (
                node.kind == NodeKind.TEST and node.name is not None):
            lines = lines[1:]               # the sigil line
        elif node.kind == NodeKind.BULLETS:
            lines = [ln.lstrip()[1:] for ln in lines]
        elif node.kind == NodeKind.LISTING:
            lines = [ln.strip() for ln in lines]
        assert _squeeze("".join(lines)) == _squeeze(text), (
            f"{node.address}: {lines!r} != {text!r}")
        checked += 1
    assert checked, project


# ── The JSON: the subtree, nested and narrow ─────────────────

def _json(capsys, address: str, depth=None):
    rc = cmd_query_content(address, depth, "json")
    out = capsys.readouterr().out
    return rc, json.loads(out)


def _schema_check(doc) -> None:
    schema = json.loads(
        (SCHEMAS / "query_result.json").read_text(encoding="utf-8"))
    jsonschema.validate(doc, {
        "$schema": schema["$schema"],
        "definitions": schema["definitions"],
        "$ref": "#/definitions/ContentOrNull",
    })


def _walk(node: dict):
    yield node
    for child in node.get("children", []):
        yield from _walk(child)


class TestJson:
    def test_it_validates(self, roman, capsys):
        rc, doc = _json(capsys, SECTION)
        assert rc == 0
        _schema_check(doc)

    def test_it_is_nested_as_containment_says(self, roman, capsys):
        _rc, doc = _json(capsys, SECTION)
        assert doc["address"] == SECTION
        assert [c["address"] for c in doc["children"]] == [
            f"{SECTION}#prose#1", f"{SECTION}#code#1",
            f"{SECTION}#example#1"]
        code = doc["children"][1]
        assert [c["address"] for c in code["children"]] == [
            "roman/numerals#from_roman"]

    def test_the_root_has_the_file_and_no_node_its_last_line(
        self, roman, capsys,
    ):
        _rc, doc = _json(capsys, SECTION)
        assert (doc["file"], doc["start_line"]) == ("roman/numerals.lob", 40)
        for node in _walk(doc):
            assert "end_line" not in node
            if node is not doc:
                assert "file" not in node

    def test_no_edges_labels_sizes_or_references(self, roman, capsys):
        _rc, doc = _json(capsys, "roman/numerals")
        assert "edges" not in doc
        for node in _walk(doc):
            assert not {"label", "size", "refs", "edges"} & set(node)
            assert {"address", "kind"} <= set(node)

    def test_each_leafs_text_is_there_once(self, roman, capsys):
        _rc, doc = _json(capsys, "roman/numerals")
        texts = [n["text"] for n in _walk(doc) if "text" in n]
        assert len(texts) == len(set(texts))
        assert not [n for n in _walk(doc)
                    if n["kind"] == "SYMBOL" and "text" in n]
        prose = next(n for n in _walk(doc)
                     if n["address"] == f"{SECTION}#prose#1")
        assert "Decoding is the inverse" in prose["text"]

    def test_named_is_there_when_the_document_names_it(self, roman, capsys):
        _rc, doc = _json(capsys, "roman/numerals")
        named = {n["address"]: n.get("named") for n in _walk(doc)}
        assert named[SECTION] is True
        assert named[f"{SECTION}#example#1"] is None

    def test_a_symbol_asked_for_alone_carries_its_text(self, roman, capsys):
        _rc, doc = _json(capsys, "roman/numerals#to_roman")
        assert doc["text"].startswith("def to_roman(n: int) -> str:")
        assert "children" not in doc
        assert doc["start_line"] == 19
        assert "end_line" not in doc

    def test_depth_limits_the_nesting(self, roman, capsys):
        _rc, alone = _json(capsys, SECTION, 0)
        assert "children" not in alone
        _rc, one = _json(capsys, SECTION, 1)
        assert [c["address"] for c in one["children"]] == [
            f"{SECTION}#prose#1", f"{SECTION}#code#1",
            f"{SECTION}#example#1"]
        assert all("children" not in c for c in one["children"])
        for doc in (alone, one):
            _schema_check(doc)

    def test_the_facts_of_a_node_when_set(self, tmp_path, monkeypatch,
                                         capsys):
        (tmp_path / "binding.lob").write_text(
            "#P\n\n---\n\n#Binding\n    ~language python\n",
            encoding="utf-8")
        (tmp_path / "m.lob").write_text(
            "#M\n\n~run on-load\n    boot()\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        _rc, doc = _json(capsys, "m")
        run = doc["children"][0]
        assert (run["kind"], run["mode"]) == ("RUN", "on-load")
        _rc, binding = _json(capsys, "p#Binding")
        declaration = binding["children"][0]
        assert (declaration["declares"], declaration["value"]) == (
            "language", "python")

    def test_the_json_is_much_narrower_than_the_old_document(
        self, roman, capsys,
    ):
        _rc, doc = _json(capsys, SECTION)
        assert len(json.dumps(doc, indent=2)) < 6000


# ── The errors ───────────────────────────────────────────────

class TestErrors:
    def test_an_unknown_address_in_text(self, roman, capsys):
        rc, out, err = _answer(capsys, "no/such#address")
        assert (rc, out) == (1, "")
        assert err.startswith("ERROR  <query>  ")

    def test_an_unknown_address_in_json_is_null(self, roman, capsys):
        rc, doc = _json(capsys, "no/such#address")
        assert (rc, doc) == (1, None)
        _schema_check(doc)

    def test_an_external_file_has_no_lines(self, tmp_path, monkeypatch,
                                           capsys):
        (tmp_path / "binding.lob").write_text(
            "#P\n\n---\n\n#Binding\n    ~language python\n"
            "    ~external data.txt\n", encoding="utf-8")
        (tmp_path / "data.txt").write_text("x\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        rc, out, err = _answer(capsys, "data.txt")
        assert (rc, out) == (1, "")
        assert err.startswith("ERROR  <query>  ")

    def test_depth_is_for_json_only(self, roman, capsys):
        rc, out, err = _answer(capsys, SECTION, 1)
        assert (rc, out) == (1, "")
        assert err.startswith("ERROR  <query>  ")
        assert "depth" in err and "json" in err.lower()

    def test_a_negative_depth_is_an_error_in_json(self, roman, capsys):
        rc = cmd_query_content(SECTION, -1, "json")
        assert rc == 1
        assert "depth" in capsys.readouterr().err

    def test_an_unknown_format_is_an_error(self, roman, capsys):
        rc, out, err = _answer(capsys, SECTION, None, "xml")
        assert (rc, out) == (1, "")
        assert "format" in err


# ── subtree is replaced ──────────────────────────────────────

def test_subtree_is_replaced_by_the_nested_content():
    assert not hasattr(graph_module, "subtree")
    assert not hasattr(commands, "subtree")
    assert callable(content_tree)


# ── The command line ─────────────────────────────────────────

class TestTheCommandLine:
    def _run(self, monkeypatch, *words):
        import sys

        import notlob.cli as cli
        monkeypatch.setattr(sys, "argv", ["notlob", "query", "content",
                                          *words])
        with pytest.raises(SystemExit) as raised:
            cli.main()
        return raised.value.code

    def test_text_is_the_default(self, roman, monkeypatch, capsys):
        assert self._run(monkeypatch, SECTION) == 0
        assert capsys.readouterr().out.startswith(f"{SECTION}  ")

    def test_format_json(self, roman, monkeypatch, capsys):
        assert self._run(monkeypatch, SECTION, "--format", "json") == 0
        assert json.loads(capsys.readouterr().out)["address"] == SECTION

    def test_depth_with_json(self, roman, monkeypatch, capsys):
        assert self._run(
            monkeypatch, SECTION, "--format", "json", "--depth", "0") == 0
        assert "children" not in json.loads(capsys.readouterr().out)

    def test_depth_with_text_is_an_error(self, roman, monkeypatch, capsys):
        assert self._run(monkeypatch, SECTION, "--depth", "1") == 1
        assert "depth" in capsys.readouterr().err


# ── The MCP tool ─────────────────────────────────────────────

class TestMcp:
    def _tool(self) -> dict:
        from notlob.mcp_server import TOOLS
        return next(t for t in TOOLS
                    if t["name"] == "notlob_query_content")

    def test_it_offers_a_format_and_a_depth(self):
        properties = self._tool()["inputSchema"]["properties"]
        assert properties["format"]["enum"] == ["text", "json"]
        assert properties["depth"]["minimum"] == 0

    def test_text_is_the_default(self, roman):
        from notlob.mcp_server import _dispatch
        result = _dispatch("notlob_query_content", {"address": SECTION})
        assert not result["isError"]
        assert result["content"][0]["text"].startswith(
            f"{SECTION}  roman/numerals.lob:40-60\n##Decoding")

    def test_json_on_request(self, roman):
        from notlob.mcp_server import _dispatch
        result = _dispatch("notlob_query_content", {
            "address": SECTION, "format": "json", "depth": 0})
        document = json.loads(result["content"][0]["text"])
        assert document["address"] == SECTION
        assert "children" not in document

    def test_depth_with_text_is_an_error(self, roman):
        from notlob.mcp_server import _dispatch
        result = _dispatch("notlob_query_content", {
            "address": SECTION, "depth": 1})
        assert result["isError"]


# ── The schema ───────────────────────────────────────────────

class TestSchema:
    def _schema(self) -> dict:
        return json.loads(
            (SCHEMAS / "query_result.json").read_text(encoding="utf-8"))

    def test_the_content_shape_is_recursive(self):
        content = self._schema()["definitions"]["Content"]
        assert content["properties"]["children"]["items"] == {
            "$ref": "#/definitions/Content"}
        assert content["additionalProperties"] is False

    def test_it_has_no_edges_labels_sizes_or_references(self):
        properties = self._schema()["definitions"]["Content"]["properties"]
        assert not {"edges", "label", "size", "refs"} & set(properties)

    def test_its_kinds_are_the_real_kinds(self):
        properties = self._schema()["definitions"]["Content"]["properties"]
        assert set(properties["kind"]["enum"]) == {k.name for k in NodeKind}

    def test_a_node_without_an_address_is_rejected(self):
        with pytest.raises(jsonschema.ValidationError):
            _schema_check({"kind": "MODULE"})

    def test_the_old_document_is_not_the_shape(self):
        with pytest.raises(jsonschema.ValidationError):
            _schema_check({"version": 2, "level": "full", "root": "x",
                           "nodes": [], "edges": []})

