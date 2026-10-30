"""notlob.mcp_server — zero-dependency MCP server (stdin/stdout).

Exposes notlob commands as MCP tools over the JSON-RPC 2.0 protocol.
No external dependencies beyond the Python stdlib and notlob itself.

Usage::

    notlob mcp          # starts the server on stdin/stdout
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

from notlob.graph import KINDS, EdgeKind, NodeKind

#: The edge kinds a graph holds, and the kinds of node ``outline`` shows:
#: what a query can be asked for.
_EDGE_KINDS = [k.name for k in EdgeKind]
_NODE_KINDS = [
    k.name for k in NodeKind if not KINDS[k].hidden_at_outline]


# ── Tool definitions ─────────────────────────────────────────

TOOLS = [
    {
        "name": "notlob_test",
        "description": (
            "Run all claims (examples, properties, #Tests) in a "
            "module or the whole project. Returns structured results "
            "with addresses, source lines, and pass/fail status."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Path to a .lob file; omit to test "
                        "the whole project"
                    ),
                },
                "only": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["lint", "examples", "props", "tests"],
                    },
                    "description": "Run only these check types",
                },
            },
        },
    },
    {
        "name": "notlob_check",
        "description": (
            "Run semantic consistency checks on the project "
            "name-graph: unused imports (error), typos, naming "
            "conventions, similar titles, unreferenced symbols."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "only": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "imports", "typos", "conventions",
                            "titles", "references",
                        ],
                    },
                    "description": "Run only these checks",
                },
            },
        },
    },
    {
        "name": "notlob_graph",
        "description": (
            "Export the package name-graph as JSON: all modules, "
            "subheadings, symbols, examples, tests, properties, "
            "and their relationships, at a level of detail."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "level": {
                    "type": ["string", "integer"],
                    "enum": ["outline", "index", "full", 1, 2, 3],
                    "description": (
                        "How much to show: outline (1, the default) is "
                        "every node but the paragraphs, code blocks and "
                        "bullet lists; index (2) adds those, the "
                        "references a paragraph holds and a size for each "
                        "node; full (3) adds the text, once"
                    ),
                },
            },
        },
    },
    {
        "name": "notlob_query_search",
        "description": (
            "Search nodes by label pattern (fnmatch). Bare words "
            "auto-wrap as *pattern* for substring matching."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "fnmatch pattern, e.g. '*discount*'",
                },
                "kind": {
                    "type": "string",
                    "enum": _NODE_KINDS,
                    "description": "Restrict to a node kind",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "notlob_query_content",
        "description": (
            "Show the source at a name-graph address, as written: a "
            "header line (address, file and lines) and the node's own "
            "lines. With format json, the subtree instead, nested, with "
            "the text of each node that holds text, once."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": (
                        "Node address, e.g. roman/numerals#to_roman"
                    ),
                },
                "format": {
                    "type": "string",
                    "enum": ["text", "json"],
                    "description": (
                        "text (the default): the source as written; "
                        "json: the subtree, nested"
                    ),
                },
                "depth": {
                    "type": "integer",
                    "minimum": 0,
                    "description": (
                        "With format json, stop this many containment "
                        "steps below the node (0: the node alone; "
                        "default: the whole subtree)"
                    ),
                },
            },
            "required": ["address"],
        },
    },
    {
        "name": "notlob_query_children",
        "description": "List direct children of a node.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Parent node address",
                },
                "kind": {
                    "type": "string",
                    "enum": _EDGE_KINDS,
                    "description": "Edge kind (default: CONTAINS)",
                },
            },
            "required": ["address"],
        },
    },
    {
        "name": "notlob_query_imports",
        "description": "List modules imported by an address.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Module address",
                },
            },
            "required": ["address"],
        },
    },
    {
        "name": "notlob_query_imported_by",
        "description": "List modules that import an address.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Module address",
                },
            },
            "required": ["address"],
        },
    },
]


# ── Dispatch ─────────────────────────────────────────────────

def _capture(fn, *args, **kwargs) -> tuple[str, int]:
    """Call *fn*, capture its stdout, return (output, exit_code)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(*args, **kwargs)
    return buf.getvalue(), rc


def _dispatch(name: str, arguments: dict) -> dict:
    """Execute an MCP tool call and return a result dict."""
    from notlob.commands import (
        cmd_check, cmd_graph, cmd_test,
        cmd_query_children, cmd_query_content,
        cmd_query_imports, cmd_query_imported_by,
        cmd_query_search,
    )

    try:
        if name == "notlob_test":
            path = (Path(arguments["path"]).resolve()
                    if "path" in arguments else None)
            only = (set(arguments["only"])
                    if "only" in arguments else None)
            out, rc = _capture(
                cmd_test, path, only=only, fmt="json",
            )
        elif name == "notlob_check":
            only = (set(arguments["only"])
                    if "only" in arguments else None)
            out, rc = _capture(
                cmd_check, only=only, fmt="json",
            )
        elif name == "notlob_graph":
            out, rc = _capture(cmd_graph, level=arguments.get("level"))
        elif name == "notlob_query_search":
            out, rc = _capture(
                cmd_query_search,
                arguments["pattern"],
                arguments.get("kind"),
            )
        elif name == "notlob_query_content":
            out, rc = _capture(
                cmd_query_content, arguments["address"],
                arguments.get("depth"), arguments.get("format", "text"),
            )
        elif name == "notlob_query_children":
            out, rc = _capture(
                cmd_query_children,
                arguments["address"],
                arguments.get("kind", "CONTAINS"),
            )
        elif name == "notlob_query_imports":
            out, rc = _capture(
                cmd_query_imports, arguments["address"],
            )
        elif name == "notlob_query_imported_by":
            out, rc = _capture(
                cmd_query_imported_by, arguments["address"],
            )
        else:
            return {
                "content": [{"type": "text",
                             "text": f"Unknown tool: {name}"}],
                "isError": True,
            }
    except Exception as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "isError": True,
        }

    return {
        "content": [{"type": "text", "text": out.strip()}],
        "isError": rc != 0,
    }


# ── JSON-RPC server ──────────────────────────────────────────

_SERVER_INFO = {"name": "notlob", "version": "0.3"}
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
