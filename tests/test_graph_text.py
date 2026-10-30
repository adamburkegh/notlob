"""``notlob graph`` answers a reader: the shape of each file, in its words.

The text is the default: each module's file on a line alone, then a line
for what is written in it, the name first and its line number in a column
on the right, indented by what is written in what. ``outline`` is the
structural lines; ``index`` adds the cross-references and declarations;
``full`` is each module as ``query content`` prints it. In JSON and
Turtle a level is the same content: ``outline`` holds the ``CONTAINS``
edges only, and no ``end_line`` is printed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest

from notlob import NodeKind, build_package
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit
from notlob.graph import (
    KINDS, EdgeKind, cited_by_edges, cites_edges, content_tree, node_summary,
)
from notlob.outline import outline_entries, render_entries

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"
SCHEMAS = ROOT / "notlob" / "schema"
RETAIL = EXAMPLES / "retail"
GUTENBERG = EXAMPLES / "gutenberg"

_KITS = {
    "roman": python_kit, "retail": python_kit, "gutenberg": python_kit,
    "haskell-roman": haskell_kit, "ts-media": typescript_kit,
}
_LEVELS = ("outline", "index", "full")

projects = pytest.mark.parametrize("project", sorted(_KITS))


@cache
def _graph(project: str):
    kit = _KITS[project]
    return build_package(
        EXAMPLES / project, kit.extract_symbols,
        call_extractor=kit.extract_calls, split_imports=kit.split_imports)


@cache
def _run(directory: Path, *args: str) -> tuple[int, str, str]:
    """``(exit code, stdout, stderr)`` of ``notlob -C directory *args``
    from the repository root."""
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    proc = subprocess.run(
        [sys.executable, "-m", "notlob.cli", "-C", str(directory), *args],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, proc.stdout, proc.stderr


def _text(project: str, level: str) -> str:
    code, out, err = _run(
        EXAMPLES / project, "graph", "--level", level)
    assert (code, err) == (0, ""), err
    return out


_LINE = re.compile(r"^( *)(.*?) {2,}(\d+)$")


def _files(text: str) -> dict[str, list[tuple[int, str, int]]]:
    """Each file of the text, with its lines as (depth, words, number)."""
    files = {}
    for block in text.rstrip("\n").split("\n\n"):
        name, *lines = block.split("\n")
        entries = []
        for line in lines:
            found = _LINE.match(line)
            assert found, f"not a line of the outline: {line!r}"
            indent, words, number = found.groups()
            assert len(indent) % 2 == 0, line
            entries.append((len(indent) // 2, words, int(number)))
        files[name] = entries
    return files


# ── The text, exactly ────────────────────────────────────────

RETAIL_INDEX = """\
binding.lob
Pricing               1
  Binding             8
    ~language python  9

pricing/discounts.lob
Pricing Discounts                        1
  cites Stacking Discounts               9
  apply_discount                        11
  ~example                              14
    uses apply_discount                 15
  Stacking Discounts                    17
    ~example                            26
      uses apply_discount               27
    ~property                           31
      uses apply_discount               43
  Tests                                 48
    boundary conditions                 50
      uses apply_discount               51
    composition                         55
      cites Stacking Discounts          58
      ~test composition_is_commutative  61
        uses apply_discount             62
  References                            69
"""

RETAIL_OUTLINE = """\
binding.lob
Pricing    1
  Binding  8

pricing/discounts.lob
Pricing Discounts                        1
  apply_discount                        11
  ~example                              14
  Stacking Discounts                    17
    ~example                            26
    ~property                           31
  Tests                                 48
    boundary conditions                 50
    composition                         55
      ~test composition_is_commutative  61
  References                            69
"""


class TestRetail:
    def test_the_outline(self):
        assert _text("retail", "outline") == RETAIL_OUTLINE

    def test_the_index(self):
        assert _text("retail", "index") == RETAIL_INDEX

    def test_the_outline_is_the_default(self):
        code, out, _ = _run(RETAIL, "graph")
        assert (code, out) == (0, RETAIL_OUTLINE)

    def test_text_is_the_default_format(self):
        assert _run(RETAIL, "graph") == _run(RETAIL, "graph", "--format",
                                             "text")

    def test_a_level_may_be_a_number(self):
        assert _run(RETAIL, "graph", "-l", "2") == _run(
            RETAIL, "graph", "--level", "index")


class TestGutenberg:
    def test_the_listing_is_under_references(self):
        hamlet = _files(_text("gutenberg", "index"))["gutenberg/hamlet.lob"]
        at = hamlet.index((2, "imports Gutenberg Corpus", 87))
        above = [e for e in hamlet[:at] if e[0] < 2][-1]
        assert above == (1, "References", above[2])

    def test_a_use_in_another_module_is_at_its_line(self):
        hamlet = _files(_text("gutenberg", "index"))["gutenberg/hamlet.lob"]
        at = hamlet.index((2, "uses load_play", 9))
        assert [e for e in hamlet[:at] if e[0] < 2][-1][1] == "HAMLET"

    def test_the_outline_has_neither(self):
        words = [w for entries in _files(
            _text("gutenberg", "outline")).values()
            for _, w, _ in entries]
        assert not [w for w in words if w.startswith(("uses ", "imports "))]


# ── Any node, not only a project ─────────────────────────────

class TestAnyNode:
    def test_a_section_with_its_references(self):
        graph = _graph("retail")
        entries = outline_entries(
            graph, "pricing/discounts#Stacking Discounts", "index")
        assert render_entries(entries) == """\
Stacking Discounts       17
  ~example               26
    uses apply_discount  27
  ~property              31
    uses apply_discount  43
"""

    def test_the_level_is_the_nodes_too(self):
        graph = _graph("retail")
        outline = outline_entries(
            graph, "pricing/discounts#Stacking Discounts", "outline")
        assert [e.words for e in outline] == [
            "Stacking Discounts", "~example", "~property"]

    def test_no_entries_render_as_nothing(self):
        assert render_entries([]) == ""


# ── Every line is real ───────────────────────────────────────

_REFERENCE = re.compile(r"^(uses|cites|imports) (.*)$")


@projects
@pytest.mark.parametrize("level", ["outline", "index"])
class TestEveryLineIsReal:
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


_DECLARATIONS = ("~language", "~external", "~on-build",
                 "~keep-generated-src")


@projects
class TestWhatIndexAdds:
    def test_only_references_and_declarations(self, project):
        outline = _files(_text(project, "outline"))
        index = _files(_text(project, "index"))
        assert list(outline) == list(index)
        for name, entries in index.items():
            kept = set(outline[name])
            added = [e for e in entries if e not in kept]
            for _, words, _ in added:
                assert (_REFERENCE.match(words)
                        or words.startswith(_DECLARATIONS)), (name, words)

    def test_the_outline_is_in_the_index_in_order(self, project):
        outline = _files(_text(project, "outline"))
        index = _files(_text(project, "index"))
        for name, entries in outline.items():
            wanted = iter(index[name])
            assert all(entry in wanted for entry in entries), name

    def test_every_reference_the_graph_holds_is_a_line(self, project):
        """A use, a citation, a listing: each at the line it is written
        on, once for a node (the first)."""
        graph = _graph(project)
        index = _files(_text(project, "index"))
        numbers = {n for entries in index.values() for _, _, n in entries}
        for edge in graph.edges():
            if edge.kind in (EdgeKind.USES, EdgeKind.CITES,
                             EdgeKind.IMPORTS):
                assert edge.start_line is not None, edge
                assert edge.start_line in numbers, edge


@projects
def test_outline_is_smaller_than_the_file_it_outlines(project):
    for name, entries in _files(_text(project, "outline")).items():
        source = (EXAMPLES / project / name).read_text(encoding="utf-8")
        outline = "\n".join(
            "  " * depth + words for depth, words, _ in entries)
        assert len(outline) < len(source), name


# ── full is query content, a module at a time ────────────────

@projects
def test_full_is_the_content_of_each_module(project):
    expected = []
    for module in _graph(project).nodes(NodeKind.MODULE):
        code, out, err = _run(
            EXAMPLES / project, "query", "content", module.address)
        assert (code, err) == (0, ""), err
        expected.append(out)
    assert _text(project, "full") == "\n".join(expected)


# ── JSON and Turtle: a level is the same content ─────────────

def _document(project: str, level: str) -> dict:
    code, out, err = _run(
        EXAMPLES / project, "graph", "--format", "json", "--level", level)
    assert (code, err) == (0, ""), err
    return json.loads(out)


@projects
class TestJsonLevels:
    def test_outline_holds_only_contains(self, project):
        kinds = {e["kind"] for e in _document(project, "outline")["edges"]}
        assert kinds == {"CONTAINS"}

    @pytest.mark.parametrize("level", ["index", "full"])
    def test_the_references_arrive_at_index(self, project, level):
        graph = _graph(project)
        wanted = {k for k in EdgeKind if k != EdgeKind.CONTAINS
                  and any(graph.edges(k))}
        kinds = {e["kind"] for e in _document(project, level)["edges"]}
        assert kinds == {"CONTAINS"} | {k.name for k in wanted}

    @pytest.mark.parametrize("level", _LEVELS)
    def test_no_end_line_in_the_document(self, project, level):
        for node in _document(project, level)["nodes"]:
            assert "end_line" not in node, node

    def test_no_end_line_in_a_summary(self, project):
        for node in _graph(project).nodes():
            assert "end_line" not in node_summary(node)

    def test_no_end_line_in_a_content_tree(self, project):
        for module in _graph(project).nodes(NodeKind.MODULE):
            tree = content_tree(_graph(project), module.address)
            assert "end_line" not in json.dumps(tree)
            assert tree["start_line"] == module.start_line

    @pytest.mark.parametrize("level", _LEVELS)
    def test_no_end_line_in_the_turtle(self, project, level):
        code, out, err = _run(
            EXAMPLES / project, "graph", "--format", "turtle",
            "--level", level)
        assert (code, err) == (0, ""), err
        assert "endLine" not in out

    def test_the_model_keeps_it(self, project):
        for module in _graph(project).nodes(NodeKind.MODULE):
            assert module.end_line is not None


def _property_names(schema) -> set[str]:
    found = set()
    if isinstance(schema, dict):
        found |= set(schema.get("properties", {}))
        for value in schema.values():
            found |= _property_names(value)
    elif isinstance(schema, list):
        for value in schema:
            found |= _property_names(value)
    return found


class TestTheSchemas:
    @pytest.mark.parametrize(
        "name", ["name_graph.json", "query_result.json"])
    def test_none_has_an_end_line(self, name):
        schema = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
        assert "end_line" not in _property_names(schema)

    def test_the_ontology_has_no_end_line(self):
        assert "endLine" not in (SCHEMAS / "notlob.ttl").read_text(
            encoding="utf-8")


# ── Citations are answered as they were ──────────────────────

def _lifted_citations(graph) -> list[tuple[str, str]]:
    """Each citation from the node that shows it at ``outline``, to the
    node it names: where a paragraph (or any node ``outline`` leaves out)
    is the source or the target, the section that holds it."""
    def shown(address: str) -> str:
        node = graph.node(address)
        while KINDS[node.kind].hidden_at_outline:
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
            if KINDS[node.kind].hidden_at_outline:
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


# ── The command ──────────────────────────────────────────────

class TestTheCommand:
    def test_the_help_says_where_the_references_are(self):
        code, out, _ = _run(RETAIL, "graph", "--help")
        words = " ".join(out.split())
        assert code == 0
        assert "text" in words and "turtle" in words
        assert re.search(r"uses.*cites.*index|index.*uses.*cites", words)

    def test_an_unknown_level_is_an_error(self):
        code, out, err = _run(RETAIL, "graph", "--level", "detail")
        assert (code, out) == (1, "")
        assert err.startswith("ERROR  <graph>  ")

    def test_an_unknown_format_is_refused(self):
        code, _, err = _run(RETAIL, "graph", "--format", "yaml")
        assert code == 2
        assert "invalid choice" in err

    def test_the_mcp_tool_answers_in_text(self, monkeypatch):
        from notlob.mcp_server import _dispatch
        monkeypatch.chdir(RETAIL)
        result = _dispatch("notlob_graph", {"level": "outline"})
        assert result["isError"] is False
        assert result["content"][0]["text"].rstrip("\n") == (
            RETAIL_OUTLINE.rstrip("\n"))
