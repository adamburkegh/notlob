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

from notlob.commands import cmd_run, cmd_test
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

    args = parser.parse_args()

    if args.command == "run":
        sys.exit(cmd_run(_resolve_path(args.file, args.module_mode)))
    elif args.command == "test":
        sys.exit(cmd_test(_resolve_path(args.file, args.module_mode)))
    else:
        parser.print_help()
        sys.exit(1)


def lob_main() -> None:
    """Thin alias: ``lob <file>`` is ``notlob run <file>``."""
    sys.argv = ["notlob", "run"] + sys.argv[1:]
    main()


if __name__ == "__main__":
    main()
