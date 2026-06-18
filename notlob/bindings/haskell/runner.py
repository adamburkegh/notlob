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
``run_properties`` requires ``~property-testing quickcheck`` in
``binding.lob``.  Without this declaration every ~property claim
receives ``Status.SKIP``.  With it, each claim is run in its own
subprocess with ``Test.QuickCheck`` loaded.  The property function
named in the claim block is found via :func:`extract_symbols`.

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

import os
import re
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from notlob.bindings import ClaimResult, Status
from notlob.graph import (
    claim_address, module_address, property_address, subheading_address,
)
from notlob.model import Claim, Module, Subheading, TestsSection, TestGroup
from notlob.bindings.haskell.assemble import _assemble_body, _merge_modules
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

    fd, tmp_path = tempfile.mkstemp(suffix=".hs")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
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
                timeout=timeout,
            )
            return proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            return "", f"timeout after {timeout}s", 1
        except FileNotFoundError as exc:
            return "", str(exc), 1
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass


# ── Assertion helpers ─────────────────────────────────────────

def _iter_assertions(lines: list[str]):
    """Yield stripped non-blank lines as individual assertion strings."""
    for raw in lines:
        stripped = raw.strip()
        if stripped:
            yield stripped


def _hs_string_escape(s: str) -> str:
    """Escape *s* for embedding in a Haskell double-quoted string literal."""
    return (
        s.replace("\\", "\\\\")
         .replace('"',  '\\"')
         .replace('\n', '\\n')
         .replace('\r', '\\r')
         .replace('\t', '\\t')
    )


# ── Dependency loading ────────────────────────────────────────

def _load_dep_modules(
    module: Module,
    file_path: Path | None,
) -> list[Module]:
    """Return the lob-ref dependency modules of *module* in declaration order.

    Resolves each ``#Title`` lob-ref in *module*'s ``#References``
    section to its ``.lob`` file under the project root, parses it, and
    returns the resulting Module objects.  Dependencies that cannot be
    found or parsed are silently skipped — GHC will report the missing
    symbol as a compile error, which is surfaced through the normal
    claim-result machinery.

    Returns an empty list when *file_path* is ``None`` (no project
    context available) or when no project root is found.
    """
    if file_path is None:
        return []

    # Lazy imports: keep runner.py free of top-level circular deps
    from notlob.project import (           # noqa: PLC0415
        find_project_root,
        module_lob_refs,
        resolve_module_path,
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
            pass  # missing dep — will surface as GHC compile error

    return result


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
    assertions: list[tuple[str, str]],
    dep_modules: list[Module] | None = None,
) -> str:
    """Build a runghc harness for a list of Boolean assertions.

    *assertions* is an ordered list of ``(address, expression)`` pairs.
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

    parts: list[str] = ["module NotlobRunner where"]

    if import_lines:
        parts.append("\n".join(import_lines))

    if code_chunks:
        parts.append("\n\n".join(_hide_user_main(c) for c in code_chunks))

    parts.append(_CHECK_HELPER)

    main_lines = ["main :: IO ()", "main = do"]
    for addr, expr in assertions:
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

    parts: list[str] = ["module NotlobRunner where"]
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
    assertions: list[tuple[str, str]],
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
    results: list[ClaimResult] = []
    lines = stdout.splitlines()
    i = 0

    while i < len(lines):
        raw = lines[i]
        if raw.startswith("CLAIM\t"):
            parts = raw.split("\t", 2)
            addr = parts[1] if len(parts) > 1 else "?"
            expr = parts[2] if len(parts) > 2 else "<assertion>"
            i += 1
            if i < len(lines):
                result_line = lines[i]
                if result_line == "PASS":
                    results.append(ClaimResult(
                        address=addr, line=expr, status=Status.PASS,
                    ))
                elif result_line == "FAIL":
                    results.append(ClaimResult(
                        address=addr, line=expr, status=Status.FAIL,
                    ))
                elif result_line.startswith("ERROR\t"):
                    msg = result_line[6:]
                    results.append(ClaimResult(
                        address=addr, line=expr, status=Status.ERROR,
                        error=RuntimeError(msg),
                    ))
                else:
                    results.append(ClaimResult(
                        address=addr, line=expr, status=Status.ERROR,
                        error=RuntimeError(
                            f"unexpected runner output: {result_line!r}"
                        ),
                    ))
            else:
                # CLAIM line with no following result — runtime crash
                err_msg = stderr.strip() or "runtime error (no result)"
                results.append(ClaimResult(
                    address=addr, line=expr, status=Status.ERROR,
                    error=RuntimeError(err_msg),
                ))
        i += 1

    # Compile error: process failed before printing any CLAIM line
    if not results and assertions:
        err_msg = stderr.strip() or "compile error"
        addr, expr = assertions[0]
        results.append(ClaimResult(
            address=addr, line="<compile>", status=Status.ERROR,
            error=RuntimeError(err_msg),
        ))

    return results


def _parse_property_output(
    stdout: str,
    stderr: str,
    returncode: int,
    addr: str,
    sigil: str,
) -> ClaimResult:
    """Parse a single-property harness output into one ClaimResult."""
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
        )

    if result_line == "PASS":
        return ClaimResult(address=addr, line=sigil, status=Status.PASS)

    fail_detail = result_line[5:] if result_line.startswith("FAIL\t") else result_line
    return ClaimResult(
        address=addr, line=sigil, status=Status.FAIL,
        error=RuntimeError(fail_detail),
    )


# ── Claim collectors ──────────────────────────────────────────

def _collect_example_assertions(
    body: list,
    containing_addr: str,
    assertions: list[tuple[str, str]],
) -> None:
    """Append (address, expression) pairs from ~example claims in body."""
    example_n = 0
    for item in body:
        if not (isinstance(item, Claim) and item.sigil == "~example"):
            continue
        example_n += 1
        addr = claim_address(containing_addr, "example", example_n)
        for expr in _iter_assertions(item.lines):
            assertions.append((addr, expr))


def _collect_tests_assertions(
    tests_section: TestsSection,
    tests_addr: str,
    assertions: list[tuple[str, str]],
) -> None:
    """Append (address, expression) pairs from a TestsSection."""
    bare: list[str] = []
    for item in tests_section.items:
        if isinstance(item, str):
            bare.append(item)
        else:
            for expr in _iter_assertions(bare):
                assertions.append((tests_addr, expr))
            bare = []
            group_addr = f"{tests_addr}#{item.title}"
            for expr in _iter_assertions(item.lines):
                assertions.append((group_addr, expr))
    for expr in _iter_assertions(bare):
        assertions.append((tests_addr, expr))


# ── Public claim runners ──────────────────────────────────────

def run_examples(
    module: Module,
    file_path: Path | None = None,
    cache: Any = None,
    keep_dir: Path | None = None,
) -> list[ClaimResult]:
    """Run all ~example claims in *module* and return results.

    Builds a single runghc harness containing all ~example assertions
    across the module body and all subheadings, executes it, and
    returns one ClaimResult per assertion line.

    *file_path* is used to locate the project root for dependency
    resolution; lob-ref dependencies are inlined into the harness.

    If *keep_dir* is set the harness source is written there as
    ``_examples.hs`` before execution.
    """
    mod_addr = module_address(module.title)
    assertions: list[tuple[str, str]] = []

    _collect_example_assertions(module.body, mod_addr, assertions)
    for item in module.body:
        if isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            _collect_example_assertions(item.body, sub_addr, assertions)

    if not assertions:
        return []

    dep_modules = _load_dep_modules(module, file_path)
    harness     = _build_examples_harness(module, assertions, dep_modules)
    keep_path   = (keep_dir / "_examples.hs") if keep_dir else None
    stdout, stderr, rc = _run_harness(harness, keep_path=keep_path)
    return _parse_output(stdout, stderr, rc, assertions)


def run_tests(
    module: Module,
    binding: dict | None = None,
    file_path: Path | None = None,
    cache: Any = None,
    keep_dir: Path | None = None,
) -> list[ClaimResult]:
    """Run all #Tests assertions in *module* and return results.

    Assertions are treated as Boolean Haskell expressions, one per
    non-blank assertion line.  Named ``##`` groups receive addresses of
    the form ``<module>#Tests#<group>``; ungrouped assertions use
    ``<module>#Tests``.

    If *keep_dir* is set the harness source is written there as
    ``_tests.hs`` before execution.
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

    mod_addr   = module_address(module.title)
    tests_addr = f"{mod_addr}#Tests"
    assertions: list[tuple[str, str]] = []

    _collect_tests_assertions(tests_section, tests_addr, assertions)

    if not assertions:
        return []

    dep_modules = _load_dep_modules(module, file_path)
    harness     = _build_examples_harness(module, assertions, dep_modules)
    keep_path   = (keep_dir / "_tests.hs") if keep_dir else None
    stdout, stderr, rc = _run_harness(harness, keep_path=keep_path)
    return _parse_output(stdout, stderr, rc, assertions)


def run_properties(
    module: Module,
    binding: dict | None = None,
    file_path: Path | None = None,
    cache: Any = None,
    keep_dir: Path | None = None,
) -> list[ClaimResult]:
    """Run all ~property claims in *module* and return results.

    Requires ``~property-testing quickcheck`` in ``binding.lob``.
    Without this declaration every ~property claim yields SKIP.

    Each claim block is run in its own subprocess.  The property
    function name is extracted from the claim lines using the Haskell
    symbol extractor; the first function found in the block is used.

    Named properties (``~property name``) use the sigil name as the
    address fragment; unnamed properties use an ordinal.

    If *keep_dir* is set each property harness is written there as
    ``_prop_<name>.hs`` before execution.
    """
    use_qc = (
        binding is not None
        and binding.get("property-testing") == "quickcheck"
    )

    mod_addr    = module_address(module.title)
    dep_modules = _load_dep_modules(module, file_path)
    results: list[ClaimResult] = []
    prop_n = 0

    def _run_prop_in(body: list, containing_addr: str) -> None:
        nonlocal prop_n
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

            if not use_qc:
                results.append(ClaimResult(
                    address=addr,
                    line=item.sigil,
                    status=Status.SKIP,
                ))
                continue

            # Find the property function name
            syms = extract_symbols(item.lines)
            if not syms:
                results.append(ClaimResult(
                    address=addr,
                    line=item.sigil,
                    status=Status.ERROR,
                    error=ValueError(
                        "no function found in ~property block; "
                        "define a top-level property function"
                    ),
                ))
                continue

            prop_name  = syms[0].name
            safe_name  = re.sub(r"[^A-Za-z0-9_]", "_", prop_name)
            harness    = _build_property_harness(
                module, item.lines, addr, prop_name, dep_modules,
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
                _parse_property_output(stdout, stderr, rc, addr, item.sigil)
            )

    _run_prop_in(module.body, mod_addr)
    for item in module.body:
        if isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            _run_prop_in(item.body, sub_addr)

    return results
