"""`notlob query content` answers with the source: the view started at an
address, at ``full``.

The shape of what it prints is held to the schema in
``test_graph_document.py`` (``TestContent``); here are its text, its errors,
its command line and its MCP tool, over the roman example, and a guard that
the span a node holds in the model is the lines of its file.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from notlob import NodeKind, build_package
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit
from notlob.commands import cmd_query_content
from notlob.graph import KINDS

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


def _expected(file: str, first: int, last: int) -> str:
    """The file, with the line the answer starts at when it is not the
    first, and the lines from there to the last."""
    lines = _lines(ROMAN / file)[first - 1:last]
    header = file if first == 1 else f"{file}:{first}"
    return header + "\n" + "\n".join(lines) + "\n"


# ── The text: the file, and exactly the node's lines ─────────

class TestText:
    def test_a_section(self, roman, capsys):
        rc, out, err = _answer(capsys, SECTION)
        assert (rc, err) == (0, "")
        assert out == _expected("roman/numerals.lob", 40, 60)
        assert out.splitlines()[1] == "##Decoding"

    def test_a_symbol(self, roman, capsys):
        rc, out, _err = _answer(capsys, "roman/numerals#to_roman")
        assert rc == 0
        assert out == _expected("roman/numerals.lob", 19, 25)
        assert out.splitlines()[1] == "    def to_roman(n: int) -> str:"

    def test_a_claim_with_its_sigil(self, roman, capsys):
        rc, out, _err = _answer(capsys, "roman/numerals#example#1")
        assert rc == 0
        assert out == _expected("roman/numerals.lob", 27, 30)
        assert out.splitlines()[1] == "~example"

    def test_a_module_is_its_whole_file_under_its_path(self, roman, capsys):
        rc, out, _err = _answer(capsys, "roman/numerals")
        assert rc == 0
        assert out == "roman/numerals.lob\n" + "\n".join(
            _lines(FILE)).rstrip("\n") + "\n"

    def test_a_section_in_the_tests(self, roman, capsys):
        rc, out, _err = _answer(capsys, "roman/numerals#Tests#encoding")
        assert rc == 0
        assert out.splitlines()[1] == "##encoding"

    def test_nothing_is_added_inside(self, roman, capsys):
        _rc, out, _err = _answer(capsys, SECTION)
        assert "#prose#" not in out and "#code#" not in out

    def test_a_depth_stops_at_the_node_alone(self, roman, capsys):
        rc, out, _err = _answer(capsys, SECTION, 0)
        assert rc == 0
        assert out == _expected("roman/numerals.lob", 40, 60)

    def test_the_answer_is_shorter_than_its_file(self, roman, capsys):
        _rc, out, _err = _answer(capsys, SECTION)
        assert len(out) < len(FILE.read_text(encoding="utf-8"))


# ── A node's lines are what the graph holds as its text ──────

def _squeeze(text: str) -> str:
    return "".join(text.split())


@pytest.mark.parametrize("project", sorted(_KITS))
def test_the_lines_of_a_node_match_its_text_in_the_graph(project):
    """A span that points at the wrong lines is a bug in the graph, not a
    formatting matter: every leaf's lines are the text it holds, up to
    how the graph writes it (dedented, without a list marker or a
    sigil)."""
    kit, root = _KITS[project], EXAMPLES / project
    graph = build_package(
        root, kit.extract_symbols, call_extractor=kit.extract_calls,
        split_imports=kit.split_imports)
    checked = 0
    for node in graph.nodes():
        if node.file is None or node.start_line is None:
            continue
        text = graph.text(node.address)
        if text is None or node.kind == NodeKind.MODULE:
            continue
        lines = _lines(root / node.file)[node.start_line - 1:node.end_line]
        if KINDS[node.kind].claim or node.kind == NodeKind.TEST:
            lines = lines[1:]               # the sigil line
        elif node.kind == NodeKind.BULLETS:
            lines = [ln.lstrip()[1:] for ln in lines]
        elif node.kind == NodeKind.LISTING:
            lines = [ln.strip() for ln in lines]
        assert _squeeze("".join(lines)) == _squeeze(text), (
            f"{node.address}: {lines!r} != {text!r}")
        checked += 1
    assert checked, project


# ── The JSON ─────────────────────────────────────────────────

class TestJson:
    def _json(self, capsys, address: str, depth=None):
        rc = cmd_query_content(address, depth, "json")
        return rc, json.loads(capsys.readouterr().out)

    def test_it_is_a_document_of_the_graph_schema(self, roman, capsys):
        rc, doc = self._json(capsys, SECTION)
        assert rc == 0
        jsonschema.validate(doc, json.loads(
            (SCHEMAS / "name_graph.json").read_text(encoding="utf-8")))

    def test_it_is_the_full_view_and_its_root_has_the_file(
        self, roman, capsys,
    ):
        _rc, doc = self._json(capsys, SECTION)
        assert doc["level"] == "full"
        assert doc["nodes"][0]["address"] == SECTION
        assert doc["nodes"][0]["file"] == "roman/numerals.lob"

    def test_a_depth_limits_the_view(self, roman, capsys):
        _rc, alone = self._json(capsys, SECTION, 0)
        assert [n["address"] for n in alone["nodes"]] == [SECTION]
        _rc, one = self._json(capsys, SECTION, 1)
        assert [n["address"] for n in one["nodes"]] == [
            SECTION, f"{SECTION}#prose#1", f"{SECTION}#code#1",
            f"{SECTION}#example#1"]

    def test_the_facts_of_a_node_when_set(self, tmp_path, monkeypatch,
                                         capsys):
        (tmp_path / "binding.lob").write_text(
            "#P\n\n---\n\n#Binding\n    ~language python\n",
            encoding="utf-8")
        (tmp_path / "m.lob").write_text(
            "#M\n\n~run on-load\n    boot()\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        _rc, doc = self._json(capsys, "m")
        run = next(n for n in doc["nodes"] if n["kind"] == "RUN")
        assert run["mode"] == "on-load"
        _rc, binding = self._json(capsys, "p#Binding")
        declaration = next(
            n for n in binding["nodes"] if n["kind"] == "DECLARATION")
        assert (declaration["declares"], declaration["value"]) == (
            "language", "python")


# ── The errors ───────────────────────────────────────────────

class TestErrors:
    def test_an_unknown_address_in_text(self, roman, capsys):
        rc, out, err = _answer(capsys, "no/such#address")
        assert (rc, out) == (1, "")
        assert err.startswith("ERROR  <query>  ")

    def test_an_unknown_address_in_json_is_null(self, roman, capsys):
        rc = cmd_query_content("no/such#address", None, "json")
        assert (rc, json.loads(capsys.readouterr().out)) == (1, None)

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

    @pytest.mark.parametrize("fmt", ["text", "json"])
    def test_a_negative_depth_is_an_error(self, roman, capsys, fmt):
        rc = cmd_query_content(SECTION, -1, fmt)
        assert rc == 1
        assert "depth" in capsys.readouterr().err

    def test_an_unknown_format_is_an_error(self, roman, capsys):
        rc, out, err = _answer(capsys, SECTION, None, "xml")
        assert (rc, out) == (1, "")
        assert "format" in err


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
        assert capsys.readouterr().out.startswith(
            "roman/numerals.lob:40\n##Decoding")

    def test_format_json(self, roman, monkeypatch, capsys):
        assert self._run(monkeypatch, SECTION, "--format", "json") == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["nodes"][0]["address"] == SECTION

    def test_depth_with_json(self, roman, monkeypatch, capsys):
        assert self._run(
            monkeypatch, SECTION, "--format", "json", "--depth", "0") == 0
        assert len(json.loads(capsys.readouterr().out)["nodes"]) == 1

    def test_depth_with_text(self, roman, monkeypatch, capsys):
        assert self._run(monkeypatch, SECTION, "--depth", "0") == 0
        assert capsys.readouterr().out == _expected(
            "roman/numerals.lob", 40, 60)


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
            "roman/numerals.lob:40\n##Decoding")

    def test_json_on_request(self, roman):
        from notlob.mcp_server import _dispatch
        result = _dispatch("notlob_query_content", {
            "address": SECTION, "format": "json", "depth": 0})
        document = json.loads(result["content"][0]["text"])
        assert [n["address"] for n in document["nodes"]] == [SECTION]

    def test_depth_with_text_is_an_answer(self, roman):
        from notlob.mcp_server import _dispatch
        result = _dispatch("notlob_query_content", {
            "address": SECTION, "depth": 0})
        assert not result["isError"]
