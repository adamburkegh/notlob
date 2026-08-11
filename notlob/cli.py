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

from notlob import __version__
from notlob.commands import (
    cmd_build, cmd_check, cmd_docs, cmd_graph, cmd_init, cmd_new,
    cmd_run, cmd_test, cmd_weave,
    cmd_query_children, cmd_query_content, cmd_query_resolve,
    cmd_query_search, cmd_query_imports, cmd_query_imported_by,
    cmd_query_callers, cmd_query_callees,
    cmd_query_references, cmd_query_referenced_by,
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
        return Path(file_or_addr).resolve()
    root = find_project_root(Path.cwd())
    if root is None:
        print(
            "ERROR  <project>  no binding.lob found — "
            "cannot resolve module address",
            file=sys.stderr,
        )
        sys.exit(1)
    return resolve_module_path(file_or_addr, root)


def _add_file_arg(p, required: bool = True) -> None:
    """Add the shared file/address positional and -m flag to a subparser.

    When *required* is False the file argument is optional; omitting it
    causes the command to operate on the entire project (CWD-based
    discovery).
    """
    p.add_argument(
        "file",
        nargs=None if required else "?",
        default=None,
        help=(
            "path to .lob file, or module address when -m is used; "
            "omit to operate on the whole project"
            if not required else
            "path to .lob file, or module address when -m is used"
        ),
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
        description="Notlob literate programming toolkit.",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = parser.add_subparsers(dest="command", metavar="command")

    run_p = sub.add_parser("run", help="assemble and execute a .lob file")
    _add_file_arg(run_p)
    run_p.add_argument(
        "--keep-generated-src", metavar="PATH", default=None,
        help=(
            "write generated source file(s) to this directory "
            "(overrides ~keep-generated-src in binding.lob)"
        ),
    )
    run_p.add_argument(
        "program_args", nargs=argparse.REMAINDER,
        help="arguments forwarded to the program as sys.argv[1:]",
    )

    test_p = sub.add_parser(
        "test",
        help="run all claims in a .lob file, or the whole project",
    )
    _add_file_arg(test_p, required=False)
    test_p.add_argument(
        "--keep-generated-src", metavar="PATH", default=None,
        help=(
            "write generated source file(s) to this directory "
            "(overrides ~keep-generated-src in binding.lob)"
        ),
    )
    test_p.add_argument(
        "--only",
        nargs="+",
        choices=["lint", "examples", "props", "tests"],
        default=None,
        metavar="CHECK",
        help=(
            "run only the listed check types "
            "(choices: lint, examples, props, tests; default: all)"
        ),
    )
    test_p.add_argument(
        "--json", dest="json_mode", action="store_true", default=False,
        help="output results as JSON",
    )

    build_p = sub.add_parser(
        "build",
        help="assemble a .lob file (or the whole project) to source artifacts",
    )
    _add_file_arg(build_p, required=False)
    build_p.add_argument(
        "--output", "-o", metavar="DIR", default="dist",
        help="output directory (default: dist/)",
    )
    build_p.add_argument(
        "--skip-tests", action="store_true", default=False,
        help="skip claim verification before building",
    )

    weave_p = sub.add_parser(
        "weave",
        help="render a .lob file (or the whole project) as Markdown",
    )
    _add_file_arg(weave_p, required=False)
    weave_p.add_argument(
        "--language", default=None, metavar="LANG",
        help=(
            "fenced-code language tag (default: from binding.lob "
            "or 'python')"
        ),
    )

    graph_p = sub.add_parser(
        "graph",
        help="export the package name-graph (JSON or Turtle RDF)",
    )
    _add_file_arg(graph_p, required=False)
    graph_p.add_argument(
        "--content", action="store_true", default=False,
        help="include source content (prose/code) on every node",
    )
    graph_p.add_argument(
        "--format", "-f", default="json",
        choices=["json", "turtle"],
        help="output format (default: json)",
    )

    query_p = sub.add_parser(
        "query", help="query the package name-graph"
    )
    qsub = query_p.add_subparsers(dest="query_op", metavar="operation")

    check_p = sub.add_parser(
        "check",
        help="run semantic checks on the project name-graph",
    )
    check_p.add_argument(
        "--only", nargs="+",
        choices=["imports", "typos", "conventions", "titles", "references",
                 "style"],
        default=None, metavar="CHECK",
        help="run only the listed checks (default: all)",
    )
    check_p.add_argument(
        "--verbose", "-v", action="store_true", default=False,
        help="show which checks ran and their counts",
    )
    check_p.add_argument(
        "--json", dest="json_mode", action="store_true", default=False,
        help="output findings as JSON",
    )

    init_p = sub.add_parser(
        "init",
        help="initialise a new notlob project in the current directory",
    )
    init_p.add_argument(
        "--language", "-l", metavar="LANG", default="python",
        help="project language (default: python)",
    )
    init_p.add_argument(
        "--bare", action="store_true", default=False,
        help="minimal scaffold only -- no AGENTS.md or docs",
    )
    init_p.add_argument(
        "--agents", dest="agents_only", action="store_true", default=False,
        help="write AGENTS.md and notlob-docs/ into an existing project",
    )

    new_p = sub.add_parser(
        "new",
        help="create a new .lob module",
    )
    new_p.add_argument(
        "name",
        help="module address, e.g. roman/numerals",
    )

    docs_p = sub.add_parser(
        "docs",
        help="write the language reference to notlob-docs/",
    )
    docs_p.add_argument(
        "--output", "-o", metavar="DIR", default=None,
        help="output directory (default: notlob-docs/)",
    )
    docs_p.add_argument(
        "--full", action="store_true", default=False,
        help="also write DESIGN.md and USER-AGENTS.md",
    )

    sub.add_parser("mcp", help="start the MCP tool server (stdin/stdout)")

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

    qcallers = qsub.add_parser(
        "callers", help="list symbols that call a given address"
    )
    qcallers.add_argument("address")

    qcallees = qsub.add_parser(
        "callees", help="list symbols called by a given address"
    )
    qcallees.add_argument("address")

    qrefs = qsub.add_parser(
        "references", help="list nodes prose-referenced by a given address"
    )
    qrefs.add_argument("address")

    qrefby = qsub.add_parser(
        "referenced-by", help="list nodes whose prose references a given address"
    )
    qrefby.add_argument("address")

    qcont = qsub.add_parser(
        "content", help="show source content at an address"
    )
    qcont.add_argument(
        "address",
        help="node address, e.g. roman/numerals#to_roman",
    )

    args = parser.parse_args()

    def _opt_path(file_arg, module_mode):
        """Resolve an optional file argument; return None when absent."""
        if file_arg is None:
            return None
        return _resolve_path(file_arg, module_mode)

    if args.command == "build":
        sys.exit(cmd_build(
            _opt_path(args.file, args.module_mode),
            output_dir=Path(args.output),
            skip_tests=args.skip_tests,
        ))
    elif args.command == "weave":
        sys.exit(cmd_weave(
            _opt_path(args.file, args.module_mode),
            language=args.language,
        ))
    elif args.command == "run":
        sys.exit(cmd_run(
            _resolve_path(args.file, args.module_mode),
            keep_generated_src=args.keep_generated_src,
            args=args.program_args or None,
        ))
    elif args.command == "test":
        sys.exit(cmd_test(
            _opt_path(args.file, args.module_mode),
            keep_generated_src=args.keep_generated_src,
            only=set(args.only) if args.only else None,
            json_mode=args.json_mode,
        ))
    elif args.command == "graph":
        sys.exit(cmd_graph(
            _opt_path(args.file, args.module_mode),
            include_content=args.content,
            fmt=args.format,
        ))
    elif args.command == "check":
        sys.exit(cmd_check(
            only=set(args.only) if args.only else None,
            verbose=args.verbose,
            json_mode=args.json_mode,
        ))
    elif args.command == "docs":
        sys.exit(cmd_docs(
            Path(args.output) if args.output else None,
            full=args.full,
        ))
    elif args.command == "init":
        sys.exit(cmd_init(
            language=args.language,
            bare=args.bare,
            agents_only=args.agents_only,
        ))
    elif args.command == "new":
        sys.exit(cmd_new(args.name))
    elif args.command == "mcp":
        from notlob.mcp_server import run_server
        run_server()
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
        elif op == "callers":
            sys.exit(cmd_query_callers(args.address))
        elif op == "callees":
            sys.exit(cmd_query_callees(args.address))
        elif op == "references":
            sys.exit(cmd_query_references(args.address))
        elif op == "referenced-by":
            sys.exit(cmd_query_referenced_by(args.address))
        elif op == "content":
            sys.exit(cmd_query_content(args.address))
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
