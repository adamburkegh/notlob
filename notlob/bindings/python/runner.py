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
import re
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Sequence

from notlob.bindings import (
    ClaimResult, ClaimToRun, Status, iter_assertions,
)
from notlob.bindings.python.assemble import assemble_with_deps
from notlob.bindings.python.harness import (
    build_examples_harness, build_properties_harness, build_tests_harness,
)
from notlob.model import Module


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

_DEFINITION_START = re.compile(r"(?:async\s+def|def|class|import|from)\b|@")

_SWALLOWED_CODE_HINT = (
    "this line is a statement, not an assertion -- code placed directly "
    "after a claim is absorbed into the claim's body, so separate the "
    "claim from the code with a line of prose"
)


def _is_statement_not_assertion(expr: str) -> bool:
    """Whether *expr* reads as a statement rather than an assertion.

    A claim body ends only at the first non-indented, non-blank line,
    so an indented code block straight after an ``~example`` is absorbed
    into it and then fails as an assertion with a bare "invalid syntax".
    Definitions and imports are recognised by their leading keyword
    (they are not valid on a single line, so compiling can't tell);
    anything else that is not a valid expression but is a valid
    statement (an assignment, say) counts too.
    """
    if _DEFINITION_START.match(expr):
        return True
    try:
        compile(expr, "<claim>", "eval")
        return False
    except SyntaxError:
        pass
    try:
        compile(expr, "<claim>", "exec")
        return True
    except SyntaxError:
        return False


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
                    if (len(eparts) > 1 and eparts[1] == "SyntaxError"
                            and _is_statement_not_assertion(expr)):
                        msg = f"{msg} -- {_SWALLOWED_CODE_HINT}"
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
                    exc_type = fparts[1] if len(fparts) > 1 else None
                    results.append(ClaimResult(
                        address=addr, line=sigil, status=Status.FAIL,
                        error=RuntimeError(
                            f"{exc_type}: {msg}" if exc_type else msg
                        ),
                        source_line=sl, file_path=file_path,
                    ))
                elif result_line.startswith("ERROR\t"):
                    eparts = result_line.split("\t", 2)
                    msg = (
                        _deliteral(eparts[2]) if len(eparts) > 2
                        else result_line[6:]
                    )
                    exc_type = eparts[1] if len(eparts) > 1 else None
                    results.append(ClaimResult(
                        address=addr, line=sigil, status=Status.ERROR,
                        error=RuntimeError(
                            f"{exc_type}: {msg}" if exc_type else msg
                        ),
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

def _module_source(
    module: Module, deps: Sequence[Module], file_path: Path | None,
) -> str:
    """Return *module*'s code, with the dependencies notlob handed over
    inlined before it -- the subprocess harness has no loader around it
    at execution time, so dependency source has to be inlined directly,
    same as ``build_python``.

    The module's own ``__file__`` is the ``.lob`` file it is written in,
    as it was under the original in-process loader; the harness script
    would otherwise be what code sees. A build sets none: an artifact is
    portable."""
    prelude = (f"__file__ = {str(Path(file_path).resolve())!r}"
               if file_path is not None else "")
    return assemble_with_deps(module, list(deps), prelude)


# ── What the claims handed over come to ─────────────────────────

def _assertions(
    claims: Sequence[ClaimToRun],
) -> list[tuple[str, str, int | None]]:
    """Return ``(addr, expr, source_line)`` for every assertion in the
    ``~example`` claims and tests of *claims*. A claim is split into its
    assertions by this language's own rules (``_iter_assertions``)."""
    assertions: list[tuple[str, str, int | None]] = []
    for claim in claims:
        for assertion, offset in _iter_assertions(claim.lines):
            sl = (claim.first_line + offset) if claim.first_line else None
            assertions.append((claim.address, assertion, sl))
    return assertions


def _properties(
    claims: Sequence[ClaimToRun],
) -> list[tuple[str, str, int | None, str]]:
    """Return ``(addr, sigil, source_line, prop_block_source)`` for every
    ``~property`` in *claims*."""
    return [
        (claim.address,
         "~property" + (f" {claim.name}" if claim.name else ""),
         claim.sigil_line,
         textwrap.dedent("\n".join(claim.lines)))
        for claim in claims
    ]


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
    claims: Sequence[ClaimToRun],
    *,
    file_path: Path | None = None,
    root: Path | None = None,
    keep_dir: Path | None = None,
    deps: Sequence[Module] = (),
) -> list[ClaimResult]:
    """Run the ~example *claims* of a module and return results.

    Runs in a subprocess under the ``PATH``-resolved interpreter (see
    module docstring); *root*, the project root, is accepted for the
    shared ``BindingKit`` call site but unused -- *deps*, the modules
    whose code the module needs (dependencies first), are inlined into
    the harness source.

    *keep_dir*, when provided, causes the harness script actually run
    to be written to ``<keep_dir>/_examples.py`` for inspection.
    """
    assertions = _assertions(claims)
    if not assertions:
        return []

    source = _module_source(module, deps, file_path)
    script = build_examples_harness(
        source, assertions, _notlob_site_packages(),
    )
    keep_path = (keep_dir / "_examples.py") if keep_dir else None
    stdout, stderr, _rc = _run_harness(script, keep_path=keep_path)

    fp = str(file_path) if file_path else None
    return _parse_protocol(stdout, stderr, assertions, fp)


def run_tests(
    module: Module,
    claims: Sequence[ClaimToRun],
    *,
    binding: dict | None = None,
    file_path: Path | None = None,
    root: Path | None = None,
    keep_dir: Path | None = None,
    deps: Sequence[Module] = (),
) -> list[ClaimResult]:
    """Run the tests in *claims*, the assertions in #Tests, and return
    results.

    Each run of bare assertions is reported at its own address,
    <module>#Tests#<group>#test#<n> (<module>#Tests#test#<n> outside any
    group).  A ``~test <name>`` block gets its own address
    (<module>#Tests#<group>#<name>), with every assertion line inside
    it sharing that one address -- matching how an unnamed ~example
    block's own lines already share one address, distinguished by
    source line rather than a per-line ordinal.  Prose commentary
    interspersed with assertions (at either level) is not evaluated.

    *binding*/*root* are accepted for signature compatibility with
    the shared ``BindingKit`` call site but unused. ``pytest`` comes
    from notlob's own install as a ``sys.path`` fallback -- see module
    docstring and ``_notlob_site_packages``.

    *keep_dir*, when provided, causes the harness script actually run
    to be written to ``<keep_dir>/_tests.py`` for inspection.

    Assembly errors produce a single ERROR result as with run_examples.
    """
    assertions = _assertions(claims)
    if not assertions:
        return []

    source = _module_source(module, deps, file_path)
    script = build_tests_harness(source, assertions, _notlob_site_packages())
    keep_path = (keep_dir / "_tests.py") if keep_dir else None
    stdout, stderr, _rc = _run_harness(script, keep_path=keep_path)

    fp = str(file_path) if file_path else None
    return _parse_protocol(stdout, stderr, assertions, fp)


def run_properties(
    module: Module,
    claims: Sequence[ClaimToRun],
    *,
    binding: dict | None = None,
    file_path: Path | None = None,
    root: Path | None = None,
    keep_dir: Path | None = None,
    deps: Sequence[Module] = (),
) -> list[ClaimResult]:
    """Run the ~property *claims* of a module and return results.

    Each claim block execs into its own fresh copy of the
    post-module, post-hypothesis-injection namespace within one
    combined subprocess -- isolating the ephemeral witness function
    from the module's permanent state and from other properties'
    witnesses, matching the previous in-process behaviour's per-claim
    namespace copy.

    *binding*/*root* are accepted for signature compatibility with
    the shared ``BindingKit`` call site but unused. ``hypothesis``
    comes from notlob's own install as a ``sys.path`` fallback -- see
    module docstring and ``_notlob_site_packages``.

    Named properties (`~property name`) use the sigil name as address.
    Unnamed properties use an ordinal: <containing>#property#n.

    *keep_dir*, when provided, causes the harness script actually run
    to be written to ``<keep_dir>/_properties.py`` for inspection.

    Assembly errors produce a single ERROR result as with run_examples.
    """
    properties = _properties(claims)
    if not properties:
        return []

    source = _module_source(module, deps, file_path)
    script = build_properties_harness(
        source, properties, _notlob_site_packages(),
    )
    keep_path = (keep_dir / "_properties.py") if keep_dir else None
    stdout, stderr, _rc = _run_harness(script, keep_path=keep_path)

    fp = str(file_path) if file_path else None
    return _parse_property_protocol(stdout, stderr, properties, fp)
