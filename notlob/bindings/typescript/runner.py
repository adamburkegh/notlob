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

For boolean expressions (no top-level ``===``), the FAIL line omits
the JSON values (lhs=None, rhs=None in the ClaimResult).

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
``run_properties`` requires ``~property-testing fast-check`` in
``binding.lob``.  Without this declaration every ``~property`` claim
receives ``Status.SKIP``.  Fast-check integration is planned for a
future iteration.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Generator

from notlob.bindings import ClaimResult, Status
from notlob.graph import (
    claim_address, module_address, property_address, subheading_address,
)
from notlob.model import Claim, Module, Subheading, TestGroup, TestsSection
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
      process.stdout.write(Boolean(lhs) ? 'PASS\\n'
        : 'FAIL\\t' + __safeStr(lhs) + '\\tnull\\n');
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


# ── Harness execution ─────────────────────────────────────────

def _run_harness(
    harness:   str,
    cmd:       list[str],
    keep_path: Path | None = None,
) -> tuple[str, str, int]:
    """Write *harness* to a temp file, execute with *cmd*, return
    ``(stdout, stderr, returncode)``.

    If *keep_path* is set the harness is also written there (for
    ``--keep-generated-src`` debugging).
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
            cmd + [tmp_path],
            stdin=subprocess.DEVNULL,   # don't inherit parent stdin
            capture_output=True,
            encoding='utf-8',
            errors='replace',
        )
        return proc.stdout, proc.stderr, proc.returncode
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── Module source assembly ────────────────────────────────────

def _build_module_source(module: Module, root: Path | None) -> str:
    """Return assembled module source with dep sources prepended.

    Dependencies declared as lob-refs in ``#References`` are assembled
    and inlined before the module's own code, mirroring what the Python
    runner achieves via ``ModuleCache``.
    """
    parts: list[str] = []

    if root is not None:
        from notlob import from_tree, parse_file
        from notlob.project import module_lob_refs, resolve_module_path
        for dep_addr in module_lob_refs(module):
            try:
                dep_path = resolve_module_path(dep_addr, root)
                dep_mod  = from_tree(parse_file(dep_path))
                dep_src  = assemble(dep_mod)
                if dep_src:
                    parts.append(dep_src)
            except Exception:
                pass   # missing dep surfaces as a claim execution error

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


# ── Section collectors ────────────────────────────────────────

def _collect_example_claims(
    body:            list,
    containing_addr: str,
    out:             list[str],
    out_lines:       list[int | None] | None = None,
) -> None:
    """Append ``__runClaim(...)`` lines for ~example blocks in *body*."""
    example_n = 0
    for item in body:
        if not (isinstance(item, Claim) and item.sigil == '~example'):
            continue
        example_n += 1
        addr = claim_address(containing_addr, 'example', example_n)
        base = (item.start_line + 1) if item.start_line else None
        for expr, offset in _iter_assertions(item.lines):
            out.append(_claim_call(addr, expr))
            if out_lines is not None:
                out_lines.append(
                    (base + offset) if base else None
                )


def _collect_tests_claims(
    tests_section: TestsSection,
    tests_addr:    str,
    out:           list[str],
    out_lines:     list[int | None] | None = None,
) -> None:
    """Append ``__runClaim(...)`` lines for #Tests assertions."""
    line_offsets = tests_section.line_offsets or {}
    bare: list[str] = []
    bare_indices: list[int] = []
    for idx, item in enumerate(tests_section.items):
        if isinstance(item, str):
            bare.append(item)
            bare_indices.append(idx)
        else:
            if bare:
                first_line = line_offsets.get(bare_indices[0])
                for expr, offset in _iter_assertions(bare):
                    out.append(_claim_call(tests_addr, expr))
                    if out_lines is not None:
                        out_lines.append(
                            (first_line + offset) if first_line else None
                        )
                bare = []
                bare_indices = []
            group_addr = f'{tests_addr}#{item.title}'
            base = (item.start_line + 1) if item.start_line else None
            for expr, offset in _iter_assertions(item.lines):
                out.append(_claim_call(group_addr, expr))
                if out_lines is not None:
                    out_lines.append(
                        (base + offset) if base else None
                    )
    if bare:
        first_line = line_offsets.get(bare_indices[0])
        for expr, offset in _iter_assertions(bare):
            out.append(_claim_call(tests_addr, expr))
            if out_lines is not None:
                out_lines.append(
                    (first_line + offset) if first_line else None
                )


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
    file_path: Path | None = None,
    cache:     Any         = None,
    keep_dir:  Path | None = None,
) -> list[ClaimResult]:
    """Run all ~example claims in *module* and return results."""
    root     = getattr(cache, 'root', None)
    cmd      = _tsx_cmd(root)
    mod_addr = module_address(module.title)

    if cmd is None:
        return [ClaimResult(
            address=mod_addr, line='<runner>',
            status=Status.ERROR,
            error=Exception('tsx or ts-node not found on PATH or in node_modules/.bin'),
        )]

    mod_source = _build_module_source(module, root)

    claim_calls: list[str] = []
    src_lines: list[int | None] = []
    _collect_example_claims(module.body, mod_addr, claim_calls, src_lines)
    for item in module.body:
        if isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            _collect_example_claims(item.body, sub_addr, claim_calls, src_lines)

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
    binding:   dict | None = None,
    file_path: Path | None = None,
    cache:     Any         = None,
    keep_dir:  Path | None = None,
) -> list[ClaimResult]:
    """Run all #Tests assertions in *module* and return results."""
    if module.post_text is None:
        return []
    tests_section = next(
        (s for s in module.post_text.sections if isinstance(s, TestsSection)),
        None,
    )
    if tests_section is None:
        return []

    root     = getattr(cache, 'root', None)
    cmd      = _tsx_cmd(root)
    mod_addr = module_address(module.title)

    if cmd is None:
        return [ClaimResult(
            address=mod_addr, line='<runner>',
            status=Status.ERROR,
            error=Exception('tsx or ts-node not found on PATH or in node_modules/.bin'),
        )]

    mod_source   = _build_module_source(module, root)
    claim_calls: list[str] = []
    src_lines: list[int | None] = []
    _collect_tests_claims(tests_section, f'{mod_addr}#Tests',
                          claim_calls, src_lines)

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
    binding:   dict | None = None,
    file_path: Path | None = None,
    cache:     Any         = None,
    keep_dir:  Path | None = None,
) -> list[ClaimResult]:
    """Run ~property claims in *module*.

    Requires ``~property-testing fast-check`` in ``binding.lob``.
    Without this declaration every ~property claim receives SKIP.
    Fast-check integration is planned for a future iteration.
    """
    mod_addr = module_address(module.title)

    fp = str(file_path) if file_path else None

    def _props_in(body: list, containing_addr: str) -> list[ClaimResult]:
        results = []
        prop_n = 0
        for item in body:
            if not (isinstance(item, Claim)
                    and item.sigil.startswith('~property')):
                continue
            prop_n += 1
            parts     = item.sigil.split(None, 1)
            prop_name = parts[1].strip() if len(parts) > 1 else None
            addr      = (
                property_address(containing_addr, prop_name)
                if prop_name else
                claim_address(containing_addr, 'property', prop_n)
            )
            results.append(ClaimResult(
                address=addr,
                line=item.sigil,
                status=Status.SKIP,
                source_line=item.start_line,
                file_path=fp,
            ))
        return results

    if binding is None or binding.get('property-testing') != 'fast-check':
        results = _props_in(module.body, mod_addr)
        for item in module.body:
            if isinstance(item, Subheading):
                sub_addr = subheading_address(mod_addr, item.title)
                results += _props_in(item.body, sub_addr)
        return results

    # fast-check integration: TODO
    return []
