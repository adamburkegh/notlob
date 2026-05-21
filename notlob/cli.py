"""notlob.cli — command-line interface.

Entry points
------------
notlob run <file>    Assemble and execute a .lob file.  No claim
                     checking; this runs the program.
notlob test <file>   Run all claims (examples, properties, #Tests)
                     and report results.  Exit 1 if any fail.
lob <file>           Thin alias: equivalent to ``notlob run <file>``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import textwrap

from notlob import from_tree, parse_file
from notlob.bindings.python.runner import (
    ClaimResult,
    Status,
    run_examples,
    run_properties,
    run_tests,
)
from notlob.bindings.python.assemble import assemble
from notlob.model import BindingSection, Claim, Subheading


# ── Binding resolution ────────────────────────────────────────

def _parse_binding_declarations(lines: list[str]) -> dict[str, str]:
    """Extract ~sigil declarations from a #Binding section's lines."""
    result: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("~"):
            parts = stripped[1:].split(None, 1)
            key = parts[0]
            value = parts[1].strip() if len(parts) > 1 else ""
            result[key] = value
    return result


def _find_binding(file_path: Path) -> dict[str, str]:
    """Walk up from *file_path* to find binding.lob; return its
    declarations.  Returns an empty dict if none is found.
    """
    for parent in file_path.resolve().parents:
        candidate = parent / "binding.lob"
        if candidate.exists():
            try:
                bmod = from_tree(parse_file(candidate))
                if bmod.post_text:
                    for section in bmod.post_text.sections:
                        if isinstance(section, BindingSection):
                            return _parse_binding_declarations(
                                section.lines
                            )
            except Exception:
                pass
            break   # found binding.lob but couldn't use it — stop
    return {}


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

def _collect_run_claims(module) -> list[Claim]:
    """Return all ~run claims from the module body and subheadings,
    in document order.
    """
    claims = []
    for item in module.body:
        if isinstance(item, Claim) and item.sigil == "~run":
            claims.append(item)
        elif isinstance(item, Subheading):
            for sub_item in item.body:
                if isinstance(sub_item, Claim) and sub_item.sigil == "~run":
                    claims.append(sub_item)
    return claims


def cmd_run(path: Path) -> int:
    """Assemble and execute *path*; return an exit code."""
    try:
        module = from_tree(parse_file(path))
    except Exception as exc:
        print(f"ERROR  <parse>  {exc}", file=sys.stderr)
        return 1

    ns: dict = {"__file__": str(path.resolve())}
    try:
        exec(assemble(module), ns)
    except Exception as exc:
        print(f"ERROR  <assembly>  {exc}", file=sys.stderr)
        return 1

    for claim in _collect_run_claims(module):
        try:
            exec(textwrap.dedent("\n".join(claim.lines)), ns)
        except Exception as exc:
            print(f"ERROR  <run>  {exc}", file=sys.stderr)
            return 1

    return 0


def cmd_test(path: Path) -> int:
    """Run all claims in *path* and return an exit code."""
    try:
        module = from_tree(parse_file(path))
    except Exception as exc:
        print(f"ERROR  <parse>  {exc}", file=sys.stderr)
        return 1

    binding = _find_binding(path)

    results = (
        run_examples(module, file_path=path)
        + run_properties(module, binding=binding, file_path=path)
        + run_tests(module, binding=binding, file_path=path)
    )

    for r in results:
        _print_result(r)

    n_fail = sum(1 for r in results if r.status != Status.PASS)
    n_pass = len(results) - n_fail
    if n_fail:
        print(f"\n{n_pass} passed, {n_fail} failed")
    else:
        print(f"\n{n_pass} passed")

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
        help="assemble and execute a .lob file",
    )
    run_p.add_argument("file", help="path to .lob file")

    test_p = sub.add_parser(
        "test",
        help="run all claims in a .lob file",
    )
    test_p.add_argument("file", help="path to .lob file")

    args = parser.parse_args()

    if args.command == "run":
        sys.exit(cmd_run(Path(args.file)))
    elif args.command == "test":
        sys.exit(cmd_test(Path(args.file)))
    else:
        parser.print_help()
        sys.exit(1)


def lob_main() -> None:
    """Thin alias: ``lob <file>`` is ``notlob run <file>``."""
    sys.argv = ["notlob", "run"] + sys.argv[1:]
    main()


if __name__ == "__main__":
    main()
