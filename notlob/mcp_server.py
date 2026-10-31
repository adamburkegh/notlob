"""notlob.mcp_server — zero-dependency MCP server (stdin/stdout).

Exposes notlob commands as MCP tools over the JSON-RPC 2.0 protocol.
A tool is a command: it answers as the command does, by default in text,
and with ``format`` in what the command offers. No external dependencies
beyond the Python stdlib and notlob itself.

Usage::

    notlob mcp          # starts the server on stdin/stdout
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Callable, NamedTuple

from notlob import __version__
from notlob.check import CHECK_NAMES
from notlob.commands import (
    GRAPH_FORMATS, QUERY_EDGE_KINDS, QUERY_FORMATS, QUERY_NODE_KINDS,
    cmd_check, cmd_graph, cmd_test,
    cmd_query_callees, cmd_query_callers, cmd_query_children,
    cmd_query_cited_by, cmd_query_cites, cmd_query_content,
    cmd_query_imported_by, cmd_query_imports, cmd_query_search,
)


# ── Tool definitions ─────────────────────────────────────────

class _Tool(NamedTuple):
    """A command offered as a tool. Its name is the command line:
    ``query cited-by`` is ``notlob_query_cited_by``. Its *properties* are
    the options and arguments of that command, under the name the command
    gives them but for ``path``, its file."""
    command:     tuple[str, ...]
    run:         Callable[..., int]
    description: str
    properties:  dict[str, dict]
    required:    tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return "notlob_" + "_".join(self.command).replace("-", "_")


def _format(choices: tuple[str, ...], what: str) -> dict:
    return {
        "type": "string",
        "enum": list(choices),
        "description": f"text (the default): {what}; the rest are for a "
                       "program",
    }


_ADDRESS = {
    "type": "string",
    "description": "Node address, e.g. roman/numerals#to_roman",
}
_MODULE = {
    "type": "string",
    "description": "Module address, e.g. roman/numerals",
}

#: A query that lists nodes answers a line a node: a sigil, the address,
#: and ``file:line``; with ``format`` json, an array of nodes.
_LISTS = "a line a node (sigil, address, file:line)"


def _lists(**properties: dict) -> dict[str, dict]:
    return {**properties, "format": _format(QUERY_FORMATS, _LISTS)}


_TOOL_LIST = [
    _Tool(
        ("test",), cmd_test,
        "Run all claims (examples, properties, #Tests) in a module or the "
        "whole project. Answers in text, a line a claim: its status, file "
        "and line, address and source, then the count; format json for "
        "the claims as structured data.",
        {
            "path": {
                "type": "string",
                "description": (
                    "Path to a .lob file; omit to test the whole project"),
            },
            "only": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["lint", "examples", "props", "tests"],
                },
                "description": "Run only these check types",
            },
            "format": _format(
                ("text", "json"), "a line a claim and the count"),
        },
    ),
    _Tool(
        ("check",), cmd_check,
        "Run semantic consistency checks on the project name-graph: "
        "unused imports (error), typos, naming conventions, similar "
        "titles, unreferenced symbols. Answers in text, a line a finding, "
        "or one line when there are none; format json for the findings "
        "as structured data.",
        {
            "only": {
                "type": "array",
                "items": {"type": "string", "enum": list(CHECK_NAMES)},
                "description": "Run only these checks",
            },
            "format": _format(("text", "json"), "a line a finding"),
        },
    ),
    _Tool(
        ("graph",), cmd_graph,
        "Show the package name-graph. Answers in text: each file, then "
        "its headings, symbols and claims, indented by what is written in "
        "what, with the line each is on. The level outline is the default; "
        "index adds the uses, cites and imports and the declarations "
        "under the node that holds them; full is each file's source. "
        "With format json, the graph itself: nodes and edges, at the "
        "same level; turtle gives it as RDF.",
        {
            "level": {
                "type": ["string", "integer"],
                "enum": ["outline", "index", "full", 1, 2, 3],
                "description": (
                    "How much to show: outline (1, the default) is the "
                    "structure of each file; index (2) adds the uses, "
                    "cites and imports, and the declarations; full (3) "
                    "is each file's source (text), or adds the text, "
                    "once (json, turtle)"
                ),
            },
            "format": _format(
                GRAPH_FORMATS, "each file's outline, a line a node"),
        },
    ),
    _Tool(
        ("query", "search"), cmd_query_search,
        "Search nodes by label pattern (fnmatch); bare words auto-wrap "
        "as *pattern* for substring matching. Answers in text, "
        + _LISTS + "; format json for an array of nodes.",
        _lists(
            pattern={
                "type": "string",
                "description": "fnmatch pattern, e.g. '*discount*'",
            },
            kind={
                "type": "string",
                "enum": list(QUERY_NODE_KINDS),
                "description": "Restrict to a node kind",
            },
        ),
        ("pattern",),
    ),
    _Tool(
        ("query", "content"), cmd_query_content,
        "Show the source at a name-graph address, as written. Answers in "
        "text: a header line (address, file and lines) and the node's own "
        "lines; format json for the subtree instead, nested, with the "
        "text of each node that holds text, once.",
        {
            "address": _ADDRESS,
            "format": _format(
                QUERY_FORMATS, "the header and the node's lines"),
            "depth": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "With format json, stop this many containment steps "
                    "below the node (0: the node alone; default: the "
                    "whole subtree)"
                ),
            },
        },
        ("address",),
    ),
    _Tool(
        ("query", "children"), cmd_query_children,
        "List the targets of the edges of a kind from a node: its "
        "children by default. Answers in text, " + _LISTS
        + "; format json for an array of nodes.",
        _lists(
            address={"type": "string", "description": "Parent node address"},
            kind={
                "type": "string",
                "enum": list(QUERY_EDGE_KINDS),
                "description": "Edge kind (default: CONTAINS)",
            },
        ),
        ("address",),
    ),
    _Tool(
        ("query", "imports"), cmd_query_imports,
        "List the modules a module imports. Answers in text, " + _LISTS
        + ", the line being the listing that imports it; format json for "
        "an array of nodes.",
        _lists(address=_MODULE),
        ("address",),
    ),
    _Tool(
        ("query", "imported-by"), cmd_query_imported_by,
        "List the modules that import a module. Answers in text, "
        + _LISTS + ", the line being the listing that imports it; "
        "format json for an array of nodes.",
        _lists(address=_MODULE),
        ("address",),
    ),
    _Tool(
        ("query", "callers"), cmd_query_callers,
        "List the nodes that use a symbol. Answers in text, " + _LISTS
        + ", the line being where it is used; format json for an array "
        "of nodes.",
        _lists(address=_ADDRESS),
        ("address",),
    ),
    _Tool(
        ("query", "callees"), cmd_query_callees,
        "List the nodes a node uses. Answers in text, " + _LISTS
        + ", the line being where it is used; format json for an array "
        "of nodes.",
        _lists(address=_ADDRESS),
        ("address",),
    ),
    _Tool(
        ("query", "cites"), cmd_query_cites,
        "List the nodes a node cites in its prose with #Label. Answers in "
        "text, " + _LISTS + ", the line being the citation; format json "
        "for an array of nodes.",
        _lists(address=_ADDRESS),
        ("address",),
    ),
    _Tool(
        ("query", "cited-by"), cmd_query_cited_by,
        "List the nodes whose prose cites a node. Answers in text, "
        + _LISTS + ", the line being the first citation; format json "
        "for an array of nodes.",
        _lists(address=_ADDRESS),
        ("address",),
    ),
]

_BY_NAME = {tool.name: tool for tool in _TOOL_LIST}

TOOLS = [
    {
        "name": tool.name,
        "description": tool.description,
        "inputSchema": {
            "type": "object",
            "properties": tool.properties,
            **({"required": list(tool.required)} if tool.required else {}),
        },
    }
    for tool in _TOOL_LIST
]


# ── Dispatch ─────────────────────────────────────────────────

#: How a tool's argument reaches its command: the keyword the command
#: has it as, and what the value is made into.
_ARGUMENT: dict[str, tuple[str, Callable]] = {
    "path":   ("path",     lambda p: Path(p).resolve()),
    "only":   ("only",     set),
    "kind":   ("kind_str", str),
    "format": ("fmt",      str),
}


def _capture(fn, *args, **kwargs) -> tuple[str, str, int]:
    """Call *fn*, capture its stdout and its stderr, return (output,
    errors, exit_code). The stdout capture has a ``buffer`` as the real
    one does, for a command that writes bytes (``graph`` as Turtle)."""
    raw = io.BytesIO()
    out = io.TextIOWrapper(raw, encoding="utf-8", newline="")
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*args, **kwargs)
    out.flush()
    return raw.getvalue().decode("utf-8"), err.getvalue(), rc


def _error(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": True}


def _dispatch(name: str, arguments: dict) -> dict:
    """Execute an MCP tool call and return a result dict."""
    tool = _BY_NAME.get(name)
    if tool is None:
        return _error(f"Unknown tool: {name}")
    missing = [a for a in tool.required if a not in arguments]
    if missing:
        return _error(f"Missing argument: {', '.join(missing)}")
    kwargs = {}
    for argument in tool.properties:
        if argument in arguments:
            keyword, make = _ARGUMENT.get(argument, (argument, None))
            value = arguments[argument]
            kwargs[keyword] = value if make is None else make(value)
    try:
        out, err, rc = _capture(tool.run, **kwargs)
    except Exception as exc:
        return _error(str(exc))
    # What the command printed, then what it said on stderr: a client
    # reads the answer (``null``, say) and the reason beside it. An empty
    # answer is an answer, so there is always a block.
    blocks = [text for text in (out.rstrip(), err.rstrip()) if text]
    return {
        "content": [{"type": "text", "text": text}
                    for text in blocks or [""]],
        "isError": rc != 0,
    }


# ── JSON-RPC server ──────────────────────────────────────────

_SERVER_INFO = {"name": "notlob", "version": __version__}
_CAPABILITIES = {"tools": {}}


def _handle(msg: dict) -> dict | None:
    """Handle one JSON-RPC message. Return response or None."""
    method = msg.get("method", "")
    msg_id = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2025-03-26",
                "serverInfo": _SERVER_INFO,
                "capabilities": _CAPABILITIES,
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOLS},
        }

    if method == "tools/call":
        params = msg.get("params", {})
        result = _dispatch(
            params.get("name", ""),
            params.get("arguments", {}),
        )
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result,
        }

    if msg_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}",
            },
        }

    return None


def run_server() -> None:
    """Run the MCP server on stdin/stdout."""
    from notlob.commands import use_utf8_streams
    use_utf8_streams(sys.stdin, sys.stdout, sys.stderr)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = _handle(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
