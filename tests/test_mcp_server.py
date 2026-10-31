"""The MCP server is a thin layer over the commands.

A tool answers as its command does: the same defaults, so ``test``,
``check`` and ``graph`` answer in text unless asked, and the same
``format`` choices. No tool lists an argument its command does not take;
the commands' options are read from the parser in ``cli.py``. These run the
server as a subprocess, over the protocol, as a client does.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest

import notlob
import notlob.cli
from notlob.mcp_server import TOOLS

ROOT = Path(__file__).parent.parent
RETAIL = ROOT / "examples" / "retail"
GUTENBERG = ROOT / "examples" / "gutenberg"

DISCOUNTS = "pricing/discounts"
HAMLET = "gutenberg/hamlet"
CORPUS = "gutenberg/corpus"

#: A tool's argument, where the command calls it something else: the
#: command's file is a positional.
_ARGUMENT_OF_COMMAND = {"path": "file"}


@cache
def _notlob(directory: Path, *args: str, stdin: str = "") -> tuple[
        int, str, str]:
    """``(exit code, stdout, stderr)`` of ``notlob -C directory *args``
    from the repository root."""
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    proc = subprocess.run(
        [sys.executable, "-m", "notlob.cli", "-C", str(directory), *args],
        cwd=ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", input=stdin)
    return proc.returncode, proc.stdout, proc.stderr


def _request(method: str, **params) -> str:
    return json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
    }) + "\n"


def _serve(directory: Path, tool: str, **arguments) -> tuple[
        list[str], bool, str]:
    """The text blocks and the error flag a client gets from *tool*, over
    the protocol from the server started in *directory*, and what the
    server itself wrote to stderr."""
    code, out, err = _notlob(
        directory, "mcp",
        stdin=_request("tools/call", name=tool, arguments=arguments))
    assert code == 0, err
    result = json.loads(out)["result"]
    assert {c["type"] for c in result["content"]} == {"text"}
    return [c["text"] for c in result["content"]], result["isError"], err


def _blocks(directory: Path, tool: str, **arguments) -> tuple[
        list[str], bool]:
    """Every text block a client gets from *tool*, and the error flag."""
    blocks, failed, _ = _serve(directory, tool, **arguments)
    return blocks, failed


def _call(directory: Path, tool: str, **arguments) -> tuple[str, bool]:
    """The text and the error flag a client gets from *tool*, when it
    answers in one block."""
    blocks, failed = _blocks(directory, tool, **arguments)
    assert len(blocks) == 1, blocks
    return blocks[0], failed


def _command(directory: Path, *args: str) -> tuple[str, bool]:
    """What the command prints, less its final newline as the server
    gives it, and whether it failed."""
    code, out, _ = _notlob(directory, *args)
    return out.rstrip(), code != 0


#: (tool, its arguments, the command line it stands for, the project):
#: each tool, over an example where it has something to say.
CASES = [
    ("notlob_test", {}, ["test"], RETAIL),
    ("notlob_test", {"path": "pricing/discounts.lob"},
     ["test", "pricing/discounts.lob"], RETAIL),
    ("notlob_test", {"only": ["examples", "props"]},
     ["test", "--only", "examples", "props"], RETAIL),
    ("notlob_check", {}, ["check"], RETAIL),
    ("notlob_check", {"only": ["imports"]},
     ["check", "--only", "imports"], GUTENBERG),
    ("notlob_graph", {}, ["graph"], RETAIL),
    ("notlob_graph", {"level": "index"},
     ["graph", "--level", "index"], GUTENBERG),
    ("notlob_query_search", {"pattern": "apply_*"},
     ["query", "search", "apply_*"], RETAIL),
    ("notlob_query_search", {"pattern": "load", "kind": "SYMBOL"},
     ["query", "search", "load", "--kind", "SYMBOL"], GUTENBERG),
    ("notlob_query_content", {"address": f"{DISCOUNTS}#apply_discount"},
     ["query", "content", f"{DISCOUNTS}#apply_discount"], RETAIL),
    ("notlob_query_children", {"address": f"{DISCOUNTS}#Stacking Discounts"},
     ["query", "children", f"{DISCOUNTS}#Stacking Discounts"], RETAIL),
    ("notlob_query_children",
     {"address": f"{DISCOUNTS}#Stacking Discounts", "kind": "USES"},
     ["query", "children", f"{DISCOUNTS}#Stacking Discounts",
      "--kind", "USES"], RETAIL),
    ("notlob_query_imports", {"address": HAMLET},
     ["query", "imports", HAMLET], GUTENBERG),
    ("notlob_query_imported_by", {"address": CORPUS},
     ["query", "imported-by", CORPUS], GUTENBERG),
    ("notlob_query_callers", {"address": f"{DISCOUNTS}#apply_discount"},
     ["query", "callers", f"{DISCOUNTS}#apply_discount"], RETAIL),
    ("notlob_query_callees", {"address": f"{HAMLET}#report"},
     ["query", "callees", f"{HAMLET}#report"], GUTENBERG),
    ("notlob_query_cites", {"address": DISCOUNTS},
     ["query", "cites", DISCOUNTS], RETAIL),
    ("notlob_query_cited_by", {"address": f"{DISCOUNTS}#Stacking Discounts"},
     ["query", "cited-by", f"{DISCOUNTS}#Stacking Discounts"], RETAIL),
]


def _id(case) -> str:
    tool, arguments, _, project = case
    return f"{project.name}-{tool}-{'-'.join(map(str, arguments.values()))}"


# ── A tool answers as its command does ───────────────────────

@pytest.mark.parametrize("case", CASES, ids=_id)
class TestAnswersAsTheCommandDoes:
    def test_by_default_in_text(self, case):
        tool, arguments, argv, project = case
        assert _call(project, tool, **arguments) == _command(project, *argv)

    def test_with_format_json_in_json(self, case):
        tool, arguments, argv, project = case
        got = _call(project, tool, **arguments, format="json")
        assert got == _command(project, *argv, "--format", "json")
        json.loads(got[0])


def _said(fn, *args, **kwargs) -> str:
    """What the command function *fn* writes to stderr, run from the
    retail project, less its final newline."""
    errors = io.StringIO()
    here = os.getcwd()
    os.chdir(RETAIL)
    try:
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(errors):
            fn(*args, **kwargs)
    finally:
        os.chdir(here)
    return errors.getvalue().rstrip()


NO_SUCH = f"{DISCOUNTS}#no_such"


class TestAToolLosesNothingItsCommandSays:
    def test_an_unknown_address_gives_the_reason(self):
        reason = _notlob(RETAIL, "query", "callers", NO_SUCH)[2].rstrip()
        assert reason.startswith("ERROR  <query>  ")
        assert _blocks(RETAIL, "notlob_query_callers", address=NO_SUCH) == (
            [reason], True)

    def test_in_json_the_answer_is_still_null_and_the_reason_beside(self):
        reason = _notlob(
            RETAIL, "query", "callers", NO_SUCH, "--format", "json")[
            2].rstrip()
        blocks, failed = _blocks(
            RETAIL, "notlob_query_callers", address=NO_SUCH, format="json")
        assert (blocks, failed) == (["null", reason], True)
        assert json.loads(blocks[0]) is None

    def test_the_reason_is_not_left_on_the_servers_stderr(self):
        _, _, err = _serve(RETAIL, "notlob_query_callers", address=NO_SUCH)
        assert err == ""

    def test_an_unknown_level_says_so(self):
        from notlob.commands import cmd_graph
        reason = _said(cmd_graph, level="bogus")
        assert reason.startswith("ERROR  <graph>  ")
        assert _blocks(RETAIL, "notlob_graph", level="bogus") == (
            [reason], True)

    def test_an_unknown_kind_says_so(self):
        from notlob.commands import cmd_query_search
        reason = _said(cmd_query_search, "x", "BOGUS")
        assert "BOGUS" in reason
        assert _blocks(
            RETAIL, "notlob_query_search", pattern="x", kind="BOGUS") == (
            [reason], True)

    def test_a_missing_file_is_stdout_then_the_reason(self):
        _, out, _ = _notlob(RETAIL, "test", "no/such.lob")
        blocks, failed = _blocks(
            RETAIL, "notlob_test", path="no/such.lob")
        assert failed
        assert len(blocks) == 2
        assert blocks[0] == out.rstrip() == "\n0 passed, 1 failed"
        assert blocks[1].startswith("ERROR  <parse>  ")
        assert "such.lob" in blocks[1]

    def test_an_empty_answer_is_one_empty_block(self):
        assert _blocks(
            GUTENBERG, "notlob_query_cited_by",
            address=f"{CORPUS}#Word Frequencies") == ([""], False)


class TestStderrOnASuccessIsCarriedNotAnError:
    def _with(self, monkeypatch, run):
        from notlob import mcp_server
        tool = mcp_server._BY_NAME["notlob_check"]
        monkeypatch.setitem(
            mcp_server._BY_NAME, tool.name, tool._replace(run=run))
        return mcp_server._dispatch("notlob_check", {})

    def test_a_warning_beside_the_answer(self, monkeypatch):
        def run(**_):
            print("answer")
            print("WARN  <check>  careful", file=sys.stderr)
            return 0
        result = self._with(monkeypatch, run)
        assert result == {
            "content": [{"type": "text", "text": "answer"},
                        {"type": "text", "text": "WARN  <check>  careful"}],
            "isError": False,
        }

    def test_only_a_reason_is_the_only_block(self, monkeypatch):
        def run(**_):
            print("ERROR  <check>  no", file=sys.stderr)
            return 1
        result = self._with(monkeypatch, run)
        assert result["content"] == [
            {"type": "text", "text": "ERROR  <check>  no"}]
        assert result["isError"] is True


class TestTheFirstLineKeepsItsColumns:
    def test_a_blank_sigil_column_is_kept(self):
        """The first row of this answer has no sigil: its address starts
        after the blank column, as the command prints it."""
        text, _ = _call(RETAIL, "notlob_query_search", pattern="*")
        first = text.splitlines()[0]
        assert first.startswith(" ")
        assert text == _command(RETAIL, "query", "search", "*")[0]
        assert first == _notlob(
            RETAIL, "query", "search", "*")[1].splitlines()[0]


class TestTheDefaultsAreTheCommandsOwn:
    @pytest.mark.parametrize("tool, argv", [
        ("notlob_test", ["test"]),
        ("notlob_check", ["check"]),
        ("notlob_graph", ["graph"]),
    ])
    def test_a_reader_is_not_given_json(self, tool, argv):
        text, _ = _call(RETAIL, tool)
        with pytest.raises(ValueError):
            json.loads(text)
        assert text == _command(RETAIL, *argv)[0]

    def test_graph_asks_for_turtle(self):
        got = _call(RETAIL, "notlob_graph", format="turtle")
        assert got == _command(RETAIL, "graph", "--format", "turtle")
        assert "@prefix" in got[0]


# ── Every tool is held to its command's options ──────────────

def _parser() -> argparse.ArgumentParser:
    """The parser ``main`` builds in ``cli.py``, taken as it is about to
    parse, so that what is tested is what a person types against."""

    class Taken(Exception):
        pass

    def take(self, *args, **kwargs):
        raise Taken(self)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(argparse.ArgumentParser, "parse_args", take)
        patch.setattr(sys, "argv", ["notlob"])
        with pytest.raises(Taken) as taken:
            notlob.cli.main()
    return taken.value.args[0]


def _subcommands(parser: argparse.ArgumentParser) -> dict:
    action = next(a for a in parser._actions
                  if isinstance(a, argparse._SubParsersAction))
    return action.choices


def _command_parser(command: tuple[str, ...]) -> argparse.ArgumentParser:
    found = _parser()
    for word in command:
        found = _subcommands(found)[word]
    return found


def _command_of(tool: str) -> tuple[str, ...]:
    """The command line a tool is named for: ``notlob_query_cited_by`` is
    ``query cited-by``."""
    name = tool.removeprefix("notlob_")
    if name.startswith("query_"):
        return ("query", name.removeprefix("query_").replace("_", "-"))
    return (name,)


def _options(parser: argparse.ArgumentParser) -> dict[str, argparse.Action]:
    """What a command takes, by the name a tool gives it: its positionals,
    and its options without the dashes."""
    options = {}
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        if action.option_strings:
            name = max(action.option_strings, key=len).removeprefix("--")
        else:
            name = action.dest
        options[name] = action
    return options


def _names() -> list[str]:
    return [t["name"] for t in TOOLS]


class TestEveryToolIsHeldToItsCommand:
    @pytest.mark.parametrize("tool", _names())
    def test_the_command_exists(self, tool):
        assert _command_parser(_command_of(tool)) is not None

    @pytest.mark.parametrize("tool", _names())
    def test_it_lists_only_arguments_the_command_takes(self, tool):
        schema = next(t for t in TOOLS if t["name"] == tool)["inputSchema"]
        taken = _options(_command_parser(_command_of(tool)))
        for name in schema["properties"]:
            assert _ARGUMENT_OF_COMMAND.get(name, name) in taken, name

    @pytest.mark.parametrize("tool", _names())
    def test_it_requires_what_the_command_requires(self, tool):
        schema = next(t for t in TOOLS if t["name"] == tool)["inputSchema"]
        taken = _options(_command_parser(_command_of(tool)))
        required = {name for name, action in taken.items()
                    if not action.option_strings and action.nargs is None}
        asked = {_ARGUMENT_OF_COMMAND.get(n, n)
                 for n in schema.get("required", [])}
        assert asked == required

    @pytest.mark.parametrize("tool", _names())
    def test_it_offers_the_choices_the_command_has(self, tool):
        schema = next(t for t in TOOLS if t["name"] == tool)["inputSchema"]
        taken = _options(_command_parser(_command_of(tool)))
        for name, prop in schema["properties"].items():
            action = taken[_ARGUMENT_OF_COMMAND.get(name, name)]
            choices = prop.get("enum") or prop.get("items", {}).get("enum")
            if action.choices is not None and choices is not None:
                assert list(choices) == list(action.choices), name

    @pytest.mark.parametrize("tool", _names())
    def test_it_takes_a_format_if_the_command_does(self, tool):
        schema = next(t for t in TOOLS if t["name"] == tool)["inputSchema"]
        taken = _options(_command_parser(_command_of(tool)))
        assert ("format" in taken) == ("format" in schema["properties"])
        if "format" in taken:
            assert (schema["properties"]["format"]["enum"]
                    == list(taken["format"].choices))

    def test_graph_keeps_its_level(self):
        schema = next(t for t in TOOLS
                      if t["name"] == "notlob_graph")["inputSchema"]
        assert "level" in schema["properties"]


class TestEveryQueryButResolveIsATool:
    def test_each_has_one(self):
        queries = set(_subcommands(_command_parser(("query",))))
        offered = {_command_of(t)[1] for t in _names()
                   if _command_of(t)[0] == "query"}
        assert queries - {"resolve"} == offered

    def test_resolve_is_not_offered(self):
        assert "notlob_query_resolve" not in _names()

    def test_the_names_are_unique(self):
        assert len(set(_names())) == len(_names())

    @pytest.mark.parametrize("tool", [
        "notlob_query_callers", "notlob_query_callees",
        "notlob_query_cites", "notlob_query_cited_by",
    ])
    def test_the_new_ones_are_listed_over_the_protocol(self, tool):
        code, out, _ = _notlob(RETAIL, "mcp", stdin=_request("tools/list"))
        assert code == 0
        listed = [t["name"] for t in json.loads(out)["result"]["tools"]]
        assert tool in listed


# ── What a description says ──────────────────────────────────

class TestDescriptionsSayWhatComesBack:
    @pytest.mark.parametrize("tool", _names())
    def test_it_says_text_and_json(self, tool):
        description = next(
            t for t in TOOLS if t["name"] == tool)["description"].lower()
        assert "text" in description
        assert "json" in description

    @pytest.mark.parametrize("tool", _names())
    def test_it_does_not_promise_what_it_no_longer_does(self, tool):
        description = next(
            t for t in TOOLS if t["name"] == tool)["description"].lower()
        assert "structured results" not in description
        assert not description.startswith("export")

    def test_graph_says_outline_is_the_default(self):
        description = next(
            t for t in TOOLS if t["name"] == "notlob_graph")["description"]
        words = " ".join(description.split())
        assert "outline" in words and "default" in words
        for reference in ("uses", "cites", "imports"):
            assert reference in words
        assert "index" in words

    def test_the_nodes_come_one_a_line(self):
        description = next(
            t for t in TOOLS
            if t["name"] == "notlob_query_callers")["description"]
        assert "line" in description


# ── The server is notlob's ───────────────────────────────────

class TestTheServerVersion:
    def test_it_is_notlobs(self):
        code, out, _ = _notlob(RETAIL, "mcp", stdin=_request("initialize"))
        assert code == 0
        info = json.loads(out)["result"]["serverInfo"]
        assert info == {"name": "notlob", "version": notlob.__version__}
