"""notlob.bindings.python.lint — ruff-based linter for Python modules.

Assembles a Module into executable Python and pipes the result through
``ruff check``.  Diagnostic line numbers are translated back to notlob
section addresses using the ``# <address>`` location comments that the
assembler emits at the start of each section.

Source-map format
-----------------
The assembler prefixes each section with a comment of the form::

    # roman/numerals
    def to_roman(n: int) -> str:
        ...

    # roman/numerals#Decoding
    def from_roman(s: str) -> str:
        ...

``parse_source_map`` reads these markers and builds a ``{line: address}``
mapping.  Lines that precede the first marker (i.e. the #References
import block) are assigned to the first section found once it appears.

Dependency context
------------------
When a project root is available, dep module sources are prepended to
the combined source before linting.  This gives ruff visibility into
names imported from other notlob modules, suppressing false-positive
F821 "undefined name" errors.  The line offset is subtracted from
ruff's reported line numbers before the source-map lookup.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from notlob.bindings import LintResult
from notlob.bindings.python.assemble import assemble
from notlob.graph import module_address
from notlob.model import Module


from notlob.bindings import parse_source_map


def lint_python(
    module: Module,
    root: Path | None = None,
) -> list[LintResult]:
    """Assemble *module* and run ruff; return a list of LintResults.

    When *root* is provided and the module has lob-ref dependencies,
    their assembled sources are prepended to the source sent to ruff so
    that cross-module names are visible.  The line offset is adjusted
    so that source-map lookup addresses the right section in the main
    module.

    Returns an empty list when ruff is not installed or the module
    produces no assembler output.
    """
    mod_source = assemble(module)
    if not mod_source:
        return []

    # Prepend dep sources for name-resolution context.
    dep_offset = _prepend_deps(module, root) if root else ("", 0)
    dep_source, offset = dep_offset

    combined = (dep_source + "\n\n" + mod_source) if dep_source else mod_source

    source_map = parse_source_map(mod_source)
    mod_addr   = module_address(module.title)

    return _run_ruff(combined, source_map, offset, mod_addr)


# ── Internals ─────────────────────────────────────────────────

def _prepend_deps(
    module: Module,
    root:   Path,
) -> tuple[str, int]:
    """Return ``(dep_source, line_offset)`` for cross-module context.

    *dep_source* is the concatenated assembled source of all lob-ref
    dependencies.  *line_offset* is the number of lines to subtract
    from ruff's reported line numbers to get into the main module's
    coordinate space.
    """
    from notlob import from_tree, parse_file
    from notlob.project import module_lob_refs, resolve_module_path

    parts: list[str] = []
    for dep_addr in module_lob_refs(module):
        try:
            dep_path = resolve_module_path(dep_addr, root)
            dep_mod  = from_tree(parse_file(dep_path))
            dep_src  = assemble(dep_mod)
            if dep_src:
                parts.append(dep_src)
        except Exception:
            pass  # missing dep — will surface as a claim execution error

    if not parts:
        return "", 0

    dep_source = "\n\n".join(parts)
    # +2 for the "\n\n" separator between dep_source and mod_source
    offset = dep_source.count("\n") + 2
    return dep_source, offset


def _run_ruff(
    source:     str,
    source_map: dict[int, str],
    offset:     int,
    fallback:   str,
) -> list[LintResult]:
    """Pipe *source* through ``ruff check`` and translate diagnostics.

    *offset* is subtracted from each reported line number before
    looking up the section address in *source_map*.  *fallback* is the
    address used when the adjusted line is not in the map.

    Returns an empty list if ruff is not installed or produces no JSON.
    """
    try:
        proc = subprocess.run(
            [
                sys.executable, "-m", "ruff",
                "check",
                "--output-format=json",
                "--stdin-filename=module.py",
                "-",
            ],
            input=source,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return []   # ruff module not importable — skip silently

    try:
        diagnostics: list[dict] = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return []

    results: list[LintResult] = []
    for d in diagnostics:
        location = d.get("location", {})
        row = location.get("row", 1)
        col = location.get("column", 1)
        code    = d.get("code") or ""
        message = d.get("message") or ""

        adjusted = row - offset
        addr = source_map.get(adjusted, fallback)

        results.append(LintResult(
            address=addr,
            code=code,
            message=message,
            col=col,
        ))

    return results
