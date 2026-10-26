"""notlob.bindings.typescript.runner — claim runner for the TypeScript binding.

Builds a ``tsx`` harness from assembled module code, executes it as a
subprocess, and parses the output into ``ClaimResult`` objects.

Runner discovery
----------------
tsx is located in this order:

1. ``node_modules/.bin/tsx`` relative to the project root (preferred —
   uses the project's own pinned version).
2. ``tsx`` on PATH (global or shell-managed install).
3. ``ts-node`` on PATH (fallback).

If none is found all claim functions return a single ERROR result.

Output protocol
---------------
Each assertion produces two consecutive stdout lines::

    CLAIM\\t<address>\\t<expression>
    PASS

or::

    CLAIM\\t<address>\\t<expression>
    FAIL\\t<lhs_json>\\t<rhs_json>

or::

    CLAIM\\t<address>\\t<expression>
    ERROR\\t<message>

For boolean expressions (no root ``===``), the line is a bare ``FAIL``
with no values (lhs=None, rhs=None in the ClaimResult), so the report
does not show a ``right: None`` that would read as a missing side.

A compile / startup error (non-zero exit, no CLAIM lines in stdout) is
reported as a single ERROR result with line ``'<assembly>'``.

Left/right extraction
---------------------
The Python-side harness generator splits claim expressions at the first
top-level ``===`` using the tokenizer, emitting two arrow-function
arguments so the harness can report concrete evaluated values on
failure.  Expressions with no top-level ``===`` (booleans, ``!==``,
method chains) are passed as a single boolean arrow function.

Properties
----------
``run_properties`` uses fast-check, which is part of the TypeScript
binding toolchain.  No ``~property-testing`` declaration is needed in
``binding.lob`` — ``~language typescript`` is sufficient.  Each
``~property`` block is wrapped in a ``fc.assert`` harness and executed
via tsx.  If fast-check is not installed, every ``~property`` claim
receives ``Status.ERROR``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Generator, Sequence

from notlob.bindings import ClaimResult, ClaimToRun, Status
from notlob.graph import module_address
from notlob.model import Module
from notlob.bindings.typescript.assemble import assemble
from notlob.bindings.typescript.tokenizer import find_split, is_complete


# ── TypeScript harness template ───────────────────────────────

_HARNESS_HEADER = """\
function __runClaim(
  addr: string, expr: string,
  lhsFn: () => unknown,
  rhsFn: (() => unknown) | null,
): void {
  process.stdout.write('CLAIM\\t' + addr + '\\t' + expr + '\\n');
  try {
    const lhs = lhsFn();
    if (rhsFn === null) {
      process.stdout.write(Boolean(lhs) ? 'PASS\\n' : 'FAIL\\n');
    } else {
      const rhs = rhsFn();
      process.stdout.write(lhs === rhs ? 'PASS\\n'
        : 'FAIL\\t' + __safeStr(lhs) + '\\t' + __safeStr(rhs) + '\\n');
    }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    process.stdout.write('ERROR\\t' + msg + '\\n');
  }
}
function __safeStr(v: unknown): string {
  try { return JSON.stringify(v); } catch { return String(v); }
}
"""


_PROPERTY_HARNESS_HEADER = """\
import * as fc from 'fast-check';

function __runProperty(
  addr: string,
  expr: string,
  fn:   () => void,
): void {
  process.stdout.write('CLAIM\\t' + addr + '\\t' + expr + '\\n');
  try {
    fn();
    process.stdout.write('PASS\\n');
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    process.stdout.write('ERROR\\t' + msg + '\\n');
  }
}
"""


# ── Runner discovery ──────────────────────────────────────────

def node_bin(name: str, root: Path | None) -> str | None:
    """Resolve an npm-installed binary, cross-platform.

    Checks project-local ``node_modules/.bin`` first, then PATH.

    On Windows, npm creates a ``<name>.cmd`` wrapper that ``subprocess``
    can execute; the extensionless file is a Unix shell script and fails
    with ``WinError 193`` if invoked directly.  The ``.cmd``/``.exe``
    variant is therefore preferred there.
    """
    exts = ('.cmd', '.exe', '.bat', '') if os.name == 'nt' else ('',)

    if root is not None:
        bin_dir = root / 'node_modules' / '.bin'
        for ext in exts:
            candidate = bin_dir / (name + ext)
            if candidate.is_file():
                return str(candidate)

    for ext in exts:
        found = shutil.which(name + ext)
        if found:
            return found
    return None


def _tsx_cmd(root: Path | None) -> list[str] | None:
    """Return the tsx command list, or None if no runner is available.

    Prefers project-local ``node_modules/.bin/tsx``; falls back to
    ``tsx`` then ``ts-node`` on PATH.
    """
    tsx = node_bin('tsx', root)
    if tsx:
        return [tsx]
    ts_node = node_bin('ts-node', root)
    if ts_node:
        return [ts_node]
    return None


def _fast_check_available(root: Path | None) -> bool:
    """Return True if fast-check is installed in the project's node_modules."""
    if root is not None:
        return (root / 'node_modules' / 'fast-check').is_dir()
    return False


# ── Harness execution ─────────────────────────────────────────

def _run_harness(
    harness:      str,
    cmd:          list[str],
    keep_path:    Path | None = None,
    env:          dict | None = None,
    program_args: list[str] | None = None,
) -> tuple[str, str, int]:
    """Write *harness* to a temp file, execute with *cmd*, return
    ``(stdout, stderr, returncode)``.

    If *keep_path* is set the harness is also written there (for
    ``--keep-generated-src`` debugging). *program_args*, when given,
    are appended after the temp file path -- for ``notlob run``'s own
    program arguments, not used by the claim runners (run_examples/
    run_tests/run_properties never take user-supplied args), matching
    the Haskell runner's equivalent ``program_args`` parameter.
    """
    if keep_path is not None:
        keep_path.parent.mkdir(parents=True, exist_ok=True)
        keep_path.write_text(harness, encoding='utf-8')

    with tempfile.NamedTemporaryFile(
        suffix='.ts', mode='w', encoding='utf-8', delete=False,
    ) as f:
        f.write(harness)
        tmp_path = f.name

    try:
        proc = subprocess.run(
            cmd + [tmp_path] + (program_args or []),
            stdin=subprocess.DEVNULL,   # don't inherit parent stdin
            capture_output=True,
            encoding='utf-8',
            errors='replace',
            env=env,
        )
        return proc.stdout, proc.stderr, proc.returncode
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── Module source assembly ────────────────────────────────────

def _build_module_source(module: Module, deps: Sequence[Module]) -> str:
    """Return assembled module source with the sources of *deps*, the
    modules whose code it needs, prepended in the order they are handed
    over (dependencies first)."""
    parts: list[str] = []

    for dep_mod in deps:
        dep_src = assemble(dep_mod)
        if dep_src:
            parts.append(dep_src)

    mod_src = assemble(module)
    if mod_src:
        parts.append(mod_src)

    return '\n\n'.join(parts)


# ── Assertion iteration ───────────────────────────────────────

def _iter_assertions(lines: list[str]) -> Generator[tuple[str, int], None, None]:
    """Yield ``(expression, line_offset)`` from raw claim lines."""
    from notlob.bindings import iter_assertions
    yield from iter_assertions(lines, is_complete=is_complete)


# ── Harness generation ────────────────────────────────────────

def _claim_call(addr: str, expr: str) -> str:
    """Return a ``__runClaim(...)`` TypeScript call for *expr*.

    For ``a === b`` expressions the call passes separate lhs and rhs
    arrow functions so the harness can report concrete values on
    failure.  For all other expressions (boolean guards, ``!==``, etc.)
    a single arrow function is passed with ``null`` for rhs.
    """
    addr_s = json.dumps(addr)
    expr_s = json.dumps(expr)
    split  = find_split(expr)
    if split is not None:
        pos, op = split
        if op == '===':
            lhs = expr[:pos].rstrip()
            rhs = expr[pos + 3:].lstrip()
            return (
                f'__runClaim({addr_s}, {expr_s},\n'
                f'  () => ({lhs}),\n'
                f'  () => ({rhs}));\n'
            )
    # Boolean expression or !==: single lambda
    return f'__runClaim({addr_s}, {expr_s}, () => ({expr}), null);\n'


def _build_harness(module_source: str, claim_calls: list[str]) -> str:
    """Combine module source, harness header, and claim calls."""
    parts = [_HARNESS_HEADER]
    if module_source:
        parts.append(module_source)
    parts.append('\n'.join(claim_calls))
    return '\n\n'.join(parts)


def _property_call(addr: str, sigil: str, lines: list[str]) -> str:
    """Return a ``__runProperty(...)`` TypeScript call for a ~property block.

    The entire block body is passed as a zero-argument arrow function so
    the harness can catch fast-check assertion failures and report them
    via the CLAIM protocol.  ``fc`` is available in scope via the
    property harness import.
    """
    addr_s  = json.dumps(addr)
    sigil_s = json.dumps(sigil)
    body    = textwrap.indent(textwrap.dedent('\n'.join(lines)), '  ')
    return (
        f'__runProperty({addr_s}, {sigil_s}, () => {{\n'
        f'{body}\n'
        f'}});\n'
    )


def _build_property_harness(module_source: str, property_calls: list[str]) -> str:
    """Combine module source, property harness header, and property calls."""
    parts = [_PROPERTY_HARNESS_HEADER]
    if module_source:
        parts.append(module_source)
    parts.append('\n'.join(property_calls))
    return '\n\n'.join(parts)


# ── Output parsing ────────────────────────────────────────────

def _parse_output(
    stdout:        str,
    stderr:        str,
    fallback_addr: str,
    source_lines:  list[int | None] | None = None,
    file_path:     Path | None = None,
) -> list[ClaimResult]:
    """Parse the CLAIM/PASS/FAIL/ERROR protocol from *stdout*."""
    fp = str(file_path) if file_path else None
    results: list[ClaimResult] = []
    lines = stdout.splitlines()
    i = 0
    claim_n = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('CLAIM\t'):
            parts = line.split('\t', 2)
            addr  = parts[1] if len(parts) > 1 else fallback_addr
            expr  = parts[2] if len(parts) > 2 else ''
            sl = (source_lines[claim_n]
                  if source_lines and claim_n < len(source_lines)
                  else None)
            claim_n += 1
            i += 1
            if i < len(lines):
                res = lines[i]
                if res == 'PASS':
                    results.append(ClaimResult(
                        address=addr, line=expr, status=Status.PASS,
                        source_line=sl, file_path=fp,
                    ))
                elif res.startswith('FAIL\t'):
                    rparts = res.split('\t', 2)
                    left   = _dejson(rparts[1] if len(rparts) > 1 else '')
                    right  = _dejson(rparts[2] if len(rparts) > 2 else '')
                    results.append(ClaimResult(
                        address=addr, line=expr, status=Status.FAIL,
                        left=left, right=right,
                        source_line=sl, file_path=fp,
                    ))
                elif res == 'FAIL':
                    results.append(ClaimResult(
                        address=addr, line=expr, status=Status.FAIL,
                        source_line=sl, file_path=fp,
                    ))
                elif res.startswith('ERROR\t'):
                    results.append(ClaimResult(
                        address=addr, line=expr, status=Status.ERROR,
                        error=Exception(res[6:]),
                        source_line=sl, file_path=fp,
                    ))
                else:
                    results.append(ClaimResult(
                        address=addr, line=expr, status=Status.ERROR,
                        error=Exception(f'unexpected output: {res!r}'),
                        source_line=sl, file_path=fp,
                    ))
        i += 1
    return results


def _dejson(s: str) -> Any:
    """Best-effort JSON decode; return the raw string on failure."""
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return s or None


def _assembly_error(
    addr: str,
    stderr: str,
    file_path: Path | None = None,
) -> list[ClaimResult]:
    msg = stderr.strip() or 'tsx exited with no output'
    return [ClaimResult(
        address=addr,
        line='<assembly>',
        status=Status.ERROR,
        error=Exception(msg),
        file_path=str(file_path) if file_path else None,
    )]


# ── What the claims handed over come to ───────────────────────

def _claim_calls(
    claims: Sequence[ClaimToRun],
) -> tuple[list[str], list[int | None]]:
    """The ``__runClaim(...)`` call for every assertion of the
    ``~example`` claims and tests in *claims*, and the line each is on.
    A claim is split into its assertions by this language's own rule
    (``_iter_assertions``)."""
    calls: list[str] = []
    lines: list[int | None] = []
    for claim in claims:
        for expr, offset in _iter_assertions(claim.lines):
            calls.append(_claim_call(claim.address, expr))
            lines.append(
                (claim.first_line + offset) if claim.first_line else None
            )
    return calls, lines


def _property_calls(
    claims: Sequence[ClaimToRun],
) -> tuple[list[str], list[str], list[str], list[int | None]]:
    """The ``__runProperty(...)`` call for each ~property in *claims*,
    with its address, its sigil and the line of its sigil."""
    calls, addrs, sigils, lines = [], [], [], []
    for claim in claims:
        sigil = '~property' + (f' {claim.name}' if claim.name else '')
        calls.append(_property_call(claim.address, sigil, claim.lines))
        addrs.append(claim.address)
        sigils.append(sigil)
        lines.append(claim.sigil_line)
    return calls, addrs, sigils, lines


# ── Keep-generated-src ────────────────────────────────────────

def _write_kept_source(
    keep_dir: Path | None,
    filename: str,
    source:   str,
) -> Path | None:
    if keep_dir is None:
        return None
    keep_dir.mkdir(parents=True, exist_ok=True)
    path = keep_dir / filename
    path.write_text(source, encoding='utf-8')
    return path


# ── Public runners ────────────────────────────────────────────

def run_examples(
    module:    Module,
    claims:    Sequence[ClaimToRun],
    *,
    file_path: Path | None = None,
    root:      Path | None = None,
    keep_dir:  Path | None = None,
    deps:      Sequence[Module] = (),
) -> list[ClaimResult]:
    """Run the ~example *claims* of *module* and return results."""
    cmd      = _tsx_cmd(root)
    mod_addr = module_address(module.title)

    if cmd is None:
        return [ClaimResult(
            address=mod_addr, line='<runner>',
            status=Status.ERROR,
            error=Exception('tsx or ts-node not found on PATH or in node_modules/.bin'),
        )]

    mod_source = _build_module_source(module, deps)

    claim_calls, src_lines = _claim_calls(claims)
    if not claim_calls:
        return []

    harness   = _build_harness(mod_source, claim_calls)
    keep_path = _write_kept_source(keep_dir, '_examples.ts', harness)
    stdout, stderr, rc = _run_harness(harness, cmd, keep_path)

    results = _parse_output(stdout, stderr, mod_addr, src_lines, file_path)
    if not results and rc != 0:
        return _assembly_error(mod_addr, stderr, file_path)
    return results


def run_tests(
    module:    Module,
    claims:    Sequence[ClaimToRun],
    *,
    binding:   dict | None = None,
    file_path: Path | None = None,
    root:      Path | None = None,
    keep_dir:  Path | None = None,
    deps:      Sequence[Module] = (),
) -> list[ClaimResult]:
    """Run the tests in *claims*, the #Tests assertions of *module*, and
    return results."""
    if not claims:
        return []

    cmd      = _tsx_cmd(root)
    mod_addr = module_address(module.title)

    if cmd is None:
        return [ClaimResult(
            address=mod_addr, line='<runner>',
            status=Status.ERROR,
            error=Exception('tsx or ts-node not found on PATH or in node_modules/.bin'),
        )]

    mod_source = _build_module_source(module, deps)
    claim_calls, src_lines = _claim_calls(claims)
    if not claim_calls:
        return []

    harness   = _build_harness(mod_source, claim_calls)
    keep_path = _write_kept_source(keep_dir, '_tests.ts', harness)
    stdout, stderr, rc = _run_harness(harness, cmd, keep_path)

    results = _parse_output(stdout, stderr, mod_addr, src_lines, file_path)
    if not results and rc != 0:
        return _assembly_error(mod_addr, stderr, file_path)
    return results


def run_properties(
    module:    Module,
    claims:    Sequence[ClaimToRun],
    *,
    binding:   dict | None = None,
    file_path: Path | None = None,
    root:      Path | None = None,
    keep_dir:  Path | None = None,
    deps:      Sequence[Module] = (),
) -> list[ClaimResult]:
    """Run the ~property *claims* of *module* using fast-check.

    fast-check is part of the TypeScript binding toolchain; no
    ``~property-testing`` declaration is required in ``binding.lob``.
    Each ``~property`` block is wrapped in a ``__runProperty`` call and
    executed via tsx with ``fc`` available in scope.

    If fast-check is not installed, every claim receives Status.ERROR.
    """
    mod_addr = module_address(module.title)
    fp       = str(file_path) if file_path else None

    prop_calls, prop_addrs, prop_sigils, src_lines = _property_calls(claims)

    if not prop_calls:
        return []

    if not _fast_check_available(root):
        return [
            ClaimResult(
                address=addr,
                line=sig,
                status=Status.ERROR,
                error=Exception(
                    'fast-check not found — run `npm install fast-check` '
                    'in the project root'
                ),
                source_line=sl,
                file_path=fp,
            )
            for addr, sig, sl in zip(prop_addrs, prop_sigils, src_lines)
        ]

    cmd = _tsx_cmd(root)
    if cmd is None:
        return [ClaimResult(
            address=mod_addr, line='<runner>',
            status=Status.ERROR,
            error=Exception('tsx or ts-node not found on PATH or in node_modules/.bin'),
        )]

    mod_source = _build_module_source(module, deps)
    harness    = _build_property_harness(mod_source, prop_calls)
    keep_path  = _write_kept_source(keep_dir, '_properties.ts', harness)

    node_env = {**os.environ, 'NODE_PATH': str(root / 'node_modules')} if root else None
    stdout, stderr, rc = _run_harness(harness, cmd, keep_path, env=node_env)

    results = _parse_output(stdout, stderr, mod_addr, src_lines, file_path)
    if not results and rc != 0:
        return _assembly_error(mod_addr, stderr, file_path)
    return results
