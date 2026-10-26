"""notlob.bindings.haskell.runner — claim runner for the Haskell binding.

Builds a ``runghc`` harness from the module's code blocks, executes it
as a subprocess, and parses the output into ``ClaimResult`` objects.

Runner discovery
----------------
The runner looks for ``runghc`` in this order:

1. A ``runghc`` executable on PATH.
2. ``stack exec -- runghc`` (Stack build tool).

If neither is found, all claim functions return a single ERROR result
rather than raising.

Output protocol
---------------
Each assertion produces two consecutive output lines::

    CLAIM\\t<address>\\t<expression>
    PASS

or::

    CLAIM\\t<address>\\t<expression>
    FAIL

If the Haskell process exits before printing a result for an assertion
(runtime exception, assertion forced an exception, etc.) the Python
parser reports ERROR for every claim that did not receive a result.

A compile error (non-zero exit, no CLAIM lines in stdout) is reported
as a single ERROR result with line ``"<compile>"``.

Property testing
----------------
``run_properties`` runs each ~property claim in its own subprocess
with ``Test.QuickCheck`` loaded.  QuickCheck is part of the Haskell
binding toolchain — no declaration in ``binding.lob`` is needed.
The property function named in the claim block is found via
:func:`extract_symbols`.

Limitations (v1)
----------------
* Lob-ref dependencies in ``#References`` are not inlined; only
  Haskell ``import`` statements are forwarded to the harness.
* Multi-line assertion expressions (spanning more than one claim line)
  are not supported; each stripped non-blank claim line is one
  assertion.
* Language pragma lines (``{-# LANGUAGE … #-}``) are emitted inline
  in code chunks; they must appear before the ``module`` declaration
  to be valid GHC pragmas.  Users should avoid them in claim blocks or
  put them in a code block at the top of the module body.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Sequence

from notlob.bindings import ClaimResult, ClaimToRun, Status
from notlob.model import Module
from notlob.bindings.haskell.assemble import _merge_modules
from notlob.bindings.haskell.symbols import extract_symbols


# ── Runner discovery ──────────────────────────────────────────

def _make_runghc_cmd(
    tmp_path: str,
    extra_packages: list[str] | None = None,
) -> list[str] | None:
    """Return the command list to execute a .hs file, or None.

    Checks for a direct ``runghc`` on PATH, then falls back to
    ``stack exec [--package ...] -- runghc``.  Returns ``None`` if
    no runner is available.
    """
    if shutil.which("runghc"):
        return ["runghc", tmp_path]
    if shutil.which("stack"):
        cmd = ["stack", "exec"]
        for pkg in (extra_packages or []):
            cmd.extend(["--package", pkg])
        cmd.extend(["--", "runghc", tmp_path])
        return cmd
    return None


# ── Low-level subprocess execution ───────────────────────────

def _run_harness(
    source: str,
    extra_packages: list[str] | None = None,
    timeout: int = 120,
    keep_path: Path | None = None,
    program_args: list[str] | None = None,
) -> tuple[str, str, int]:
    """Write *source* to a temp .hs file and run it with runghc.

    Returns ``(stdout, stderr, returncode)``.  On timeout the stderr
    is a human-readable message and returncode is 1.  If no runner is
    found, returns an appropriate error triple immediately.

    If *keep_path* is provided the source is also written there before
    execution, for inspection.  Errors writing to *keep_path* are
    silently ignored so they never interfere with the test run.
    """
    if keep_path is not None:
        try:
            keep_path.parent.mkdir(parents=True, exist_ok=True)
            keep_path.write_text(source, encoding="utf-8")
        except OSError:
            pass

    # GHC 9.10 runghc requires the entry-point file to be named Main.hs
    # (or to carry an explicit `module Main where` declaration) so that
    # the runtime can locate `main`.  A randomly-named temp file without
    # a module declaration is treated as a module named after the file,
    # and runghc then fails with "Not in scope: main".  Writing into a
    # temp *directory* as Main.hs is the simplest cross-platform fix.
    tmpdir = tempfile.mkdtemp()
    tmp_path = str(Path(tmpdir) / "Main.hs")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(source)

        cmd = _make_runghc_cmd(tmp_path, extra_packages)
        if cmd is None:
            return "", "no Haskell runner found (install runghc or stack)", 1
        if program_args:
            cmd = cmd + program_args

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            return proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            return "", f"timeout after {timeout}s", 1
        except FileNotFoundError as exc:
            return "", str(exc), 1
    finally:
        import shutil
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except OSError:
            pass


# ── Assertion helpers ─────────────────────────────────────────

def _iter_assertions(lines: list[str]):
    """Yield ``(expression, line_offset)`` for non-blank lines."""
    from notlob.bindings import iter_assertions
    yield from iter_assertions(lines)


def _hs_string_escape(s: str) -> str:
    """Escape *s* for embedding in a Haskell double-quoted string literal."""
    return (
        s.replace("\\", "\\\\")
         .replace('"',  '\\"')
         .replace('\n', '\\n')
         .replace('\r', '\\r')
         .replace('\t', '\\t')
    )


# ── Harness builders ──────────────────────────────────────────

_CHECK_HELPER = """\
_notlobCheck :: String -> String -> Bool -> IO ()
_notlobCheck addr expr result = do
  putStrLn $ "CLAIM\\t" ++ addr ++ "\\t" ++ expr
  if result
    then putStrLn "PASS"
    else putStrLn "FAIL"\
"""

_MAIN_RE = re.compile(r"^main(?=\s|:)", re.MULTILINE)


def _hide_user_main(source: str) -> str:
    """Rename top-level ``main`` to ``_notlobUserMain``.

    Prevents a duplicate-declaration error when the user's module
    defines its own ``main`` and the test harness also defines ``main``.
    The renamed binding is unreachable but keeps GHC happy.
    """
    return _MAIN_RE.sub("_notlobUserMain", source)


def _build_examples_harness(
    module: Module,
    assertions: list[tuple[str, str, int | None]],
    dep_modules: list[Module] | None = None,
) -> str:
    """Build a runghc harness for a list of Boolean assertions.

    *assertions* is an ordered list of ``(address, expression, source_line)`` triples.
    The harness calls ``_notlobCheck`` for each assertion in order and
    prints CLAIM / PASS / FAIL lines.

    *dep_modules*, when provided, are inlined before *module*'s own
    code so every symbol they define is in scope.

    If any code chunk defines ``main``, it is renamed to
    ``_notlobUserMain`` so it does not clash with the harness entry
    point.
    """
    import_lines, code_chunks = _merge_modules(
        (dep_modules or []) + [module]
    )

    parts: list[str] = []

    if import_lines:
        parts.append("\n".join(import_lines))

    if code_chunks:
        parts.append("\n\n".join(_hide_user_main(c) for c in code_chunks))

    parts.append(_CHECK_HELPER)

    main_lines = ["main :: IO ()", "main = do"]
    for addr, expr, _sl in assertions:
        ea = _hs_string_escape(addr)
        ee = _hs_string_escape(expr)
        main_lines.append(
            f'  _notlobCheck "{ea}" "{ee}" ({expr})'
        )
    parts.append("\n".join(main_lines))

    return "\n\n".join(parts) + "\n"


def _build_property_harness(
    module: Module,
    prop_lines: list[str],
    addr: str,
    prop_name: str,
    dep_modules: list[Module] | None = None,
) -> str:
    """Build a runghc harness for a single QuickCheck property.

    The harness imports ``Test.QuickCheck``, inlines *dep_modules* and
    *module*'s own code, appends the property definition from
    *prop_lines*, then runs ``quickCheckWithResult`` on *prop_name* and
    prints PASS or FAIL.
    """
    import_lines, code_chunks = _merge_modules(
        (dep_modules or []) + [module]
    )

    parts: list[str] = []
    # Import specific names so the harness works with any QuickCheck version
    parts.append(
        "import Test.QuickCheck"
        " (quickCheckWithResult, stdArgs, Args(..), Result(..))"
    )

    if import_lines:
        parts.append("\n".join(import_lines))

    if code_chunks:
        parts.append("\n\n".join(_hide_user_main(c) for c in code_chunks))

    prop_code = textwrap.dedent("\n".join(prop_lines)).strip()
    if prop_code:
        parts.append(prop_code)

    ea = _hs_string_escape(addr)
    main_src = "\n".join([
        "main :: IO ()",
        "main = do",
        f'  putStrLn $ "CLAIM\\t{ea}\\t{_hs_string_escape(prop_name)}"',
        # chatty=False suppresses QuickCheck's own progress output so
        # it does not interleave with our PASS/FAIL protocol lines.
        f"  result <- quickCheckWithResult"
        f" (stdArgs {{ chatty = False }}) {prop_name}",
        "  case result of",
        '    Success {} -> putStrLn "PASS"',
        '    _ -> putStrLn $ "FAIL\\t" ++ show result',
    ])
    parts.append(main_src)

    return "\n\n".join(parts) + "\n"


# ── Output parsers ────────────────────────────────────────────

def _parse_output(
    stdout: str,
    stderr: str,
    returncode: int,
    assertions: list[tuple[str, str, int | None]],
    file_path: Path | None = None,
) -> list[ClaimResult]:
    """Parse harness stdout into ClaimResult objects.

    Expected stdout format (two lines per assertion)::

        CLAIM\\t<address>\\t<expression>
        PASS

    or::

        CLAIM\\t<address>\\t<expression>
        FAIL

    A CLAIM line with no following result line indicates a crash;
    that assertion and all subsequent unrun assertions are ERROR.

    If stdout has no CLAIM lines at all and the process failed, a
    single ERROR result is returned for the first assertion (covering
    the compile-error case).
    """
    fp = str(file_path) if file_path else None
    results: list[ClaimResult] = []
    lines = stdout.splitlines()
    i = 0
    claim_n = 0

    while i < len(lines):
        raw = lines[i]
        if raw.startswith("CLAIM\t"):
            parts = raw.split("\t", 2)
            addr = parts[1] if len(parts) > 1 else "?"
            expr = parts[2] if len(parts) > 2 else "<assertion>"
            sl = (assertions[claim_n][2]
                  if claim_n < len(assertions) else None)
            claim_n += 1
            i += 1
            if i < len(lines):
                result_line = lines[i]
                if result_line == "PASS":
                    results.append(ClaimResult(
                        address=addr, line=expr, status=Status.PASS,
                        source_line=sl, file_path=fp,
                    ))
                elif result_line == "FAIL":
                    results.append(ClaimResult(
                        address=addr, line=expr, status=Status.FAIL,
                        source_line=sl, file_path=fp,
                    ))
                elif result_line.startswith("ERROR\t"):
                    msg = result_line[6:]
                    results.append(ClaimResult(
                        address=addr, line=expr, status=Status.ERROR,
                        error=RuntimeError(msg),
                        source_line=sl, file_path=fp,
                    ))
                else:
                    results.append(ClaimResult(
                        address=addr, line=expr, status=Status.ERROR,
                        error=RuntimeError(
                            f"unexpected runner output: {result_line!r}"
                        ),
                        source_line=sl, file_path=fp,
                    ))
            else:
                err_msg = stderr.strip() or "runtime error (no result)"
                results.append(ClaimResult(
                    address=addr, line=expr, status=Status.ERROR,
                    error=RuntimeError(err_msg),
                    source_line=sl, file_path=fp,
                ))
        i += 1

    if not results and assertions:
        err_msg = stderr.strip() or "compile error"
        addr, expr, sl = assertions[0]
        results.append(ClaimResult(
            address=addr, line="<compile>", status=Status.ERROR,
            error=RuntimeError(err_msg),
            source_line=sl, file_path=fp,
        ))

    return results


def _parse_property_output(
    stdout: str,
    stderr: str,
    returncode: int,
    addr: str,
    sigil: str,
    source_line: int | None = None,
    file_path: Path | None = None,
) -> ClaimResult:
    """Parse a single-property harness output into one ClaimResult."""
    fp = str(file_path) if file_path else None
    lines = stdout.splitlines()
    result_line = None
    for i, raw in enumerate(lines):
        if raw.startswith("CLAIM\t") and i + 1 < len(lines):
            result_line = lines[i + 1]
            break

    if result_line is None:
        err = stderr.strip() or "compile error"
        return ClaimResult(
            address=addr, line="<compile>",
            status=Status.ERROR, error=RuntimeError(err),
            source_line=source_line, file_path=fp,
        )

    if result_line == "PASS":
        return ClaimResult(
            address=addr, line=sigil, status=Status.PASS,
            source_line=source_line, file_path=fp,
        )

    fail_detail = result_line[5:] if result_line.startswith("FAIL\t") else result_line
    return ClaimResult(
        address=addr, line=sigil, status=Status.FAIL,
        error=RuntimeError(fail_detail),
        source_line=source_line, file_path=fp,
    )


# ── What the claims handed over come to ───────────────────────

def _assertions(
    claims: Sequence[ClaimToRun],
) -> list[tuple[str, str, int | None]]:
    """Return (address, expression, source_line) for every assertion of
    the ``~example`` claims and tests in *claims*.

    A claim is split into its assertions by this language's own rule
    (``_iter_assertions``), one for each non-blank line.
    """
    assertions: list[tuple[str, str, int | None]] = []
    for claim in claims:
        for expr, offset in _iter_assertions(claim.lines):
            sl = (claim.first_line + offset) if claim.first_line else None
            assertions.append((claim.address, expr, sl))
    return assertions


# ── Public claim runners ──────────────────────────────────────

def run_examples(
    module: Module,
    claims: Sequence[ClaimToRun],
    *,
    file_path: Path | None = None,
    root: Path | None = None,
    keep_dir: Path | None = None,
    deps: Sequence[Module] = (),
) -> list[ClaimResult]:
    """Run the ~example *claims* of *module* and return results.

    Builds a single runghc harness containing all their assertions,
    executes it, and returns one ClaimResult per assertion line.

    *deps*, the modules whose code *module* needs (dependencies first),
    are inlined into the harness.

    If *keep_dir* is set the harness source is written there as
    ``_examples.hs`` before execution.
    """
    assertions = _assertions(claims)
    if not assertions:
        return []

    harness     = _build_examples_harness(module, assertions, list(deps))
    keep_path   = (keep_dir / "_examples.hs") if keep_dir else None
    stdout, stderr, rc = _run_harness(harness, keep_path=keep_path)
    return _parse_output(stdout, stderr, rc, assertions, file_path)


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
    """Run the tests in *claims*, the #Tests assertions of *module*, and
    return results.

    Assertions are treated as Boolean Haskell expressions, one per
    non-blank assertion line.  Each run of bare assertions is reported
    at its own address, ``<module>#Tests#<group>#test#<n>``
    (``<module>#Tests#test#<n>`` outside any group).

    If *keep_dir* is set the harness source is written there as
    ``_tests.hs`` before execution.
    """
    assertions = _assertions(claims)
    if not assertions:
        return []

    harness     = _build_examples_harness(module, assertions, list(deps))
    keep_path   = (keep_dir / "_tests.hs") if keep_dir else None
    stdout, stderr, rc = _run_harness(harness, keep_path=keep_path)
    return _parse_output(stdout, stderr, rc, assertions, file_path)


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
    """Run the ~property *claims* of *module* and return results.

    Each claim block is run in its own subprocess.  The property
    function name is extracted from the claim lines using the Haskell
    symbol extractor; the first function found in the block is used.

    A claim reports at the address notlob gave it: a named property's
    name, or an ordinal among the properties of the section it is in.

    If *keep_dir* is set each property harness is written there as
    ``_prop_<name>.hs`` before execution.
    """
    dep_modules = list(deps)
    results: list[ClaimResult] = []

    for claim in claims:
        addr  = claim.address
        sigil = "~property" + (f" {claim.name}" if claim.name else "")
        sl    = claim.sigil_line

        syms = extract_symbols(claim.lines)
        if not syms:
            results.append(ClaimResult(
                address=addr,
                line=sigil,
                status=Status.ERROR,
                error=ValueError(
                    "no function found in ~property block; "
                    "define a top-level property function"
                ),
                source_line=sl,
                file_path=str(file_path) if file_path else None,
            ))
            continue

        prop_name  = syms[0].name
        safe_name  = re.sub(r"[^A-Za-z0-9_]", "_", prop_name)
        harness    = _build_property_harness(
            module, claim.lines, addr, prop_name, dep_modules,
        )
        keep_path  = (
            keep_dir / f"_prop_{safe_name}.hs"
        ) if keep_dir else None
        stdout, stderr, rc = _run_harness(
            harness,
            extra_packages=["QuickCheck"],
            keep_path=keep_path,
        )
        results.append(
            _parse_property_output(
                stdout, stderr, rc, addr, sigil,
                source_line=sl, file_path=file_path,
            )
        )

    return results

    return results
