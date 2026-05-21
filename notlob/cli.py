"""notlob.cli — command-line interface.

Entry points
------------
notlob run <file>    Run all claims in a .lob file (examples, properties,
                     tests) and report results.  Exit 1 if any fail.
lob <file>           Thin alias: equivalent to ``notlob run <file>``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from notlob import from_tree, parse_file
from notlob.bindings.python.runner import (
    ClaimResult,
    Status,
    run_examples,
    run_properties,
    run_tests,
)


# ── Formatting ────────────────────────────────────────────────

def _print_result(r: ClaimResult) -> None:
    tag = r.status.name
    print(f"{tag:5}  {r.address}  {r.line}")
    if r.status == Status.FAIL:
        if r.left is not None or r.right is not None:
            print(f"         left:  {r.left!r}")
            print(f"         right: {r.right!r}")
        if r.error is not None:
            print(f"         error: {r.error}")
    elif r.status == Status.ERROR and r.error is not None:
        print(f"         error: {r.error}")


# ── Commands ──────────────────────────────────────────────────

def cmd_run(path: Path) -> int:
    """Run all claims in *path* and return an exit code."""
    try:
        module = from_tree(parse_file(path))
    except Exception as exc:
        print(f"ERROR  <parse>  {exc}", file=sys.stderr)
        return 1

    results = (
        run_examples(module)
        + run_properties(module)
        + run_tests(module)
    )

    for r in results:
        _print_result(r)

    n_fail = sum(1 for r in results if r.status != Status.PASS)
    n_pass = len(results) - n_fail
    label = "failed" if n_fail else "passed"
    if n_fail:
        print(f"\n{n_pass} passed, {n_fail} {label}")
    else:
        print(f"\n{n_pass} {label}")

    return 1 if n_fail else 0


# ── Entry points ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="notlob",
        description="Notlob literate-program runner.",
    )
    sub = parser.add_subparsers(dest="command", metavar="command")

    run_p = sub.add_parser(
        "run",
        help="run all claims in a .lob file",
    )
    run_p.add_argument("file", help="path to .lob file")

    args = parser.parse_args()

    if args.command == "run":
        sys.exit(cmd_run(Path(args.file)))
    else:
        parser.print_help()
        sys.exit(1)


def lob_main() -> None:
    """Thin alias: ``lob <file>`` is ``notlob run <file>``."""
    sys.argv = ["notlob", "run"] + sys.argv[1:]
    main()


if __name__ == "__main__":
    main()
