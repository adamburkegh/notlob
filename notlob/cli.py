"""notlob.cli — command-line interface.

Entry points
------------
notlob run <file>    Assemble and execute a .lob file.  No claim
                     checking; this runs the program.
notlob test <file>   Run all claims (examples, properties, #Tests)
                     and report results.  Exit 1 if any fail.
lob <file>           Thin alias: equivalent to ``notlob run <file>``.

Command implementations live in :mod:`notlob.commands`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from notlob.commands import (
    cmd_graph, cmd_run, cmd_test,
    cmd_query_children, cmd_query_resolve, cmd_query_search,
    cmd_query_imports, cmd_query_imported_by,
)
from notlob.project import find_project_root, resolve_module_path


def _resolve_path(file_or_addr: str, module_mode: bool) -> Path:
    """Resolve the CLI argument to a ``.lob`` path.

    Without ``-m``: treat the argument as a filesystem path (CWD-relative).
    With ``-m``: treat it as a module address, find the project root from
    CWD, and resolve the address to a path under that root.

    Exits with a helpful message if the project root cannot be found.
    """
    if not module_mode:
        return Path(file_or_addr)
    root = find_project_root(Path.cwd())
    if root is None:
        print(
            "ERROR  <project>  no binding.lob found — "
            "cannot resolve module address",
            file=sys.stderr,
        )
        sys.exit(1)
    return resolve_module_path(file_or_addr, root)


def _add_file_arg(p) -> None:
    """Add the shared file/address positional and -m flag to a subparser."""
    p.add_argument(
        "file",
        help="path to .lob file, or module address when -m is used",
    )
    p.add_argument(
        "-m", "--module",
        dest="module_mode",
        action="store_true",
        default=False,
        help=(
            "treat argument as a module address (e.g. roman/numerals) "
            "resolved relative to the project root"
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="notlob",
        description="Notlob literate-program runner.",
    )
    sub = parser.add_subparsers(dest="command", metavar="command")

    run_p = sub.add_parser("run", help="assemble and execute a .lob file")
    _add_file_arg(run_p)

    test_p = sub.add_parser("test", help="run all claims in a .lob file")
    _add_file_arg(test_p)

    graph_p = sub.add_parser(
        "graph", help="export the package name-graph as JSON"
    )
    _add_file_arg(graph_p)

    query_p = sub.add_parser(
        "query", help="query the package name-graph"
    )
    qsub = query_p.add_subparsers(dest="query_op", metavar="operation")

    qc = qsub.add_parser("children", help="list direct children of a node")
    qc.add_argument("address")
    qc.add_argument(
        "--kind", default="CONTAINS",
        choices=["CONTAINS", "DEFINES", "IMPORTS"],
        help="edge kind to follow (default: CONTAINS)",
    )

    qr = qsub.add_parser("resolve", help="resolve a #label reference")
    qr.add_argument("label")
    qr.add_argument(
        "--context", metavar="ADDRESS",
        help="module address for resolution context",
    )

    qs = qsub.add_parser("search", help="search nodes by label pattern")
    qs.add_argument("pattern", help="fnmatch-style pattern, e.g. '*discount*'")
    qs.add_argument(
        "--kind", default=None,
        choices=["MODULE", "SUBHEADING", "SYMBOL", "PROPERTY"],
        help="restrict to a node kind",
    )

    qi = qsub.add_parser("imports", help="list modules imported by an address")
    qi.add_argument("address")

    qib = qsub.add_parser(
        "imported-by", help="list modules that import an address"
    )
    qib.add_argument("address")

    args = parser.parse_args()

    if args.command == "run":
        sys.exit(cmd_run(_resolve_path(args.file, args.module_mode)))
    elif args.command == "test":
        sys.exit(cmd_test(_resolve_path(args.file, args.module_mode)))
    elif args.command == "graph":
        sys.exit(cmd_graph(_resolve_path(args.file, args.module_mode)))
    elif args.command == "query":
        op = getattr(args, "query_op", None)
        if op == "children":
            sys.exit(cmd_query_children(args.address, args.kind))
        elif op == "resolve":
            sys.exit(cmd_query_resolve(args.label, args.context))
        elif op == "search":
            sys.exit(cmd_query_search(args.pattern, args.kind))
        elif op == "imports":
            sys.exit(cmd_query_imports(args.address))
        elif op == "imported-by":
            sys.exit(cmd_query_imported_by(args.address))
        else:
            query_p.print_help()
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


def lob_main() -> None:
    """Thin alias: ``lob <file>`` is ``notlob run <file>``."""
    sys.argv = ["notlob", "run"] + sys.argv[1:]
    main()


if __name__ == "__main__":
    main()
