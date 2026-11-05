"""The commands write the view, and the old path is gone.

``notlob graph`` takes the view of a preset and writes it, for a project and
for a one-file project; ``--level`` takes the four names or their ranks;
the queries print the target's node; and nothing of the old document is
left in ``notlob/``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from functools import cache

from notlob import build_package
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit
from notlob.commands import (
    QUERY_EDGE_KINDS, QUERY_NODE_KINDS, cmd_graph, cmd_query_callers,
    cmd_query_children, cmd_query_search,
)
from notlob.graph import KINDS, PRESETS, EdgeKind, NodeKind
from notlob.view import cited_by_edges, cites_edges
from test_graph_document import SMALL

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"
GOLDEN = Path(__file__).parent / "golden"
SCHEMAS = ROOT / "notlob" / "schema"

LEVEL_RANKS = {"outline": "1", "index": "2", "block": "3", "full": "4"}

_KITS = {
    "roman": python_kit, "retail": python_kit, "gutenberg": python_kit,
    "haskell-roman": haskell_kit, "ts-media": typescript_kit,
}
projects = pytest.mark.parametrize("project", sorted(_KITS))
RETAIL = EXAMPLES / "retail"

SINGLE = """\
#Single

See #Sec.

    def f(x):
        return x

##Sec

Text.

~example
    f(1) == 1
"""


def _notlob(directory: Path, *args: str) -> tuple[int, str, str]:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    done = subprocess.run(
        [sys.executable, "-m", "notlob.cli", "-C", str(directory), *args],
        cwd=ROOT, env=env, capture_output=True, encoding="utf-8")
    return done.returncode, done.stdout, done.stderr


@pytest.fixture
def small(tmp_path) -> Path:
    for name, text in SMALL.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


@pytest.fixture
def single(tmp_path, monkeypatch) -> Path:
    """A .lob file with no ``binding.lob`` above it, as the working
    directory."""
    (tmp_path / "mod.lob").write_text(SINGLE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ── --level takes the four names or their ranks ──────────────

class TestLevelByNumber:
    @pytest.mark.parametrize("fmt", ["text", "json", "turtle"])
    @pytest.mark.parametrize("name", LEVEL_RANKS)
    def test_a_rank_is_its_level(self, small, name, fmt):
        by_name = _notlob(small, "graph", "--format", fmt, "--level", name)
        by_rank = _notlob(
            small, "graph", "--format", fmt, "--level", LEVEL_RANKS[name])
        assert by_name[0] == by_rank[0] == 0, by_name[2] + by_rank[2]
        assert by_name[1] == by_rank[1]

    def test_block_is_three_and_full_is_four(self, small):
        _, block, _ = _notlob(small, "graph", "--level", "block")
        _, full, _ = _notlob(small, "graph", "--level", "full")
        assert _notlob(small, "graph", "--level", "3")[1] == block
        assert _notlob(small, "graph", "--level", "4")[1] == full
        assert block != full

    def test_block_lists_the_blocks(self, small):
        _, block, _ = _notlob(small, "graph", "--level", "block")
        assert "prose#1" in block and "post-text" in block

    @pytest.mark.parametrize("level", ["detail", "0", "5", "-1"])
    def test_an_unknown_level_names_the_choices(self, small, level):
        code, out, err = _notlob(small, "graph", "--level", level)
        assert (code, out) == (1, "")
        for choice in ("outline", "index", "block", "full", "1", "4"):
            assert choice in err

    def test_the_help_says_what_each_level_shows(self):
        _, out, _ = _notlob(ROOT, "graph", "--help")
        for level in LEVEL_RANKS:
            assert level in out


# ── A one-file project has its file ──────────────────────────

class TestOneFile:
    def test_text_at_outline(self, single, capsys):
        assert cmd_graph(Path("mod.lob"), fmt="text", level="outline") == 0
        assert capsys.readouterr().out == (
            "mod.lob\n"
            "Single" + " " * 9 + "1\n"
            "  f" + " " * 12 + "5\n"
            "  Sec" + " " * 10 + "8\n"
            "    ~example  12\n")

    def test_text_at_full_is_the_file_under_its_path(self, single, capsys):
        assert cmd_graph(Path("mod.lob"), fmt="text", level="full") == 0
        assert capsys.readouterr().out == "mod.lob\n" + SINGLE

    def test_text_at_index_has_its_references(self, single, capsys):
        assert cmd_graph(Path("mod.lob"), fmt="text", level="index") == 0
        out = capsys.readouterr().out
        assert "cites Sec" in out and "uses f" in out

    @pytest.mark.parametrize("level", list(LEVEL_RANKS))
    def test_json_names_the_module_s_file(self, single, capsys, level):
        assert cmd_graph(Path("mod.lob"), fmt="json", level=level) == 0
        doc = json.loads(capsys.readouterr().out)
        (module,) = [n for n in doc["nodes"] if n["kind"] == "MODULE"]
        assert module["file"] == "mod.lob"
        assert [n["address"] for n in doc["nodes"] if "file" in n] == [
            "single"]

    def test_json_at_full_has_the_bodies(self, single, capsys):
        cmd_graph(Path("mod.lob"), fmt="json", level="full")
        doc = json.loads(capsys.readouterr().out)
        bodies = {n["address"]: n.get("body") for n in doc["nodes"]}
        assert bodies["single"] == "#Single"
        assert bodies["single#Sec"] == "##Sec"

    def test_turtle_names_the_file(self, single, capsys):
        cmd_graph(Path("mod.lob"), fmt="turtle", level="outline")
        assert 'notlob:file "mod.lob"' in capsys.readouterr().out

    def test_a_file_that_does_not_parse_is_an_error(
        self, single, capsys,
    ):
        (single / "bad.lob").write_text("not a module\n", encoding="utf-8")
        assert cmd_graph(Path("bad.lob")) == 1
        assert capsys.readouterr().out == ""


# ── An appendix in text ──────────────────────────────────────

class TestAnAppendixInText:
    def test_the_small_project_at_outline(self, small):
        code, out, err = _notlob(small, "graph", "--level", "outline")
        assert code == 0, err
        assert out == (GOLDEN / "view_small_outline.txt").read_text(
            encoding="utf-8")

    def test_a_titled_appendix_says_its_heading_then_its_name(self, small):
        _, out, _ = _notlob(small, "graph", "--level", "outline")
        words = [line.split()[:-1] for line in out.splitlines()
                 if "Appendix" in line]
        assert words == [["Appendix", "Glossary"], ["Appendix"]]


# ── MCP and the CLI say the same ─────────────────────────────

class TestMcp:
    def test_graph_offers_the_four_levels_and_their_ranks(self):
        from notlob.mcp_server import TOOLS
        tool = next(t for t in TOOLS if t["name"] == "notlob_graph")
        level = tool["inputSchema"]["properties"]["level"]
        assert set(level["enum"]) == {
            "outline", "index", "block", "full", 1, 2, 3, 4}
        for name in LEVEL_RANKS:
            assert name in tool["description"]


# ── The queries print the target's node ──────────────────────

def _schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


QUERIES = [
    ("children", "pricing/discounts#Stacking Discounts"),
    ("search", "apply_*"),
    ("callers", "pricing/discounts#apply_discount"),
    ("callees", "pricing/discounts#Stacking Discounts#example#1"),
    ("cites", "pricing/discounts"),
    ("cited-by", "pricing/discounts#Stacking Discounts"),
]


class TestAQueryPrintsTheTargetsNode:
    @pytest.mark.parametrize("op, argument", QUERIES)
    def test_its_json_is_a_node_list(self, op, argument):
        code, out, err = _notlob(
            EXAMPLES / "retail", "query", op, argument, "--format", "json")
        assert code == 0, err
        nodes = json.loads(out)
        jsonschema.validate(nodes, {
            **_schema("query_result.json"),
            "anyOf": [{"$ref": "#/definitions/NodeList"}]})
        assert nodes
        for node in nodes:
            assert "label" not in node
            assert "file" in node or node["kind"] == "EXTERNAL"
            assert not {"size", "refs", "text"} & set(node)

    def test_a_named_node_has_its_name(self):
        _, out, _ = _notlob(
            EXAMPLES / "retail", "query", "search", "apply_discount",
            "--format", "json")
        (node,) = json.loads(out)
        assert node["name"] == "apply_discount"
        assert node["kind"] == "SYMBOL"
        assert node["file"] == "pricing/discounts.lob"

    def test_a_positional_node_has_no_name(self):
        _, out, _ = _notlob(
            EXAMPLES / "retail", "query", "children",
            "pricing/discounts", "--format", "json")
        prose = [n for n in json.loads(out) if n["kind"] == "PROSE"]
        assert prose and all("name" not in n for n in prose)

    def test_the_schema_s_node_is_the_graphs_node_but_for_its_file(self):
        node = _schema("query_result.json")["definitions"]["Node"]
        graph = _schema("name_graph.json")["definitions"]["GraphNode"]
        assert set(node["properties"]) == set(graph["properties"])
        for name, definition in graph["properties"].items():
            if name != "file":
                assert node["properties"][name] == definition, name
        assert set(node["required"]) == {"address", "kind"}

    def test_the_schema_has_no_content_edge_or_ref(self):
        definitions = _schema("query_result.json")["definitions"]
        assert not {"Content", "ContentOrNull", "GraphRef", "Edge"} & set(
            definitions)


class TestQueryKinds:
    def test_search_offers_every_kind(self):
        assert QUERY_NODE_KINDS == tuple(k.name for k in NodeKind)

    def test_children_does_not_offer_what_no_graph_holds(self):
        assert "CONTAINS_INDIRECTLY" not in QUERY_EDGE_KINDS
        assert set(QUERY_EDGE_KINDS) == {
            k.name for k in EdgeKind} - {"CONTAINS_INDIRECTLY"}

    def test_search_finds_a_node_by_its_name_whatever_its_kind(
        self, monkeypatch, capsys,
    ):
        monkeypatch.chdir(EXAMPLES / "ts-media")
        assert cmd_query_search("index.html", fmt="json") == 0
        found = json.loads(capsys.readouterr().out)
        assert [(n["address"], n["kind"], n["name"]) for n in found] == [
            ("index.html", "EXTERNAL", "index.html")]

    def test_search_without_a_kind_finds_every_named_node_and_no_other(
        self, monkeypatch, capsys,
    ):
        monkeypatch.chdir(EXAMPLES / "ts-media")
        graph = build_package(
            EXAMPLES / "ts-media", typescript_kit.extract_symbols,
            call_extractor=typescript_kit.extract_calls)
        assert cmd_query_search("*", fmt="json") == 0
        found = json.loads(capsys.readouterr().out)
        kinds = {n["kind"] for n in found}
        assert "EXTERNAL" in kinds
        assert not {"PROSE", "CODE", "BULLETS", "POST_TEXT",
                    "TEST_LINES"} & kinds
        assert [n["address"] for n in found] == [
            n.address for n in graph.nodes() if n.name is not None]

    def test_children_by_a_kind_a_graph_holds(self, monkeypatch, capsys):
        monkeypatch.chdir(EXAMPLES / "retail")
        assert cmd_query_children(
            "pricing/discounts#Stacking Discounts", "USES",
            fmt="json") == 0
        assert cmd_query_callers(
            "pricing/discounts#apply_discount", fmt="json") == 0


# ── The old path is gone ─────────────────────────────────────

GONE = ("hidden_at_outline", "name_graph_next", "graph_next", "to_dict",
        "parse_level", "_sizes", "content_tree")

#: The parse tree's own converters, which share the name ``to_dict``.
_TREES = ("parser.py", "__init__.py")


class TestTheOldPathIsGone:
    @pytest.mark.parametrize("word", GONE)
    def test_nothing_in_notlob_names_it(self, word):
        pattern = re.compile(rf"\b{word}\b")
        found = []
        for path in sorted((ROOT / "notlob").rglob("*")):
            if (not path.is_file() or path.suffix == ".pyc"
                    or "__pycache__" in path.parts
                    or (word == "to_dict" and path.name in _TREES)):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if pattern.search(text):
                found.append(path.relative_to(ROOT).as_posix())
        assert found == []

    def test_the_old_schema_took_the_new_ones_name(self):
        assert not (SCHEMAS / "name_graph_next.json").exists()
        doc = _schema("name_graph.json")
        assert doc["properties"]["level"]["enum"] == [
            "outline", "index", "block", "full"]

    def test_the_old_modules_are_gone(self):
        assert not (ROOT / "notlob" / "graph_next.py").exists()
        assert not (ROOT / "notlob" / "outline.py").exists()


# ── The text is real ─────────────────────────────────────────

@cache
def _graph(project: str):
    kit = _KITS[project]
    return build_package(
        EXAMPLES / project, kit.extract_symbols,
        call_extractor=kit.extract_calls, split_imports=kit.split_imports)


@cache
def _text(project: str, level: str) -> str:
    code, out, err = _notlob(
        EXAMPLES / project, "graph", "--level", level)
    assert (code, err) == (0, ""), err
    return out


_ROW = re.compile(r"^( *)(.*?) {2,}(\d+)(?:-\d+)?(?:, \d+(?:-\d+)?)*$")
_REFERENCE = re.compile(r"^(uses|cites|imports) (.*)$")


def _files(text: str) -> dict[str, list[tuple[int, str, int]]]:
    """Each file of the text, with its rows as (depth, words, the first
    line of the number column)."""
    files = {}
    for block in text.rstrip("\n").split("\n\n"):
        name, *rows = block.split("\n")
        entries = []
        for row in rows:
            found = _ROW.match(row)
            assert found, f"not a row of the text: {row!r}"
            indent, words, number = found.groups()
            assert len(indent) % 2 == 0, row
            entries.append((len(indent) // 2, words, int(number)))
        files[name] = entries
    return files


@projects
@pytest.mark.parametrize("level", ["outline", "index"])
class TestEveryRowIsReal:
    def test_the_line_holds_the_words(self, project, level):
        for name, entries in _files(_text(project, level)).items():
            lines = (EXAMPLES / project / name).read_text(
                encoding="utf-8").splitlines()
            for _, words, number in entries:
                assert 1 <= number <= len(lines), (name, words, number)
                reference = _REFERENCE.match(words)
                needle = reference.group(2) if reference else words
                assert needle in lines[number - 1], (
                    name, words, number, lines[number - 1])

    def test_a_file_is_named_as_it_is_in_the_project(self, project, level):
        for name in _files(_text(project, level)):
            assert (EXAMPLES / project / name).is_file()
            assert "\\" not in name


@projects
def test_the_outline_is_smaller_than_the_file_it_outlines(project):
    for name, entries in _files(_text(project, "outline")).items():
        source = (EXAMPLES / project / name).read_text(encoding="utf-8")
        outline = "\n".join(
            "  " * depth + words for depth, words, _ in entries)
        assert len(outline) < len(source), name


class TestTheCommandsDefaults:
    def test_the_outline_is_the_default(self):
        assert _notlob(RETAIL, "graph") == _notlob(
            RETAIL, "graph", "--level", "outline")

    def test_text_is_the_default_format(self):
        assert _notlob(RETAIL, "graph") == _notlob(
            RETAIL, "graph", "--format", "text")

    def test_an_unknown_format_is_refused(self):
        code, _, err = _notlob(RETAIL, "graph", "--format", "yaml")
        assert code == 2 and "invalid choice" in err

    def test_the_mcp_tool_answers_as_the_command_does(self, monkeypatch):
        from notlob.mcp_server import _dispatch
        monkeypatch.chdir(RETAIL)
        result = _dispatch("notlob_graph", {"level": "block"})
        assert result["isError"] is False
        assert result["content"][0]["text"] == _notlob(
            RETAIL, "graph", "--level", "block")[1].rstrip("\n")

    def test_the_mcp_tool_takes_a_rank(self, monkeypatch):
        from notlob.mcp_server import _dispatch
        monkeypatch.chdir(RETAIL)
        by_rank = _dispatch("notlob_graph", {"level": 3})
        by_name = _dispatch("notlob_graph", {"level": "block"})
        assert by_rank == by_name


# ── Citations are answered as they were ──────────────────────

def _lifted_citations(graph) -> list[tuple[str, str]]:
    """Each citation from the node that shows it at ``outline``, to the
    node it names: where a paragraph (or any node ``outline`` leaves out)
    is the source or the target, the section that holds it."""
    def shown(address: str) -> str:
        node = graph.node(address)
        while KINDS[node.kind].rank > PRESETS["outline"]:
            node = graph.parent_of(node.address)
        return node.address

    found: dict[tuple[str, str], None] = {}
    for edge in graph.edges(EdgeKind.CITES):
        found.setdefault((shown(edge.source), shown(edge.target)))
    return list(found)


@projects
class TestCitationsAreAsTheyWere:
    def test_cites(self, project):
        graph = _graph(project)
        lifted = _lifted_citations(graph)
        for node in graph.nodes():
            if KINDS[node.kind].rank > PRESETS["outline"]:
                continue
            got = [e.target for e in cites_edges(graph, node.address)]
            assert sorted(got) == sorted(
                {t for s, t in lifted if s == node.address}), node.address

    def test_cited_by(self, project):
        graph = _graph(project)
        lifted = _lifted_citations(graph)
        for node in graph.nodes():
            got = [e.source for e in cited_by_edges(graph, node.address)]
            assert sorted(got) == sorted(
                {s for s, t in lifted if t == node.address}), node.address
