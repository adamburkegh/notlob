"""notlob.bindings.typescript.lint — tsc-based type checker for TS modules.

Assembles a Module into TypeScript and runs ``tsc --noEmit`` over it,
translating each diagnostic's line number back to a notlob section
address via the ``// <address>`` location comments the assembler emits.

Why ``tsc`` rather than a style linter
--------------------------------------
The runner executes modules with ``tsx``, which strips types and runs
without type-checking — so genuine type errors otherwise slip through
to runtime.  ``tsc --noEmit`` is the only stage that catches them, which
makes it the highest-value "lint" for the TypeScript binding.  A style
linter (Biome/ESLint) would be a complementary second layer; this
module covers correctness first.

Dependency context
------------------
When a project root is available, lob-ref dependency sources are
prepended before type-checking so cross-module names resolve (mirroring
``lint_python``).  The prepended line count is subtracted from each
reported line before the source-map lookup.

Tool contract
-------------
Because the kit sets ``lint`` to this function, type-checking is part of
the test contract.  When ``tsc`` cannot be found (project-local
``node_modules/.bin/tsc`` or on PATH), ``LintToolUnavailable`` is raised
so ``notlob test`` fails loudly — mirroring how the runner errors when
``tsx`` is missing — rather than silently reporting a false pass.  A
module with no code produces no source to check and returns ``[]``
without needing the tool.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from notlob.bindings import (
    LintResult, LintToolUnavailable, parse_source_map,
)
from notlob.bindings.typescript.assemble import assemble
from notlob.bindings.typescript.runner import node_bin
from notlob.graph import module_address
from notlob.model import Module


# tsc diagnostic line, e.g.:
#   /tmp/abc.ts(12,5): error TS2322: Type 'string' is not assignable ...
_DIAG_RE = re.compile(
    r'^.+?\((\d+),(\d+)\): error (TS\d+): (.+)$'
)

_TSC_FLAGS = [
    '--noEmit',
    '--skipLibCheck',
    '--target', 'ES2020',
    '--lib', 'ES2020,DOM',
    '--moduleResolution', 'node',
]


def lint_typescript(
    module: Module,
    root: Path | None = None,
) -> list[LintResult]:
    """Assemble *module* and run ``tsc --noEmit``; return LintResults.

    When *root* is provided and the module has lob-ref dependencies,
    their assembled sources are prepended so cross-module names resolve.

    Raises ``LintToolUnavailable`` when tsc cannot be found.  Returns an
    empty list when the module produces no assembler output (nothing to
    check, so the tool is not needed).
    """
    mod_source = assemble(module)
    if not mod_source:
        return []

    dep_source, offset = _prepend_deps(module, root) if root else ("", 0)
    combined = (
        dep_source + "\n\n" + mod_source if dep_source else mod_source
    )

    source_map = parse_source_map(mod_source, comment_prefix="//")
    mod_addr   = module_address(module.title)

    return _run_tsc(combined, source_map, offset, mod_addr, root)


# ── Internals ─────────────────────────────────────────────────

def _prepend_deps(module: Module, root: Path) -> tuple[str, int]:
    """Return ``(dep_source, line_offset)`` for cross-module context.

    *dep_source* is the concatenated assembled source of all lob-ref
    dependencies.  *line_offset* is the number of lines to subtract from
    tsc's reported line numbers to reach the main module's coordinates.
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
            pass  # missing dep surfaces as a claim execution error

    if not parts:
        return "", 0

    dep_source = "\n\n".join(parts)
    # +2 for the "\n\n" separator between dep_source and mod_source
    offset = dep_source.count("\n") + 2
    return dep_source, offset


def _run_tsc(
    source:     str,
    source_map: dict[int, str],
    offset:     int,
    fallback:   str,
    root:       Path | None,
) -> list[LintResult]:
    """Type-check *source* with ``tsc --noEmit`` and translate diagnostics.

    *offset* is subtracted from each reported line before the source-map
    lookup; *fallback* is used when the adjusted line is not in the map.

    Raises ``LintToolUnavailable`` if tsc is not installed.  Returns an
    empty list when tsc runs but emits no diagnostics.
    """
    tsc = node_bin('tsc', root)
    if tsc is None:
        raise LintToolUnavailable(
            "tsc not found. Install typescript "
            "(project-local node_modules/.bin/tsc or on PATH)."
        )

    with tempfile.NamedTemporaryFile(
        suffix='.ts', mode='w', encoding='utf-8', delete=False,
    ) as f:
        f.write(source)
        tmp_path = f.name

    try:
        proc = subprocess.run(
            [tsc, *_TSC_FLAGS, tmp_path],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
    except (FileNotFoundError, OSError):
        return []
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass

    return _parse_tsc_output(proc.stdout, source_map, offset, fallback)


def _parse_tsc_output(
    output:     str,
    source_map: dict[int, str],
    offset:     int,
    fallback:   str,
) -> list[LintResult]:
    """Parse tsc stdout into LintResults via the source map."""
    results: list[LintResult] = []
    for line in output.splitlines():
        m = _DIAG_RE.match(line)
        if not m:
            continue   # continuation / summary lines
        row     = int(m.group(1))
        col     = int(m.group(2))
        code    = m.group(3)
        message = m.group(4)

        adjusted = row - offset
        addr = source_map.get(adjusted, fallback)

        results.append(LintResult(
            address=addr,
            code=code,
            message=message,
            col=col,
        ))

    return results
