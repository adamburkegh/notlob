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
Only the module's own assembled source is ever sent to ruff -- a
dependency's source is never prepended. Instead, when a project root
is available, ``_dependency_names`` collects the top-level names each
direct lob-ref dependency defines, and an ``F821`` "undefined name"
finding is dropped when the reported name is one of them: it's a
genuine cross-module reference, not an actually-undefined name. An
earlier version of this module prepended each dependency's full
assembled source (imports included) for this instead, which both
leaked the dependency's own findings into the referencing module's
results (needing its own after-the-fact filtering) and could collide
with a legitimate re-import of the same name in the referencing
module's own ``#References`` (``F811``). Filtering by name after
linting only the module's own text avoids both: ruff never sees
anything but this module's own source, so there's nothing to
misattribute and nothing for its own imports to collide with. (Real
cross-module reference *correctness* -- is this call actually valid,
not just "is this name spelled the same somewhere" -- is notlob's own
``NameGraph``-based ``check`` command's job, which has the real call
graph; ruff's F821 was only ever redundant noise for this case, not a
check anything relies on for real coverage.)

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

    When *root* is provided and the module has lob-ref dependencies, an
    ``F821`` finding for a name one of them defines is suppressed (see
    module docstring) -- otherwise only the module's own source is ever
    linted.

    Raises ``LintToolUnavailable`` when ruff cannot be found (ruff is a
    core notlob dependency, so this should not happen in a correct
    install).  Returns an empty list when the module produces no
    assembler output (nothing to check, so the tool is not needed).
    """
    mod_source = assemble(module)
    if not mod_source:
        return []

    dep_names  = _dependency_names(module, root) if root else frozenset()
    source_map = parse_source_map(mod_source)
    mod_addr   = module_address(module.title)
    claim_text = _claim_text(module)

    return _run_ruff(mod_source, source_map, mod_addr, claim_text, dep_names)


# ── Internals ─────────────────────────────────────────────────

def _dependency_names(module: Module, root: Path) -> frozenset[str]:
    """Top-level names defined by *module*'s direct lob-ref dependencies.

    Used only to recognise a cross-module reference so a genuine
    ``F821`` "undefined name" isn't reported for it; see module
    docstring. ``extract_symbols`` already ignores ``import`` lines (it
    only handles ``def``/``class``/assignment nodes), so a dependency's
    own imported names are never included here -- intentionally: this
    is about the dependency's *own* name surface, not what it imports.
    """
    from notlob import from_tree, parse_file
    from notlob.bindings.python.symbols import extract_symbols
    from notlob.project import module_lob_refs, resolve_module_path

    names: set[str] = set()
    for dep_addr in module_lob_refs(module):
        try:
            dep_path = resolve_module_path(dep_addr, root)
            dep_mod  = from_tree(parse_file(dep_path))
            dep_src  = assemble(dep_mod)
            if dep_src:
                names.update(
                    s.name for s in extract_symbols(dep_src.splitlines())
                )
        except Exception:
            pass  # missing dep — will surface as a claim execution error

    return frozenset(names)


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
_UNDEFINED_NAME_RE = re.compile(r"^Undefined name `([\w.]+)`$")


def _is_unused_import_used_by_claim(message: str, claim_text: str) -> bool:
    """Whether an F401 *message*'s reported name appears in *claim_text*."""
    if not claim_text:
        return False
    m = _UNUSED_IMPORT_RE.match(message)
    if not m:
        return False
    local_name = m.group(1).rsplit(".", 1)[-1]
    return re.search(rf"\b{re.escape(local_name)}\b", claim_text) is not None


def _is_undefined_name_from_dependency(
    message: str, dep_names: frozenset[str],
) -> bool:
    """Whether an F821 *message*'s reported name is a dependency's own."""
    if not dep_names:
        return False
    m = _UNDEFINED_NAME_RE.match(message)
    return m is not None and m.group(1) in dep_names


def _run_ruff(
    source:     str,
    source_map: dict[int, str],
    fallback:   str,
    claim_text: str = "",
    dep_names:  frozenset[str] = frozenset(),
) -> list[LintResult]:
    """Pipe *source* through ``ruff check`` and translate diagnostics.

    *fallback* is the address used when a finding's line isn't in
    *source_map*. An ``F401`` finding is dropped when the reported name
    is used by a claim in *claim_text*; an ``F821`` finding is dropped
    when the reported name is in *dep_names* (see module docstring).

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

        if code == "F401" and _is_unused_import_used_by_claim(
            message, claim_text,
        ):
            continue
        if code == "F821" and _is_undefined_name_from_dependency(
            message, dep_names,
        ):
            continue
        addr = source_map.get(row, fallback)

        results.append(LintResult(
            address=addr,
            code=code,
            message=message,
            col=col,
        ))

    return results
