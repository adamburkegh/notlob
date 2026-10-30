"""``notlob query`` answers a reader: text by default, three columns.

A list of nodes is one line a node: a sigil (blank for what has none), the
address, and where, ``file:line`` from the project root. For a query that
follows an edge, where is the line the edge is written on. ``--format
json`` gives the answer as before.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
from functools import cache
from pathlib import Path

import jsonschema
import pytest

import notlob.commands as commands
from notlob.commands import (
    cmd_query_callees, cmd_query_callers, cmd_query_children,
    cmd_query_cited_by, cmd_query_cites, cmd_query_imported_by,
    cmd_query_imports, cmd_query_resolve, cmd_query_search,
)
from notlob.graph import (
    EdgeKind, KINDS, NodeKind, cited_by, cites_of, node_summary,
)

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"
SCHEMA = ROOT / "notlob" / "schema" / "query_result.json"

RETAIL = EXAMPLES / "retail"
GUTENBERG = EXAMPLES / "gutenberg"

DISCOUNTS = "pricing/discounts"
DISCOUNTS_LOB = "pricing/discounts.lob"
HAMLET = "gutenberg/hamlet"
HAMLET_LOB = "gutenberg/hamlet.lob"

#: The address queries that follow an edge, by command-line name.
_EDGE_QUERIES = {
    "callers": cmd_query_callers, "callees": cmd_query_callees,
    "cites": cmd_query_cites, "cited-by": cmd_query_cited_by,
    "imports": cmd_query_imports, "imported-by": cmd_query_imported_by,
}


@cache
def _run(directory: Path, *args: str) -> tuple[int, str, str]:
    """``(exit code, stdout, stderr)`` of ``notlob -C directory *args``
    from the repository root."""
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    proc = subprocess.run(
        [sys.executable, "-m", "notlob.cli", "-C", str(directory), *args],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, proc.stdout, proc.stderr


def _render(rows: list[tuple[str, str, str]]) -> str:
    """What an answer of *rows* (sigil, address, where) must look like:
    each column as wide as its longest entry and two spaces from the next,
    trailing spaces stripped; a column with nothing in it is not there."""
    columns = [list(c) for c in zip(*rows)]
    widths = [max(map(len, c)) for c in columns]
    lines = []
    for row in rows:
        cells = [cell.ljust(width) for cell, width in zip(row, widths)
                 if width]
        lines.append("  ".join(cells).rstrip())
    return "".join(f"{line}\n" for line in lines)


def _query(fn, *args, **kwargs) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*args, **kwargs)
    return rc, out.getvalue(), err.getvalue()


# ── The answers, exactly ─────────────────────────────────────

class TestRetail:
    def test_callers(self):
        code, out, err = _run(
            RETAIL, "query", "callers", f"{DISCOUNTS}#apply_discount")
        assert (code, err) == (0, "")
        assert out == _render([
            ("~example", f"{DISCOUNTS}#example#1",
             f"{DISCOUNTS_LOB}:15"),
            ("~example", f"{DISCOUNTS}#Stacking Discounts#example#1",
             f"{DISCOUNTS_LOB}:27"),
            ("~property", f"{DISCOUNTS}#Stacking Discounts#property#1",
             f"{DISCOUNTS_LOB}:43"),
            ("", f"{DISCOUNTS}#Tests#boundary conditions#test#1",
             f"{DISCOUNTS_LOB}:51"),
            ("~test",
             f"{DISCOUNTS}#Tests#composition#composition_is_commutative",
             f"{DISCOUNTS_LOB}:62"),
        ])

    def test_callers_as_text_have_the_brief_shape(self):
        _, out, _ = _run(
            RETAIL, "query", "callers", f"{DISCOUNTS}#apply_discount")
        first = out.splitlines()[0]
        assert re.fullmatch(
            r"~example   pricing/discounts#example#1 +"
            r"pricing/discounts\.lob:15", first)

    def test_search_gives_where_the_node_starts(self):
        code, out, _ = _run(RETAIL, "query", "search", "apply_*")
        assert code == 0
        assert out == _render([
            ("", f"{DISCOUNTS}#apply_discount", f"{DISCOUNTS_LOB}:11")])

    def test_search_by_kind_has_the_sigil(self):
        _, out, _ = _run(
            RETAIL, "query", "search", "*", "--kind", "PROPERTY")
        assert out == _render([
            ("~property", f"{DISCOUNTS}#Stacking Discounts#property#1",
             f"{DISCOUNTS_LOB}:31")])

    def test_children_give_where_each_starts(self):
        code, out, _ = _run(
            RETAIL, "query", "children", f"{DISCOUNTS}#Stacking Discounts")
        assert code == 0
        assert out == _render([
            ("", f"{DISCOUNTS}#Stacking Discounts#prose#1",
             f"{DISCOUNTS_LOB}:19"),
            ("", f"{DISCOUNTS}#Stacking Discounts#prose#2",
             f"{DISCOUNTS_LOB}:23"),
            ("~example", f"{DISCOUNTS}#Stacking Discounts#example#1",
             f"{DISCOUNTS_LOB}:26"),
            ("~property", f"{DISCOUNTS}#Stacking Discounts#property#1",
             f"{DISCOUNTS_LOB}:31"),
        ])

    def test_a_child_by_another_edge_still_gives_where_it_starts(self):
        _, out, _ = _run(
            RETAIL, "query", "children",
            f"{DISCOUNTS}#example#1", "--kind", "USES")
        assert out == _render([
            ("", f"{DISCOUNTS}#apply_discount", f"{DISCOUNTS_LOB}:11")])


class TestGutenberg:
    def test_callees_give_where_the_uses_are_written(self):
        code, out, err = _run(
            GUTENBERG, "query", "callees", f"{HAMLET}#report")
        assert (code, err) == (0, "")
        assert out == _render([
            ("", f"{HAMLET}#WORDS", f"{HAMLET_LOB}:47"),
            ("", f"{HAMLET}#_TOP", f"{HAMLET_LOB}:55"),
        ])
        assert out == (
            "gutenberg/hamlet#WORDS  gutenberg/hamlet.lob:47\n"
            "gutenberg/hamlet#_TOP   gutenberg/hamlet.lob:55\n")

    def test_imports_give_the_line_of_the_listing(self):
        _, out, _ = _run(GUTENBERG, "query", "imports", HAMLET)
        assert out == _render([
            ("", "gutenberg/corpus", f"{HAMLET_LOB}:87")])

    def test_imported_by_gives_the_same_line(self):
        _, out, _ = _run(GUTENBERG, "query", "imported-by",
                         "gutenberg/corpus")
        assert out == _render([("", HAMLET, f"{HAMLET_LOB}:87")])

    def test_callers(self):
        _, out, _ = _run(
            GUTENBERG, "query", "callers", "gutenberg/corpus#load_play")
        assert out == _render([
            ("", f"{HAMLET}#HAMLET", f"{HAMLET_LOB}:9")])

    def test_cites_give_the_line_of_the_citation(self):
        _, out, _ = _run(GUTENBERG, "query", "cites", HAMLET)
        assert out == _render([
            ("", "gutenberg/corpus", f"{HAMLET_LOB}:5")])

    def test_cited_by_with_nothing_prints_nothing(self):
        code, out, err = _run(
            GUTENBERG, "query", "cited-by",
            "gutenberg/corpus#Word Frequencies")
        assert (code, out, err) == (0, "", "")


# ── Every line is real ───────────────────────────────────────

def _projects() -> list[Path]:
    return sorted(p.parent for p in EXAMPLES.glob("*/binding.lob"))


def _in(project: Path, monkeypatch):
    """Work in *project*, with its graph built once for every query that
    asks for it, and return that graph."""
    monkeypatch.chdir(project)
    graph = commands._require_graph()
    monkeypatch.setattr(commands, "_require_graph", lambda *a, **k: graph)
    return graph


def _parse(answer: str) -> list[tuple[str, str | None]]:
    """``(address, where)`` for each line of a text answer. The address
    is the column before where; a blank where leaves the address last."""
    found = []
    for line in answer.splitlines():
        where = re.search(r"\s{2,}(\S+:\d+)$", line)
        head = line[:where.start()] if where else line
        columns = re.split(r"\s{2,}", head.strip())
        found.append((columns[-1], where.group(1) if where else None))
    return found


def _line_of(project: Path, where: str) -> str:
    file, _, number = where.rpartition(":")
    lines = (project / file).read_text(encoding="utf-8").splitlines()
    return lines[int(number) - 1]


@pytest.mark.parametrize("project", _projects(), ids=lambda p: p.name)
class TestEveryLineIsReal:
    def _asked(self, graph) -> list[str]:
        """The addresses worth asking an edge query about: every end of
        every edge there is, and the modules."""
        asked = {n.address for n in graph.nodes(NodeKind.MODULE)}
        for kind in (EdgeKind.USES, EdgeKind.CITES, EdgeKind.IMPORTS):
            for edge in graph.edges(kind):
                asked |= {edge.source, edge.target}
        return sorted(asked)

    def test_the_line_names_the_thing_the_edge_reaches(
        self, project, monkeypatch,
    ):
        graph = _in(project, monkeypatch)
        checked = 0
        for address in self._asked(graph):
            for name, fn in _EDGE_QUERIES.items():
                rc, out, err = _query(fn, address)
                assert (rc, err) == (0, ""), (name, address, err)
                for printed, where in _parse(out):
                    reached = (address if name in
                               ("callers", "cited-by", "imported-by")
                               else printed)
                    label = graph.node(reached).label
                    assert where, (name, address, printed)
                    assert label in _line_of(project, where), (
                        name, address, printed, where, label)
                    checked += 1
        has_edges = any(list(graph.edges(kind)) for kind in (
            EdgeKind.USES, EdgeKind.CITES, EdgeKind.IMPORTS))
        assert checked or not has_edges

    def test_a_sigil_is_the_one_the_file_has_at_that_line(
        self, project, monkeypatch,
    ):
        _in(project, monkeypatch)
        rc, out, _ = _query(cmd_query_search, "*")
        assert rc == 0
        for line in out.splitlines():
            sigil = re.match(r"(~\w+)\s", line)
            where = re.search(r"\s{2,}(\S+:\d+)$", line)
            if sigil:
                assert where, line
                assert _line_of(project, where.group(1)).lstrip().startswith(
                    sigil.group(1)), line


# ── Sigils, one home ─────────────────────────────────────────

class TestSigils:
    def test_the_kinds_that_have_one(self):
        have = {k.name: KINDS[k].sigil for k in NodeKind if KINDS[k].sigil}
        assert have == {"EXAMPLE": "~example", "PROPERTY": "~property",
                        "RUN": "~run", "TEST": "~test"}

    def test_only_a_named_test_has_its_sigil(self):
        assert KINDS[NodeKind.TEST].sigil_needs_name
        assert not any(KINDS[k].sigil_needs_name for k in NodeKind
                       if k != NodeKind.TEST)

    def test_a_run_of_bare_assertions_has_none_and_a_named_test_has(
        self, monkeypatch,
    ):
        monkeypatch.chdir(RETAIL)
        _, out, _ = _query(cmd_query_search, "*", "TEST")
        by_address = {a: line for (a, _), line in
                      zip(_parse(out), out.splitlines())}
        named = f"{DISCOUNTS}#Tests#composition#composition_is_commutative"
        bare = f"{DISCOUNTS}#Tests#boundary conditions#test#1"
        assert by_address[named].startswith("~test")
        assert not by_address[bare].lstrip().startswith("~")


# ── Edge cases of the answer ─────────────────────────────────

class TestTheAnswerAtItsEdges:
    @pytest.mark.parametrize("name", sorted(_EDGE_QUERIES) + ["children"])
    def test_an_unknown_address_is_an_error(self, name):
        code, out, err = _run(RETAIL, "query", name, "no/such#address")
        assert code == 1
        assert out == ""
        assert err.startswith("ERROR  <query>  "), err

    @pytest.mark.parametrize("name", sorted(_EDGE_QUERIES) + ["children"])
    def test_an_unknown_address_is_null_and_an_error_in_json(self, name):
        code, out, err = _run(
            RETAIL, "query", name, "no/such#address", "--format", "json")
        assert (code, json.loads(out)) == (1, None)
        assert err.startswith("ERROR  <query>  "), err
        jsonschema.validate(
            None, json.loads(SCHEMA.read_text(encoding="utf-8")))

    def test_a_real_address_with_nothing_to_list_is_an_empty_array(self):
        code, out, err = _run(
            EXAMPLES / "gutenberg", "query", "cited-by",
            "gutenberg/corpus#Word Frequencies", "--format", "json")
        assert (code, json.loads(out), err) == (0, [], "")

    def test_a_node_with_no_file_has_a_blank_where(self):
        code, out, _ = _run(
            EXAMPLES / "ts-media", "query", "children",
            "ts/media#Binding#declaration#2", "--kind", "USES_EXTERNAL")
        assert code == 0
        assert out == "index.html\n"

    def test_the_format_is_checked(self):
        code, _, err = _run(RETAIL, "query", "search", "x",
                            "--format", "turtle")
        assert code == 2
        assert "invalid choice" in err


# ── --format json is what it was ─────────────────────────────

def _schema_node_list(doc) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(doc, {
        "$schema": schema["$schema"],
        "definitions": schema["definitions"],
        "$ref": "#/definitions/NodeList",
    })


def _json(fn, *args):
    rc, out, err = _query(fn, *args, fmt="json")
    assert err == ""
    return rc, json.loads(out)


@pytest.mark.parametrize("project", _projects(), ids=lambda p: p.name)
class TestJsonIsWhatItWas:
    """Each is checked against the graph's own answer, which the command
    printed before: a JSON array of node summaries."""

    def test_the_edge_queries(self, project, monkeypatch):
        graph = _in(project, monkeypatch)
        before = {
            "callers": lambda a: list(graph.parents(a, EdgeKind.USES)),
            "callees": lambda a: list(graph.children(a, EdgeKind.USES)),
            "cites": lambda a: cites_of(graph, a),
            "cited-by": lambda a: cited_by(graph, a),
            "imports": graph.imports_of,
            "imported-by": graph.imported_by,
        }
        for address in sorted({n.address for n in graph.nodes()}):
            for name, fn in _EDGE_QUERIES.items():
                rc, doc = _json(fn, address)
                assert rc == 0
                assert doc == [node_summary(n) for n in before[name](address)]
                _schema_node_list(doc)

    def test_children_and_search(self, project, monkeypatch):
        graph = _in(project, monkeypatch)
        for node in graph.nodes():
            for kind in ("CONTAINS", "USES"):
                rc, doc = _json(cmd_query_children, node.address, kind)
                assert rc == 0
                assert doc == [
                    node_summary(n)
                    for n in graph.children(node.address, EdgeKind[kind])]
        rc, doc = _json(cmd_query_search, "*")
        assert rc == 0
        _schema_node_list(doc)
        shown = [n for n in graph.nodes()
                 if not KINDS[n.kind].hidden_at_outline]
        assert [d["address"] for d in doc] == [n.address for n in shown]


# ── resolve is deprecated, and as it was ─────────────────────

class TestResolve:
    def test_it_answers_as_before_and_says_it_is_deprecated(self):
        code, out, err = _run(
            RETAIL, "query", "resolve", "Pricing Discounts")
        assert code == 0
        assert json.loads(out)["address"] == DISCOUNTS
        assert err == (
            "DEPRECATED  <query>  query resolve will be removed; "
            "use query search\n")

    def test_an_unresolved_name_is_null_and_exit_1(self):
        code, out, err = _run(RETAIL, "query", "resolve", "Nonesuch")
        assert (code, json.loads(out)) == (1, None)
        assert err.count("DEPRECATED") == 1

    def test_it_has_no_format(self):
        code, _, err = _run(
            RETAIL, "query", "resolve", "x", "--format", "json")
        assert code == 2
        assert "unrecognized arguments" in err

    def test_the_command_function_is_unchanged(self, monkeypatch):
        monkeypatch.chdir(RETAIL)
        rc, out, _ = _query(cmd_query_resolve, "Pricing Discounts")
        assert rc == 0
        assert json.loads(out)["address"] == DISCOUNTS


# ── The MCP tools answer in text ─────────────────────────────

class TestMcp:
    def _call(self, name: str, **arguments) -> dict:
        from notlob.mcp_server import _dispatch
        return _dispatch(name, arguments)

    def test_search_answers_in_text(self, monkeypatch):
        monkeypatch.chdir(RETAIL)
        result = self._call("notlob_query_search", pattern="apply_*")
        assert result["isError"] is False
        assert result["content"][0]["text"] == _render([
            ("", f"{DISCOUNTS}#apply_discount",
             f"{DISCOUNTS_LOB}:11")]).strip()

    def test_children_answer_in_text(self, monkeypatch):
        monkeypatch.chdir(RETAIL)
        result = self._call(
            "notlob_query_children", address=f"{DISCOUNTS}#Stacking Discounts")
        text = result["content"][0]["text"]
        assert not text.startswith("[")
        assert f"{DISCOUNTS}#Stacking Discounts#property#1" in text

    def test_imports_answer_in_text(self, monkeypatch):
        monkeypatch.chdir(GUTENBERG)
        result = self._call("notlob_query_imports", address=HAMLET)
        assert result["content"][0]["text"] == (
            f"gutenberg/corpus  {HAMLET_LOB}:87")
