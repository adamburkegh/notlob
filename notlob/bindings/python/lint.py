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
ruff's reported line numbers before the source-map lookup; a finding
whose adjusted line falls at or before 0 is inside the prepended
dependency text, not the module actually being linted, and is dropped
rather than misattributed to it (that dependency's own findings are
reported when *it* is linted directly).

Claims aren't part of what gets linted -- ``assemble()`` only ever
collects real body code, not ``~example``/``#Tests``/``~property``
bodies -- so an import used solely by a claim looks unused to ruff.
``_claim_text`` collects every claim's raw source (a flat blob, not
parsed) so an ``F401`` finding can be suppressed when the reported
name is referenced anywhere in it. This is a textual, best-effort
check (consistent with how e.g. ``extract_calls`` is documented as
best-effort elsewhere in this codebase) rather than real static
analysis -- a name that only coincidentally appears in a claim (inside
a string literal, say) would wrongly suppress a genuine finding, but
that's judged the safer failure mode than the status quo of *always*
flagging an import a claim genuinely uses.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

from notlob.bindings import (
    LintResult, LintToolUnavailable, parse_source_map,
)
from notlob.bindings.python.assemble import assemble
from notlob.graph import module_address
from notlob.model import Module, TestsSection


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

    Raises ``LintToolUnavailable`` when ruff cannot be found (ruff is a
    core notlob dependency, so this should not happen in a correct
    install).  Returns an empty list when the module produces no
    assembler output (nothing to check, so the tool is not needed).
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
    claim_text = _claim_text(module)

    return _run_ruff(combined, source_map, offset, mod_addr, claim_text)


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


def _claim_text(module: Module) -> str:
    """Concatenated raw source of every claim in *module*.

    Covers ``~example`` (module body and subheadings), ``#Tests``
    (bare assertions, named ``~test`` blocks, and groups), and
    ``~property`` bodies -- every claim type the runner actually
    executes. Used only to check whether a name ruff considers unused
    is in fact used by a claim; see the module docstring.
    """
    # Local import avoids a hard dependency between the lint and
    # runner submodules for callers that only need one of them.
    from notlob.bindings.python.runner import (
        _collect_example_assertions, _collect_properties,
        _collect_test_assertions,
    )

    parts = [expr for _, expr, _ in _collect_example_assertions(module)]
    parts += [block for _, _, _, block in _collect_properties(module)]

    if module.post_text is not None:
        tests_section = next(
            (s for s in module.post_text.sections
             if isinstance(s, TestsSection)),
            None,
        )
        if tests_section is not None:
            mod_addr = module_address(module.title)
            parts += [
                expr for _, expr, _ in
                _collect_test_assertions(tests_section, mod_addr)
            ]

    return "\n".join(parts)


_UNUSED_IMPORT_RE = re.compile(r"^`([\w.]+)` imported but unused")


def _is_unused_import_used_by_claim(message: str, claim_text: str) -> bool:
    """Whether an F401 *message*'s reported name appears in *claim_text*."""
    if not claim_text:
        return False
    m = _UNUSED_IMPORT_RE.match(message)
    if not m:
        return False
    local_name = m.group(1).rsplit(".", 1)[-1]
    return re.search(rf"\b{re.escape(local_name)}\b", claim_text) is not None


def _run_ruff(
    source:     str,
    source_map: dict[int, str],
    offset:     int,
    fallback:   str,
    claim_text: str = "",
) -> list[LintResult]:
    """Pipe *source* through ``ruff check`` and translate diagnostics.

    *offset* is subtracted from each reported line number before
    looking up the section address in *source_map*.  *fallback* is the
    address used when the adjusted line is not in the map. A finding
    whose adjusted line is at or before 0 falls inside the prepended
    dependency text (see module docstring) and is dropped rather than
    attributed to *fallback*. An ``F401`` finding is also dropped when
    the reported name is used by a claim in *claim_text*.

    Raises ``LintToolUnavailable`` if ruff is not importable.  Returns an
    empty list when ruff runs but produces no diagnostics.
    """
    if importlib.util.find_spec("ruff") is None:
        raise LintToolUnavailable(
            "ruff not found. Install ruff (a core notlob dependency)."
        )

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
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        raise LintToolUnavailable(
            "ruff not found. Install ruff (a core notlob dependency)."
        )

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
        if adjusted <= 0:
            # Inside the prepended dependency text, not this module.
            continue
        if code == "F401" and _is_unused_import_used_by_claim(
            message, claim_text,
        ):
            continue
        addr = source_map.get(adjusted, fallback)

        results.append(LintResult(
            address=addr,
            code=code,
            message=message,
            col=col,
        ))

    return results
