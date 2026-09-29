"""notlob.bindings.python.runner — claim runner for the Python binding.

Assembles a module's code (with lob-ref dependencies inlined, mirroring
``build_python``) into a self-contained harness script, runs it as a
*subprocess* with an interpreter resolved from ``PATH``, and parses a
line protocol from its stdout back into ``ClaimResult`` objects.  See
``notlob.bindings.python.harness`` for the harness scripts themselves
and the exact protocol.

This binding used to ``exec()`` claims directly inside notlob's own
process, which meant claims always ran under notlob's own interpreter
(e.g. its pipx venv) regardless of any activated venv, asdf/mise shim,
or project-local interpreter in the caller's shell -- so a module
importing a third-party library installed only in the *target*
project's environment would fail with ``ModuleNotFoundError``, even
though that import is perfectly valid from the user's own shell. The
subprocess approach, resolving the interpreter via
``_resolve_python_interpreter`` (PATH-based, like
``notlob.bindings.haskell.runner._make_runghc_cmd``'s own
``shutil.which("runghc")`` lookup -- deliberately not ``sys.executable``,
which is fixed to whichever interpreter is running notlob itself and
does not reflect the caller's shell state), fixes this: claims run
under whatever interpreter the caller's ``PATH`` currently resolves,
exactly like Haskell's and TypeScript's runners already do.

One ClaimResult is produced per assertion line.  The ordinal in the
claim address counts ~example blocks within their containing node:

    roman/numerals#example#1     ← first ~example in module body
    roman/numerals#Decoding#example#2  ← second ~example in subheading

Running the module's own code under the target interpreter is only
half the story: ``#Tests``/``~property`` claims also need
``pytest``/``hypothesis`` specifically, and those are notlob's own
tooling, not something the target project should have to install --
"comes for free with the Python binding" is a real requirement, not
just a nice-to-have. So each ``#Tests``/``~property`` harness appends
notlob's *own* site-packages directory (see ``_notlob_site_packages``)
to ``sys.path`` as a fallback, not an override: Python always searches
the target interpreter's normal locations first, so a project that
already has its own pinned ``pytest``/``hypothesis`` keeps using it
unchanged, and notlob's bundled copies only fill the gap when the
target has none at all. This is deliberately narrower than injecting
notlob's whole site-packages directory via ``PYTHONPATH`` (which would
be searched *before* the target's own packages) -- that would let
notlob's own dependencies with the same name as something the target
project uses for something else entirely (``lark``, ``regex``, ...)
silently shadow the target's real ones, which ``sys.path.append`` at
the bottom of the harness script avoids by construction.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from notlob.bindings import ClaimResult, Status, iter_assertions
from notlob.bindings.python.assemble import assemble_with_deps
from notlob.bindings.python.harness import (
    build_examples_harness, build_properties_harness, build_tests_harness,
)
from notlob.graph import (
    claim_address, module_address, property_address, subheading_address,
)
from notlob.model import (
    Claim, Module, NamedTest, Subheading, TestGroup, TestsSection,
)


# ── Interpreter resolution ──────────────────────────────────────

def _resolve_python_interpreter() -> str | None:
    """Return a python interpreter resolved from ``PATH``, or ``None``.

    Deliberately not ``sys.executable``: that's whichever interpreter
    is currently running notlob itself, fixed at however notlob was
    launched (e.g. a pipx-isolated venv) -- it doesn't reflect the
    caller's shell state at all. ``PATH``-based lookup is exactly what
    activating a venv or an asdf/mise shim modifies, so it's what picks
    those up.

    ``"python"`` is tried before ``"python3"``: Windows venvs only ever
    provide ``python.exe`` (no ``python3.exe``), and Windows ships a
    fake ``python3.exe`` "app execution alias" stub on ``PATH`` by
    default that isn't a real interpreter -- checking ``python3`` first
    risks landing on that stub instead of falling through to a real
    one. Verified against a real isolated venv on Windows before
    relying on this ordering.
    """
    return shutil.which("python") or shutil.which("python3")


def _notlob_site_packages() -> str:
    """Return the directory ``pytest`` was actually imported from.

    ``hypothesis`` and ``pytest`` are guaranteed to be importable here,
    since they're notlob's own ``pyproject.toml`` dependencies -- this
    is what ``#Tests``/``~property`` harnesses append to ``sys.path`` as
    a fallback so those two are available "for free" regardless of the
    target interpreter.

    Deliberately resolved via the real import machinery
    (``pytest.__file__``) rather than ``sysconfig.get_paths()``:
    ``sysconfig`` derives its answer from the running interpreter's
    install scheme (``sys.prefix``), which is correct for a normal venv
    or pipx/uvx install but wrong for a zipapp-style bundle (e.g. shiv)
    that makes packages importable by prepending an extraction-cache
    directory to ``sys.path`` without ever changing ``sys.prefix`` --
    under that scheme ``sysconfig`` would point at the base interpreter's
    own site-packages, which has neither package in it, silently
    breaking this fallback.
    """
    import pytest
    return str(Path(pytest.__file__).resolve().parent.parent)


# ── Subprocess execution ────────────────────────────────────────

def _run_harness(
    script: str,
    keep_path: Path | None = None,
    timeout: int = 120,
) -> tuple[str, str, int]:
    """Write *script* to a temp file and run it with the resolved
    interpreter. Returns ``(stdout, stderr, returncode)``.

    If *keep_path* is set, *script* is also written there for
    inspection -- errors doing so are silently ignored so they never
    interfere with the actual run.
    """
    if keep_path is not None:
        try:
            keep_path.parent.mkdir(parents=True, exist_ok=True)
            keep_path.write_text(script, encoding="utf-8")
        except OSError:
            pass

    interpreter = _resolve_python_interpreter()
    if interpreter is None:
        return "", "no Python interpreter found on PATH", 1

    tmpdir = tempfile.mkdtemp()
    tmp_path = Path(tmpdir) / "_harness.py"
    try:
        tmp_path.write_text(script, encoding="utf-8")
        try:
            # PYTHONIOENCODING controls the *child* interpreter's own
            # stdout/stderr encoding -- without it, a harness that
            # prints a non-ASCII address (e.g. from a Unicode heading
            # title) crashes inside the child on Windows, where the
            # default is the console codepage, not UTF-8. This is a
            # separate concern from this call's own encoding="utf-8"
            # below, which only controls how *this* process decodes
            # the bytes it receives back -- it has no effect on how
            # the child encodes them in the first place.
            child_env = dict(os.environ, PYTHONIOENCODING="utf-8")
            proc = subprocess.run(
                [interpreter, str(tmp_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=child_env,
            )
            return proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            return "", f"timeout after {timeout}s", 1
        except FileNotFoundError as exc:
            return "", str(exc), 1
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except OSError:
            pass


def _deliteral(s: str) -> Any:
    """Best-effort Python literal decode; return the raw string on
    failure. Mirrors ``notlob.bindings.typescript.runner._dejson`` --
    the harness sends ``repr(value)`` over the wire since arbitrary
    Python objects can't otherwise cross a subprocess text boundary;
    ``ast.literal_eval`` reconstructs the common cases (numbers,
    strings, None, bools, tuples/lists/dicts of those) so downstream
    consumers that treat ``ClaimResult.left``/``.right`` as real values
    (they all just ``repr()`` them for display, but the contract is
    "a value", not "already-formatted text") keep working. Falls back
    to the repr text itself for anything that doesn't round-trip
    (custom ``__repr__`` output, etc.) -- an inherent limit of crossing
    a subprocess boundary, not a bug.
    """
    try:
        return ast.literal_eval(s)
    except (ValueError, SyntaxError):
        return s or None


# ── Protocol parsing ────────────────────────────────────────────

def _parse_protocol(
    stdout: str,
    stderr: str,
    assertions: list[tuple[str, str, int | None]],
    file_path: str | None,
) -> list[ClaimResult]:
    """Parse the CLAIM/PASS/FAIL/ERROR protocol for boolean assertions
    (``~example``/``#Tests``) into ``ClaimResult`` objects.

    Expected stdout format, two lines per assertion::

        CLAIM\\t<addr>\\t<source_line_or_empty>\\t<expr>
        PASS

    or ``FAIL\\t<lhs_repr>\\t<rhs_repr>`` / ``ERROR\\t<type>\\t<message>``
    in place of ``PASS``. A CLAIM line with no following result line
    indicates a crash mid-run. If stdout has no CLAIM lines at all,
    the module failed to load -- reported as a single ``<assembly>``
    error, matching the previous in-process behaviour.
    """
    results: list[ClaimResult] = []
    lines = stdout.splitlines()
    i = 0
    claim_n = 0

    while i < len(lines):
        raw = lines[i]
        if raw.startswith("CLAIM\t"):
            parts = raw.split("\t", 3)
            addr = parts[1] if len(parts) > 1 else "?"
            expr = (
                _deliteral(parts[3]) if len(parts) > 3 else "<assertion>"
            )
            sl = (assertions[claim_n][2]
                  if claim_n < len(assertions) else None)
            claim_n += 1
            i += 1
            if i < len(lines):
                result_line = lines[i]
                if result_line == "PASS":
                    results.append(ClaimResult(
                        address=addr, line=expr, status=Status.PASS,
                        source_line=sl, file_path=file_path,
                    ))
                elif result_line.startswith("FAIL\t"):
                    fparts = result_line.split("\t", 2)
                    left = _deliteral(fparts[1]) if len(fparts) > 1 else None
                    right = _deliteral(fparts[2]) if len(fparts) > 2 else None
                    results.append(ClaimResult(
                        address=addr, line=expr, status=Status.FAIL,
                        left=left, right=right,
                        source_line=sl, file_path=file_path,
                    ))
                elif result_line.startswith("ERROR\t"):
                    eparts = result_line.split("\t", 2)
                    msg = (
                        _deliteral(eparts[2]) if len(eparts) > 2
                        else result_line[6:]
                    )
                    results.append(ClaimResult(
                        address=addr, line=expr, status=Status.ERROR,
                        error=RuntimeError(msg),
                        source_line=sl, file_path=file_path,
                    ))
                else:
                    results.append(ClaimResult(
                        address=addr, line=expr, status=Status.ERROR,
                        error=RuntimeError(
                            f"unexpected runner output: {result_line!r}"
                        ),
                        source_line=sl, file_path=file_path,
                    ))
            else:
                err_msg = stderr.strip() or "runtime error (no result)"
                results.append(ClaimResult(
                    address=addr, line=expr, status=Status.ERROR,
                    error=RuntimeError(err_msg),
                    source_line=sl, file_path=file_path,
                ))
        i += 1

    if not results and assertions:
        err_msg = stderr.strip() or "assembly error"
        addr, _expr, sl = assertions[0]
        results.append(ClaimResult(
            address=addr, line="<assembly>", status=Status.ERROR,
            error=RuntimeError(err_msg),
            source_line=sl, file_path=file_path,
        ))

    return results


def _parse_property_protocol(
    stdout: str,
    stderr: str,
    properties: list[tuple[str, str, int | None, str]],
    file_path: str | None,
) -> list[ClaimResult]:
    """Parse the CLAIM/PASS/FAIL/ERROR protocol for ``~property``
    claims. Unlike a boolean assertion, a property has no natural left/
    right side -- a FAIL line carries ``(exc_type, exc_message)``
    instead, stored on ``ClaimResult.error`` (matching the previous
    in-process ``error=exc`` behaviour), not ``.left``/``.right``.
    """
    results: list[ClaimResult] = []
    lines = stdout.splitlines()
    i = 0
    claim_n = 0

    while i < len(lines):
        raw = lines[i]
        if raw.startswith("CLAIM\t"):
            parts = raw.split("\t", 3)
            addr = parts[1] if len(parts) > 1 else "?"
            sigil = parts[3] if len(parts) > 3 else "~property"
            sl = (properties[claim_n][2]
                  if claim_n < len(properties) else None)
            claim_n += 1
            i += 1
            if i < len(lines):
                result_line = lines[i]
                if result_line == "PASS":
                    results.append(ClaimResult(
                        address=addr, line=sigil, status=Status.PASS,
                        source_line=sl, file_path=file_path,
                    ))
                elif result_line.startswith("FAIL\t"):
                    fparts = result_line.split("\t", 2)
                    msg = (
                        _deliteral(fparts[2]) if len(fparts) > 2
                        else result_line[5:]
                    )
                    results.append(ClaimResult(
                        address=addr, line=sigil, status=Status.FAIL,
                        error=RuntimeError(msg),
                        source_line=sl, file_path=file_path,
                    ))
                elif result_line.startswith("ERROR\t"):
                    eparts = result_line.split("\t", 2)
                    msg = (
                        _deliteral(eparts[2]) if len(eparts) > 2
                        else result_line[6:]
                    )
                    results.append(ClaimResult(
                        address=addr, line=sigil, status=Status.ERROR,
                        error=RuntimeError(msg),
                        source_line=sl, file_path=file_path,
                    ))
                else:
                    results.append(ClaimResult(
                        address=addr, line=sigil, status=Status.ERROR,
                        error=RuntimeError(
                            f"unexpected runner output: {result_line!r}"
                        ),
                        source_line=sl, file_path=file_path,
                    ))
            else:
                err_msg = stderr.strip() or "runtime error (no result)"
                results.append(ClaimResult(
                    address=addr, line=sigil, status=Status.ERROR,
                    error=RuntimeError(err_msg),
                    source_line=sl, file_path=file_path,
                ))
        i += 1

    if not results and properties:
        err_msg = stderr.strip() or "assembly error"
        addr, _sigil, sl, _src = properties[0]
        results.append(ClaimResult(
            address=addr, line="<assembly>", status=Status.ERROR,
            error=RuntimeError(err_msg),
            source_line=sl, file_path=file_path,
        ))

    return results


# ── Dependency loading / assembly ───────────────────────────────

def _load_dep_modules(
    module: Module,
    file_path: Path | None,
) -> list[Module]:
    """Return the lob-ref dependency modules of *module* in declaration order.

    Resolves each ``#Title`` lob-ref in *module*'s ``#References``
    section to its ``.lob`` file under the project root, parses it, and
    returns the resulting Module objects. Dependencies that cannot be
    found or parsed are silently skipped -- the resulting NameError at
    execution time surfaces the missing symbol, same as a real import
    error would.

    Returns an empty list when *file_path* is ``None`` (no project
    context available) or when no project root is found.
    """
    if file_path is None:
        return []

    from notlob.project import (           # noqa: PLC0415
        find_project_root, module_lob_refs, resolve_module_path,
    )
    from notlob.parser import parse_file   # noqa: PLC0415
    from notlob.model import from_tree     # noqa: PLC0415

    root = find_project_root(file_path)
    if root is None:
        return []

    result: list[Module] = []
    for dep_addr in module_lob_refs(module):
        try:
            dep_path = resolve_module_path(dep_addr, root)
            result.append(from_tree(parse_file(dep_path)))
        except Exception:
            pass  # missing dep — will surface as a NameError at exec time

    return result


def _module_source(module: Module, file_path: Path | None) -> str:
    """Return *module*'s code, with lob-ref dependencies inlined
    before it -- the subprocess harness has no loader around it at
    execution time, so dependency source has to be inlined directly,
    same as ``build_python``."""
    dep_modules = _load_dep_modules(module, file_path)
    return assemble_with_deps(module, dep_modules)


# ── Claim collection (parsing-only, no execution) ───────────────

def _collect_example_assertions(
    module: Module,
) -> list[tuple[str, str, int | None]]:
    """Return ``(addr, expr, source_line)`` for every ~example
    assertion in *module* (module body and subheadings)."""
    mod_addr = module_address(module.title)
    assertions: list[tuple[str, str, int | None]] = []

    def _collect(body: list, containing_addr: str) -> None:
        example_n = 0
        for item in body:
            if not (isinstance(item, Claim) and item.sigil == "~example"):
                continue
            example_n += 1
            addr = claim_address(containing_addr, "example", example_n)
            base = (item.start_line + 1) if item.start_line else None
            for assertion, offset in _iter_assertions(item.lines):
                sl = (base + offset) if base else None
                assertions.append((addr, assertion, sl))

    _collect(module.body, mod_addr)
    for item in module.body:
        if isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            _collect(item.body, sub_addr)

    return assertions


def _collect_test_assertions(
    tests_section: TestsSection,
    mod_addr: str,
) -> list[tuple[str, str, int | None]]:
    """Return ``(addr, expr, source_line)`` for every #Tests assertion."""
    tests_addr = f"{mod_addr}#Tests"
    line_offsets = tests_section.line_offsets or {}
    assertions: list[tuple[str, str, int | None]] = []
    bare: list[str] = []
    bare_indices: list[int] = []

    def _flush_bare() -> None:
        if not bare:
            return
        first_line = line_offsets.get(bare_indices[0])
        for assertion, offset in _iter_assertions(bare):
            sl = (first_line + offset) if first_line else None
            assertions.append((tests_addr, assertion, sl))
        bare.clear()
        bare_indices.clear()

    for idx, item in enumerate(tests_section.items):
        if isinstance(item, str):
            bare.append(item)
            bare_indices.append(idx)
        elif isinstance(item, TestGroup):
            _flush_bare()
            group_addr = f"{tests_addr}#{item.title}"
            _collect_group_assertions(item, group_addr, assertions)
        # ProseBlock: commentary, not evaluated.

    _flush_bare()
    return assertions


def _collect_group_assertions(
    group: TestGroup,
    group_addr: str,
    assertions: list[tuple[str, str, int | None]],
) -> None:
    """Append ``(addr, expr, source_line)`` for one TestGroup's own bare
    assertions and NamedTest blocks."""
    line_offsets = group.line_offsets or {}
    bare: list[str] = []
    bare_indices: list[int] = []

    def _flush_bare() -> None:
        if not bare:
            return
        first_line = line_offsets.get(bare_indices[0])
        for assertion, offset in _iter_assertions(bare):
            sl = (first_line + offset) if first_line else None
            assertions.append((group_addr, assertion, sl))
        bare.clear()
        bare_indices.clear()

    for idx, item in enumerate(group.items):
        if isinstance(item, str):
            bare.append(item)
            bare_indices.append(idx)
        elif isinstance(item, NamedTest):
            _flush_bare()
            addr = property_address(group_addr, item.name)
            base = (item.start_line + 1) if item.start_line else None
            for assertion, offset in _iter_assertions(item.lines):
                sl = (base + offset) if base else None
                assertions.append((addr, assertion, sl))
        # ProseBlock: commentary, not evaluated.

    _flush_bare()


def _collect_properties(
    module: Module,
) -> list[tuple[str, str, int | None, str]]:
    """Return ``(addr, sigil, source_line, prop_block_source)`` for
    every ~property claim in *module* (module body and subheadings)."""
    mod_addr = module_address(module.title)
    properties: list[tuple[str, str, int | None, str]] = []

    def _collect(body: list, containing_addr: str) -> None:
        prop_n = 0
        for item in body:
            if not (isinstance(item, Claim)
                    and item.sigil.startswith("~property")):
                continue
            prop_n += 1
            parts = item.sigil.split(None, 1)
            if len(parts) > 1:
                addr = property_address(containing_addr, parts[1].strip())
            else:
                addr = claim_address(containing_addr, "property", prop_n)
            prop_block = textwrap.dedent("\n".join(item.lines))
            properties.append((addr, item.sigil, item.start_line, prop_block))

    _collect(module.body, mod_addr)
    for item in module.body:
        if isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            _collect(item.body, sub_addr)

    return properties


def _iter_assertions(lines: list[str]):
    """Yield ``(expression, line_offset)`` from raw claim lines."""
    yield from iter_assertions(lines, is_complete=_is_complete)


def _is_complete(text: str) -> bool:
    """Return True if text is a syntactically complete expression.

    An unclosed delimiter ("was never closed") means more lines are
    needed.  Any other SyntaxError is treated as complete — the error
    will be reported when the assertion is actually executed.
    """
    try:
        compile(f"assert {text}", "<claim>", "exec")
        return True
    except SyntaxError as exc:
        return "was never closed" not in (exc.msg or "")


# ── Public claim runners ─────────────────────────────────────────

def run_examples(
    module: Module,
    file_path: Path | None = None,
    cache: Any = None,
    keep_dir: Path | None = None,
) -> list[ClaimResult]:
    """Run all ~example claims in a module and return results.

    Runs in a subprocess under the ``PATH``-resolved interpreter (see
    module docstring); *cache* is accepted for signature compatibility
    with the shared ``BindingKit`` call site but unused -- dependencies
    are inlined into the harness source instead of merged into an
    in-process namespace via a ``ModuleCache``.

    *keep_dir*, when provided, causes the harness script actually run
    to be written to ``<keep_dir>/_examples.py`` for inspection.
    """
    assertions = _collect_example_assertions(module)
    if not assertions:
        return []

    source = _module_source(module, file_path)
    script = build_examples_harness(source, assertions)
    keep_path = (keep_dir / "_examples.py") if keep_dir else None
    stdout, stderr, _rc = _run_harness(script, keep_path=keep_path)

    fp = str(file_path) if file_path else None
    return _parse_protocol(stdout, stderr, assertions, fp)


def run_tests(
    module: Module,
    binding: dict | None = None,
    file_path: Path | None = None,
    cache: Any = None,
    keep_dir: Path | None = None,
) -> list[ClaimResult]:
    """Run all assertions in the #Tests section and return results.

    Assertions under a named ## group get an address of the form
    <module>#Tests#<group>.  Bare assertions outside any group use
    <module>#Tests.  A ``~test <name>`` block gets its own address
    (<module>#Tests#<group>#<name>), with every assertion line inside
    it sharing that one address -- matching how an unnamed ~example
    block's own lines already share one address, distinguished by
    source line rather than a per-line ordinal.  Prose commentary
    interspersed with assertions (at either level) is not evaluated.

    *binding*/*cache* are accepted for signature compatibility with
    the shared ``BindingKit`` call site but unused. ``pytest`` comes
    from notlob's own install as a ``sys.path`` fallback -- see module
    docstring and ``_notlob_site_packages``.

    *keep_dir*, when provided, causes the harness script actually run
    to be written to ``<keep_dir>/_tests.py`` for inspection.

    Assembly errors produce a single ERROR result as with run_examples.
    """
    if module.post_text is None:
        return []

    tests_section = next(
        (s for s in module.post_text.sections
         if isinstance(s, TestsSection)),
        None,
    )
    if tests_section is None:
        return []

    mod_addr = module_address(module.title)
    assertions = _collect_test_assertions(tests_section, mod_addr)
    if not assertions:
        return []

    source = _module_source(module, file_path)
    script = build_tests_harness(source, assertions, _notlob_site_packages())
    keep_path = (keep_dir / "_tests.py") if keep_dir else None
    stdout, stderr, _rc = _run_harness(script, keep_path=keep_path)

    fp = str(file_path) if file_path else None
    return _parse_protocol(stdout, stderr, assertions, fp)


def run_properties(
    module: Module,
    binding: dict | None = None,
    file_path: Path | None = None,
    cache: Any = None,
    keep_dir: Path | None = None,
) -> list[ClaimResult]:
    """Run all ~property claims in a module and return results.

    Each claim block execs into its own fresh copy of the
    post-module, post-hypothesis-injection namespace within one
    combined subprocess -- isolating the ephemeral witness function
    from the module's permanent state and from other properties'
    witnesses, matching the previous in-process behaviour's per-claim
    namespace copy.

    *binding*/*cache* are accepted for signature compatibility with
    the shared ``BindingKit`` call site but unused. ``hypothesis``
    comes from notlob's own install as a ``sys.path`` fallback -- see
    module docstring and ``_notlob_site_packages``.

    Named properties (`~property name`) use the sigil name as address.
    Unnamed properties use an ordinal: <containing>#property#n.

    *keep_dir*, when provided, causes the harness script actually run
    to be written to ``<keep_dir>/_properties.py`` for inspection.

    Assembly errors produce a single ERROR result as with run_examples.
    """
    properties = _collect_properties(module)
    if not properties:
        return []

    source = _module_source(module, file_path)
    script = build_properties_harness(
        source, properties, _notlob_site_packages(),
    )
    keep_path = (keep_dir / "_properties.py") if keep_dir else None
    stdout, stderr, _rc = _run_harness(script, keep_path=keep_path)

    fp = str(file_path) if file_path else None
    return _parse_property_protocol(stdout, stderr, properties, fp)
