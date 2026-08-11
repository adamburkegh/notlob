"""notlob.bindings.haskell.lint — hlint-based linter for Haskell modules.

Assembles a Module into Haskell source and pipes it through
``hlint --json``.  Diagnostic line numbers are translated back to
notlob section addresses using the ``-- <address>`` location comments
that the assembler emits at the start of each section.

Source-map format
-----------------
The assembler prefixes each section with a comment of the form::

    -- roman/numerals
    numerals :: [(Int, String)]
    ...

    -- roman/numerals#Properties
    prop_positive :: Int -> Bool
    ...

``parse_source_map`` reads these markers and builds a ``{line: address}``
mapping.  Lines that precede the first marker (i.e. the ``module Foo
where`` header) are assigned to the first section found once it appears.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from notlob.bindings import LintResult, LintToolUnavailable
from notlob.bindings.haskell.assemble import assemble
from notlob.graph import module_address
from notlob.model import Module


def parse_source_map(assembled_src: str) -> dict[int, str]:
    """Haskell source map: delegates to shared implementation."""
    from notlob.bindings import parse_source_map as _shared
    return _shared(assembled_src, comment_prefix="--")


def lint_haskell(
    module: Module,
    root: Path | None = None,
) -> list[LintResult]:
    """Assemble *module* and run hlint; return a list of LintResults.

    *root* is accepted for API symmetry with ``lint_python`` but is not
    currently used — hlint is a style checker that does not need
    cross-module name resolution.

    Raises ``LintToolUnavailable`` when hlint cannot be found.  Returns
    an empty list when the module produces no assembler output (nothing
    to check, so the tool is not needed).
    """
    source = assemble(module)
    if not source:
        return []

    source_map = parse_source_map(source)
    mod_addr   = module_address(module.title)

    return _run_hlint(source, source_map, mod_addr)


# ── Internals ─────────────────────────────────────────────────

def _hlint_cmd() -> list[str] | None:
    """Return the hlint command list, or None if hlint is unavailable.

    Tries ``hlint`` on PATH first; falls back to
    ``stack exec -- hlint`` when Stack is available **and** hlint is
    present in the Stack environment (verified by a probe run).
    """
    if shutil.which("hlint"):
        return ["hlint", "--json", "-"]
    if shutil.which("stack"):
        try:
            probe = subprocess.run(
                ["stack", "exec", "--", "hlint", "--version"],
                capture_output=True, text=True, timeout=30,
            )
            if probe.returncode == 0:
                return ["stack", "exec", "--", "hlint", "--json", "-"]
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            pass
    return None


def _run_hlint(
    source:     str,
    source_map: dict[int, str],
    fallback:   str,
) -> list[LintResult]:
    """Pipe *source* through ``hlint --json`` and translate diagnostics.

    *fallback* is the address used when the adjusted line number is not
    in *source_map* (should not normally occur for well-formed output).

    Raises ``LintToolUnavailable`` if hlint is not installed.  Returns an
    empty list when hlint runs but produces no diagnostics.
    """
    cmd = _hlint_cmd()
    if cmd is None:
        raise LintToolUnavailable(
            "hlint not found. Install hlint (on PATH or via "
            "`stack install hlint`)."
        )

    try:
        proc = subprocess.run(
            cmd,
            input=source,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, OSError):
        return []

    try:
        diagnostics: list[dict] = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return []

    results: list[LintResult] = []
    for d in diagnostics:
        row  = d.get("startLine", 1)
        col  = d.get("startColumn", 1)
        hint = d.get("hint") or ""
        addr = source_map.get(row, fallback)

        results.append(LintResult(
            address=addr,
            code=hint,
            message=_format_message(d),
            col=col,
        ))

    return results


def _format_message(d: dict) -> str:
    """Format an hlint diagnostic as a concise human-readable string.

    When hlint supplies a refactoring suggestion (``from`` and ``to``
    fields), the message is ``<from> ==> <to>``.  Otherwise just the
    hint name is returned.

    >>> _format_message({"hint": "Redundant do", "from": "do f x", "to": "f x"})
    'do f x ==> f x'
    >>> _format_message({"hint": "Use const", "from": "", "to": None})
    'Use const'
    >>> _format_message({"hint": "Eta reduce"})
    'Eta reduce'
    """
    from_  = (d.get("from") or "").strip()
    to_    = (d.get("to")   or "").strip()
    if from_ and to_:
        return f"{from_} ==> {to_}"
    return (d.get("hint") or "").strip()
