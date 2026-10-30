"""notlob.commands — Command implementations for the notlob CLI.

The public functions here implement the ``notlob run`` and
``notlob test`` commands.  They accept a resolved :class:`pathlib.Path`
and return an integer exit code.  All argument parsing and entry-point
wiring lives in :mod:`notlob.cli`, which delegates here.

Validation order in ``cmd_test``
---------------------------------
1. Parse the module.
2. Check that the module's title-derived address matches its file path.
3. Validate all prose cross-references.
4. Run examples, properties, and #Tests claims.

Steps 2 and 3 are document-integrity checks; a failure short-circuits
before any claim execution.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from functools import lru_cache
from importlib.metadata import entry_points
from pathlib import Path

from notlob import (
    build, enrich, from_tree, parse_file, validate_refs,
    EdgeKind, NodeKind, AddressCollisionError,
)
from notlob.bindings import (
    ClaimResult, LintResult, LintToolUnavailable, Status,
)
from notlob.bindings.python.runner import _resolve_python_interpreter
from notlob.bindings import ClaimToRun
from notlob.graph import (
    KINDS, NameGraph, Node, cited_by_edges, cites_edges, claims_to_run,
    content_tree, module_address, node_summary, parse_level, sigil_of,
)
from notlob.model import BindingSection
from notlob.project import (
    LobRefCycleError,
    address_from_path,
    build_package,
    find_project_root,
    load_dependencies,
)


def use_utf8_streams(*streams) -> None:
    """Make the standard streams write (and read) UTF-8.

    Without this Python picks the system codepage for a pipe or a
    redirect, which cannot hold most of the text a `.lob` file may.
    Streams that cannot be reconfigured (a test's capture, say) are
    left as they are.
    """
    for stream in streams or (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


# ── Language dispatch ─────────────────────────────────────────

@lru_cache(maxsize=None)
def _load_binding_kit(name: str):
    """Load ``(kit, extract_symbols)`` for *name* from the binding registry.

    Bindings are discovered via Python entry points in the
    ``"notlob.bindings"`` group.  Third-party packages register a
    binding by declaring an entry point whose name is the language
    identifier (e.g. ``"rust"``) and whose value is a module that
    exposes a ``kit: BindingKit`` and an ``extract_symbols`` callable.
    The three built-in bindings (``python``, ``haskell``,
    ``typescript``) are registered the same way in ``pyproject.toml``.
    """
    eps = {ep.name: ep for ep in entry_points(group="notlob.bindings")}
    if name not in eps:
        available = sorted(eps)
        raise ValueError(
            f"no binding registered for language {name!r} -- "
            f"available: {available}"
        )
    mod = eps[name].load()
    return mod.kit, mod.extract_symbols


def _get_binding_kit(language: str | None):
    """Return ``(kit, extract_symbols)`` for the given language name.

    ``None`` (no ``~language`` declared) defaults to Python.
    Unknown language names raise ``ValueError``.
    """
    return _load_binding_kit(language or "python")


# ── Binding resolution ────────────────────────────────────────

def _binding_to_dict(section: BindingSection) -> dict:
    """Convert a typed BindingSection to the string dict used throughout
    this module.  Keys match the old ~sigil names so all call sites that
    read ``binding.get("language")`` etc. continue to work unchanged.
    """
    result: dict = {}
    if section.language is not None:
        result['language'] = section.language
    if section.externals:
        result['external'] = section.externals
    if section.on_build is not None:
        result['on-build'] = section.on_build
    if section.keep_generated_src is not None:
        result['keep-generated-src'] = section.keep_generated_src
    return result


def _find_binding(file_path: Path) -> dict[str, str]:
    """Walk up from *file_path* to find binding.lob; return its
    declarations.  Returns an empty dict if none is found.
    """
    root = find_project_root(file_path)
    if root is None:
        return {}
    try:
        bmod = from_tree(parse_file(root / "binding.lob"))
        if bmod.post_text:
            for section in bmod.post_text.sections:
                if isinstance(section, BindingSection):
                    return _binding_to_dict(section)
    except Exception:
        pass
    return {}


# ── Address validation ────────────────────────────────────────

def _check_address(
    module,
    path: Path,
    root: Path | None,
) -> str | None:
    """Return an error string if title address ≠ path address, else None.

    A standalone file (no project root) is exempt: there is no folder
    structure to validate against.
    """
    if root is None:
        return None
    expected = address_from_path(path, root)
    actual   = module_address(module.title)
    if actual != expected:
        return (
            f"address mismatch: title gives {actual!r}, "
            f"file path gives {expected!r}"
        )
    return None


# ── Formatting ────────────────────────────────────────────────

#: Version of the ``notlob test --format json`` document (see
#: ``notlob/schema/test_result.json``). Bumped on a breaking change.
_TEST_JSON_VERSION = 1


#: Version of the ``notlob check --format json`` document
#: (``notlob/schema/check_result.json``). Bumped on a breaking change.
_CHECK_JSON_VERSION = 1


def _finding_dict(f) -> dict:
    """Convert a ``notlob.check.Finding`` to its JSON form (the
    ``CheckFinding`` definition shared by ``check_result.json`` and
    ``test_result.json``)."""
    return {
        "check": f.check,
        "message": f.message,
        "addresses": list(f.addresses),
        "severity": f.severity,
    }


def _collision_finding(exc: AddressCollisionError) -> dict:
    """The ``names`` finding reported for an address collision, in the
    shared ``CheckFinding`` shape. It is not a check ``notlob check``
    runs: the graph could not be built, so no check could."""
    return {
        "check": "names",
        "message": str(exc),
        "addresses": [exc.address],
        "severity": "error",
    }


def _project_relative(file_path: str, root: Path | None) -> str:
    """*file_path* as notlob prints a file: relative to the project *root*,
    with forward slashes (the form of a module address). Outside a project
    (no *root*, or the file is outside it) it is the path as the command
    was given it, which is relative to the working directory when the file
    is under it."""
    p = Path(file_path)
    base = root if root is not None else Path.cwd()
    try:
        return p.resolve().relative_to(base.resolve()).as_posix()
    except (ValueError, OSError):
        return p.as_posix()


def _result_dict(r: ClaimResult, kind: str, root: Path | None) -> dict:
    """Convert a ClaimResult to a JSON-serialisable dict.

    *kind* is ``EXAMPLE``, ``PROPERTY`` or ``TEST``; ``source`` is the
    assertion text and ``line`` its 1-based line number in ``file``.
    """
    d: dict = {
        "address": r.address,
        "kind": kind,
        "status": r.status.name,
        "source": r.line,
    }
    if r.file_path:
        d["file"] = _project_relative(r.file_path, root)
    if r.source_line:
        d["line"] = r.source_line
    if r.status == Status.FAIL:
        if r.left is not None:
            d["left"] = repr(r.left)
        if r.right is not None:
            d["right"] = repr(r.right)
    if r.error is not None:
        d["error"] = str(r.error)
    return d


def _lint_dict(r: LintResult) -> dict:
    """Convert a LintResult to a JSON-serialisable dict."""
    return {
        "address": r.address,
        "code": r.code,
        "message": r.message,
        "col": r.col,
    }


def _one_line(text: str) -> str:
    """*text*, a claim written over several lines, on one: each line
    stripped, joined by single spaces."""
    return " ".join(line.strip() for line in text.splitlines())


def _print_result(r: ClaimResult, root: Path | None) -> None:
    tag = r.status.name
    loc = ""
    if r.file_path and r.source_line:
        loc = f"{_project_relative(r.file_path, root)}:{r.source_line}  "
    print(f"{tag:5}  {loc}{r.address}  {_one_line(r.line)}")
    if r.status == Status.FAIL:
        if r.left is not None or r.right is not None:
            print(f"         left:  {r.left!r}")
            print(f"         right: {r.right!r}")
        if r.error is not None:
            print(f"         error: {r.error}")
    elif r.status == Status.ERROR and r.error is not None:
        print(f"         error: {r.error}")


def _print_lint_result(r: LintResult) -> None:
    print(f"LINT   {r.address}  {r.code}: {r.message} (col {r.col})")


# ── The graph of a command ────────────────────────────────────

def _collision_of(path: Path, collisions: list | None):
    """The collision found for the module at *path* among *collisions*
    (``(path, error)`` as :func:`_package_graph` returns them), or
    ``None``."""
    return next(
        (exc for where, exc in collisions or ()
         if where.resolve() == path.resolve()), None)


def _graph_of_module(
    path: Path, module, root: Path | None, binding: dict | None,
):
    """``(graph, collision)`` for a command that reads one module: the
    package graph in a project, otherwise the module built and enriched on
    its own. *collision* is the error if the module's names collide, and
    then the graph is not to be read."""
    if root is not None:
        graph, collisions = _package_graph(root, binding)
        return graph, _collision_of(path, collisions)
    kit, extract_symbols = _get_binding_kit(
        binding.get("language") if binding else None,
    )
    try:
        graph = build(module)
        enrich(graph, module, extract_symbols, kit.split_imports)
    except AddressCollisionError as exc:
        return None, exc
    return graph, None


def _package_graph(root: Path, binding: dict | None):
    """The package graph of the project at *root*, built once for a
    command, and the collisions found in it as ``(path, error)``.

    A module whose names collide is in the graph without its symbols;
    what is read from it for another module is not affected, and the
    command reports the collision as that module's own error."""
    kit, extract_symbols = _get_binding_kit(
        binding.get("language") if binding else None,
    )
    collisions: list = []
    graph = build_package(
        root, extract_symbols, call_extractor=kit.extract_calls,
        collisions=collisions, split_imports=kit.split_imports)
    return graph, collisions


def _dependencies(graph, module, root: Path | None, kit):
    """``(deps, error)`` for a command that runs, tests or builds
    *module*: the modules whose code it needs, parsed and in load order,
    to hand to the binding (see :func:`notlob.project.load_order`). Worked
    out once, from *graph*. There is nothing to load without a project
    *root*. *error* is the ``ERROR  <imports>`` line when the modules'
    code needs each other in a cycle, and then the module's claims do
    not run."""
    if root is None or graph is None:
        return [], None
    try:
        return load_dependencies(
            graph, module_address(module.title), root, kit), None
    except LobRefCycleError as exc:
        return [], f"ERROR  <imports>  {exc}"


# ── Commands ──────────────────────────────────────────────────

def _resolve_keep_dir(
    cli_path: str | None,
    binding:  dict,
    root:     Path | None,
) -> Path | None:
    """Resolve the keep-generated-src directory from CLI flag and binding.

    The CLI flag takes precedence.  A relative path is resolved against
    the project root when one is available, otherwise against CWD.
    """
    raw = cli_path or binding.get("keep-generated-src")
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = (root / p) if root else (Path.cwd() / p)
    return p


def _cmd_run_haskell(
    module,
    claims: list[ClaimToRun],
    path: Path,
    keep_dir: Path | None = None,
    args: list[str] | None = None,
    deps: list | None = None,
) -> int:
    """Assemble a Haskell module (with inlined deps) and run with runghc.

    Uses :func:`notlob.bindings.haskell.build_haskell` to assemble, so
    the module's own ``~run`` (bare or ``on-invocation``) claim bodies
    are included — that's normally where ``main :: IO ()`` is defined.
    If no ``main`` ends up in scope, GHC reports a link error, which
    surfaces here as a non-zero exit code with the compiler message on
    stderr.  ``~run on-load`` is not supported by the Haskell binding
    and surfaces as an ``ERROR  <run>`` here rather than a crash.

    If *keep_dir* is set the assembled source is also written there as
    ``<module-address-slugified>.hs`` before execution.
    """
    from notlob.bindings.haskell import build_haskell
    from notlob.bindings.haskell.runner import _run_harness

    try:
        source = build_haskell(module, claims, path, deps=deps or ())
    except ValueError as exc:
        print(f"ERROR  <run>  {exc}", file=sys.stderr)
        return 1
    if not source:
        print("ERROR  <run>  nothing to run — module contains no code blocks",
              file=sys.stderr)
        return 1

    if keep_dir is not None:
        from notlob.graph import module_address as _mod_addr
        slug = _mod_addr(module.title).replace("/", "_")
        keep_path = keep_dir / f"{slug}.hs"
    else:
        keep_path = None

    stdout, stderr, rc = _run_harness(source, keep_path=keep_path,
                                       program_args=args or [])
    if stdout:
        print(stdout, end="")
    if rc != 0:
        if stderr:
            print(stderr, end="", file=sys.stderr)
        return 1
    return 0


def _cmd_run_typescript(
    module,
    claims: list[ClaimToRun],
    path: Path,
    keep_dir: Path | None = None,
    args: list[str] | None = None,
    deps: list | None = None,
) -> int:
    """Assemble a TypeScript module (with inlined deps) and run with
    tsx/ts-node.

    Uses :func:`notlob.bindings.typescript.build_typescript` to
    assemble, so the module's own ``~run`` bodies are included --
    ``on-load`` at module scope unconditionally, bare/``on-invocation``
    wrapped in a Node entry-point guard (see that function's docstring).

    If *keep_dir* is set the assembled source is also written there as
    ``<module-address-slugified>.ts`` before execution.
    """
    from notlob.bindings.typescript import build_typescript
    from notlob.bindings.typescript.runner import _run_harness, _tsx_cmd
    from notlob.project import find_project_root

    root = find_project_root(path)
    try:
        source = build_typescript(module, claims, path, deps=deps or ())
    except Exception as exc:
        print(f"ERROR  <run>  {exc}", file=sys.stderr)
        return 1
    if not source:
        print("ERROR  <run>  nothing to run — module contains no code blocks",
              file=sys.stderr)
        return 1

    cmd = _tsx_cmd(root)
    if cmd is None:
        print(
            "ERROR  <run>  no tsx/ts-node found on PATH or in "
            "node_modules/.bin -- install tsx (npm install -D tsx)",
            file=sys.stderr,
        )
        return 1

    if keep_dir is not None:
        from notlob.graph import module_address as _mod_addr
        slug = _mod_addr(module.title).replace("/", "_")
        keep_path = keep_dir / f"{slug}.ts"
    else:
        keep_path = None

    stdout, stderr, rc = _run_harness(source, cmd, keep_path=keep_path,
                                       program_args=args or [])
    if stdout:
        print(stdout, end="")
    if rc != 0:
        if stderr:
            print(stderr, end="", file=sys.stderr)
        return 1
    return 0


def cmd_run(
    path: Path,
    keep_generated_src: str | None = None,
    args: list[str] | None = None,
) -> int:
    """Assemble and execute *path*; return an exit code."""
    try:
        module = from_tree(parse_file(path))
    except Exception as exc:
        print(f"ERROR  <parse>  {exc}", file=sys.stderr)
        return 1

    binding  = _find_binding(path)
    language = binding.get("language")
    root     = find_project_root(path)

    graph, collision = _graph_of_module(path, module, root, binding)
    if collision is not None:
        print(f"ERROR  <names>  {collision}", file=sys.stderr)
        return 1
    claims = claims_to_run(graph, module_address(module.title))

    py_kit, _ = _get_binding_kit(language)
    deps, deps_err = _dependencies(graph, module, root, py_kit)
    if deps_err:
        print(deps_err, file=sys.stderr)
        return 1

    if language == "haskell":
        keep_dir = _resolve_keep_dir(keep_generated_src, binding, root)
        return _cmd_run_haskell(
            module, claims, path, keep_dir=keep_dir, args=args, deps=deps)

    if language == "typescript":
        keep_dir = _resolve_keep_dir(keep_generated_src, binding, root)
        return _cmd_run_typescript(
            module, claims, path, keep_dir=keep_dir, args=args, deps=deps)

    addr_err = _check_address(module, path, root)
    if addr_err:
        print(f"ERROR  <address>  {addr_err}", file=sys.stderr)
        return 1

    try:
        source = py_kit.build(module, claims, path, deps=deps)
    except Exception as exc:
        print(f"ERROR  <assembly>  {exc}", file=sys.stderr)
        return 1
    if not source:
        print("ERROR  <run>  nothing to run — module contains no code",
              file=sys.stderr)
        return 1

    interpreter = _resolve_python_interpreter()
    if interpreter is None:
        print("ERROR  <run>  no Python interpreter found on PATH",
              file=sys.stderr)
        return 1

    tmpdir = tempfile.mkdtemp()
    try:
        tmp_path = Path(tmpdir) / f"{path.stem}.py"
        tmp_path.write_text(source, encoding="utf-8")
        # PYTHONIOENCODING forces the child interpreter's own stdout to
        # UTF-8 -- without it, a module printing non-ASCII content
        # (e.g. from a Unicode heading title) crashes inside the child
        # on Windows, where the default is the console codepage.
        child_env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.run(
            [interpreter, str(tmp_path), *(args or [])],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            env=child_env,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if proc.stdout:
        print(proc.stdout, end="")
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
        return 1
    return 0


def _test_module(
    path:               Path,
    root:               Path | None,
    binding:            dict,
    keep_generated_src: str | None      = None,
    only:               set[str] | None = None,
    json_out:           dict | None     = None,
    graph:              NameGraph | None = None,
    collisions:         list | None     = None,
) -> tuple[int, int, int]:
    """Test one module; print per-claim output (or collect into *json_out*).

    *json_out*, when given, is a dict with ``"claims"`` and ``"lint"``
    lists that this call appends to instead of printing.

    *graph* is the package graph of the project the module is in, with
    the *collisions* found building it (see :func:`_package_graph`);
    without one the module is built and enriched on its own.

    Returns *(n_pass, n_fail, n_lint)*.  Parse or document errors count
    as one failure and short-circuit claim execution.
    """
    try:
        module = from_tree(parse_file(path))
    except Exception as exc:
        print(f"ERROR  <parse>  {exc}", file=sys.stderr)
        return 0, 1, 0

    language = binding.get("language")
    kit, extract_symbols = _get_binding_kit(language)
    keep_dir = _resolve_keep_dir(keep_generated_src, binding, root)

    run_lint     = only is None or "lint"     in only
    run_examples = only is None or "examples" in only
    run_props    = only is None or "props"    in only
    run_tests_   = only is None or "tests"    in only

    doc_errors: list[str] = []

    addr_err = _check_address(module, path, root)
    if addr_err:
        doc_errors.append(f"ERROR  <address>  {addr_err}")

    collision = _collision_of(path, collisions)
    ref_graph = graph
    if ref_graph is None:
        try:
            ref_graph = build(module)
            enrich(ref_graph, module, extract_symbols, kit.split_imports)
        except AddressCollisionError as exc:
            collision = exc

    deps: list = []
    if collision is not None:
        doc_errors.append(f"ERROR  <names>  {collision}")
    else:
        for ref_err in validate_refs(ref_graph, module):
            doc_errors.append(f"ERROR  <refs>  {ref_err}")
        deps, deps_err = _dependencies(ref_graph, module, root, kit)
        if deps_err:
            doc_errors.append(deps_err)

    if doc_errors:
        for msg in doc_errors:
            print(msg, file=sys.stderr)
        return 0, 1, 0

    # What notlob found to run, from the graph: each binding is handed the
    # kinds it runs.
    claims = claims_to_run(ref_graph, module_address(module.title))

    def _of(kind: str) -> list[ClaimToRun]:
        return [c for c in claims if c.kind == kind]

    # ── Lint ──────────────────────────────────────────────────
    lint_results: list[LintResult] = []
    if run_lint and kit.lint is not None:
        try:
            lint_results = kit.lint(module, claims, root=root)
        except LintToolUnavailable as exc:
            # The binding declares a linter but its tool is missing.
            # Fail loudly rather than silently skip — a missing checker
            # must never be reported as a pass.
            print(f"ERROR  <lint>  {exc}", file=sys.stderr)
            return 0, 1, 0
        if json_out is None:
            for r in lint_results:
                _print_lint_result(r)

    # ── Claims ────────────────────────────────────────────────
    kinded: list[tuple[str, ClaimResult]] = []
    if run_examples:
        kinded += [("EXAMPLE", r) for r in kit.run_examples(
            module, _of("EXAMPLE"), file_path=path, root=root,
            keep_dir=keep_dir, deps=deps,
        )]
    if run_props:
        kinded += [("PROPERTY", r) for r in kit.run_properties(
            module, _of("PROPERTY"), binding=binding, file_path=path,
            root=root, keep_dir=keep_dir, deps=deps,
        )]
    if run_tests_:
        kinded += [("TEST", r) for r in kit.run_tests(
            module, _of("TEST"), binding=binding, file_path=path,
            root=root, keep_dir=keep_dir, deps=deps,
        )]
    results = [r for _, r in kinded]

    non_skip = [r for r in results if r.status != Status.SKIP]
    if json_out is not None:
        json_out["claims"] += [
            _result_dict(r, kind, root) for kind, r in kinded
        ]
        json_out["lint"] += [_lint_dict(r) for r in lint_results]
    else:
        for r in results:
            _print_result(r, root)

    n_fail = sum(1 for r in non_skip if r.status != Status.PASS)
    n_pass = len(non_skip) - n_fail
    n_lint = len(lint_results)
    return n_pass, n_fail, n_lint


def cmd_test(
    path:               Path | None      = None,
    keep_generated_src: str | None       = None,
    only:               set[str] | None  = None,
    fmt:                str              = "text",
    graph:              NameGraph | None = None,
    collisions:         list | None      = None,
) -> int:
    """Run claims in *path* (or all project modules) and return an exit code.

    *fmt* is ``"text"`` (the default) or ``"json"``, the document
    described by ``schema/test_result.json``.

    When *path* is omitted, discovers the project from CWD and tests
    every module.  Pass a specific *.lob* path to test a single module.

    *only* restricts which check types run.  When *None* all checks run.
    Valid values in the set: ``"lint"``, ``"examples"``, ``"props"``,
    ``"tests"``.  Lint failures produce exit code 1 just like claim
    failures.

    In a project the package graph is built once, before the modules are
    tested (or given as *graph*, with its *collisions*, by a command that
    already built it): each module's references are validated against it
    and the closing checks read it.  A module whose names collide is
    reported as an error of its own and the others are still tested; the
    closing checks then report the collision instead of running on a
    graph that lacks that module's symbols.
    """
    json_mode = fmt == "json"
    json_out: dict | None = (
        {"claims": [], "lint": []} if json_mode else None
    )

    if path is not None:
        root    = find_project_root(path)
        binding = _find_binding(path)
        if root is not None and graph is None:
            graph, collisions = _package_graph(root, binding)
        n_pass, n_fail, n_lint = _test_module(
            path, root, binding, keep_generated_src, only,
            json_out=json_out, graph=graph, collisions=collisions,
        )
    else:
        root, binding = _require_root()
        if root is None:
            return 1
        if graph is None:
            graph, collisions = _package_graph(root, binding)
        n_pass = n_fail = n_lint = 0
        for lob_path in sorted(root.glob("**/*.lob")):
            if lob_path.name == "binding.lob":
                continue
            p, f, lint = _test_module(
                lob_path, root, binding, keep_generated_src, only,
                json_out=json_out, graph=graph, collisions=collisions,
            )
            n_pass += p
            n_fail += f
            n_lint += lint

    check_errors = False
    check_findings: list[dict] = []
    if path is None:
        if json_mode and collisions:
            check_findings = [_collision_finding(collisions[0][1])]
            check_errors = True
        elif json_mode:
            from notlob.check import has_errors, run_checks
            findings, _ = run_checks(graph)
            check_findings = [_finding_dict(f) for f in findings]
            check_errors = has_errors(findings)
        else:
            check_errors = _run_check_advisory(
                root, binding, graph, collisions)

    if json_mode:
        output = {
            "version": _TEST_JSON_VERSION,
            "summary": {
                "passed": n_pass,
                "failed": n_fail,
                "lint": n_lint,
            },
            "claims": json_out["claims"],
            "lint": json_out["lint"],
        }
        if path is None:
            output["checks"] = check_findings
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        parts = [f"{n_pass} passed"]
        if n_fail:
            parts.append(f"{n_fail} failed")
        if n_lint:
            parts.append(f"{n_lint} lint")
        print(f"\n{', '.join(parts)}")

    return 1 if (n_fail or n_lint or check_errors) else 0


def _run_check_advisory(
    root: Path, binding: dict, graph: NameGraph | None = None,
    collisions: list | None = None,
) -> bool:
    """Run semantic checks and print findings.

    Reads *graph*, the package graph, or builds it when none is given.
    If any module's names *collided* building it, the first collision is
    reported, as an error, and the checks do not run: the graph lacks
    that module's symbols, so another module could get a false finding.
    Returns True if any error-severity findings were found.
    """
    from notlob.check import has_errors, run_checks

    if collisions:
        print(f"ERROR  <names>  {collisions[0][1]}", file=sys.stderr)
        return True
    if graph is None:
        kit, extract_symbols = _get_binding_kit(
            binding.get("language") if binding else None,
        )
        try:
            graph = build_package(
                root, extract_symbols, call_extractor=kit.extract_calls,
                split_imports=kit.split_imports)
        except AddressCollisionError as exc:
            print(f"ERROR  <names>  {exc}", file=sys.stderr)
            return True
    findings, _ = run_checks(graph)
    for f in findings:
        prefix = "ERROR" if f.severity == "error" else "CHECK"
        addrs = ", ".join(f.addresses)
        print(f"{prefix}  [{f.check}]  {f.message}")
        print(f"       {addrs}")
    return has_errors(findings)


# ── Init / docs / new helpers ────────────────────────────────

_DOCS_DIR = Path(__file__).parent / "docs"
_SCHEMA_DIR = Path(__file__).parent / "schema"
_GRAMMAR_PATH = Path(__file__).parent / "grammar.lark"
_GRAMMAR_NOTE = (
    "// This is notlob's syntax reference for .lob files, written by\n"
    "// `notlob docs`. The syntax it defines is what to rely on; its rule\n"
    "// and terminal names may change between notlob versions.\n"
    "//\n"
)


def _binding_docs() -> list[tuple[str, Path]]:
    """``(language, path)`` for each registered binding that has a doc.

    The doc is the ``BINDING.md`` in the binding package's directory.
    The package is located with ``find_spec``, not imported, so a binding
    that fails to import cannot break ``notlob docs``. Bindings that are
    single modules, cannot be found, or carry no ``BINDING.md`` are
    skipped.
    """
    docs: list[tuple[str, Path]] = []
    for ep in sorted(entry_points(group="notlob.bindings"),
                     key=lambda e: e.name):
        if not re.fullmatch(r"[\w.-]+", ep.name):
            continue
        try:
            spec = importlib.util.find_spec(ep.module)
        except (ImportError, ValueError):
            continue
        if spec is None or not spec.submodule_search_locations:
            continue
        doc = Path(next(iter(spec.submodule_search_locations))) / "BINDING.md"
        if doc.is_file():
            docs.append((ep.name, doc))
    return docs


def _address_to_title(address: str) -> str:
    """Convert a module address or directory name to a title string.

    ``'roman/numerals'`` → ``'Roman Numerals'``
    ``'my-project'``     → ``'My Project'``
    """
    parts = (
        address.replace("/", " ")
               .replace("-", " ")
               .replace("_", " ")
               .split()
    )
    return " ".join(p.capitalize() for p in parts)


def _render_binding(project_title: str, language: str) -> str:
    """Return the content of a new ``binding.lob`` file."""
    return (
        f"#{project_title}\n\n"
        "---\n\n"
        "#Binding\n"
        f"    ~language {language}\n"
    )


def _render_starter(module_title: str) -> str:
    """Return the content of a starter ``.lob`` module."""
    return (
        f"#{module_title}\n\n"
        "Describe this module here.\n\n"
        "    code goes here\n\n"
        "Description of a general property of these concepts. Example\n"
        "properties might be roundtrip, preserves, monotone, rejects, or\n"
        "wellformed.\n\n"
        "~property property-name\n"
        "    property assertion code \n\n"
        "More description setting up the example. Properties are often well-served by an example.\n\n"
        "~example\n"
        "    assertion code\n\n"
        "---\n\n"
        "#Tests\n\n"
        "##test group named for what it establishes \n"
        "    anonymous assertion code \n\n"
        "~test named test \n"
        "    assertion code \n\n"
        "#References\n\n"
    )


def _render_agents(project_title: str) -> str:
    """Return the content of a project-level ``AGENTS.md`` file.

    Reads ``USER-AGENTS.md`` from the bundled docs directory and
    substitutes ``{project_title}``.
    """
    template = (_DOCS_DIR / "USER-AGENTS.md").read_text(encoding="utf-8")
    return template.format(project_title=project_title)


def _render_package_json(project_slug: str) -> str:
    """Return a minimal ``package.json`` declaring the TS toolchain.

    notlob is distributed via pip and cannot ship npm packages the way
    it brings ruff for Python, so a TypeScript project provides its own
    toolchain — ``tsx`` to run claims, ``typescript`` (tsc) to
    type-check.  ``notlob init`` generates this manifest so the language
    is declared once (in binding.lob); the user materialises it with
    ``npm install``, the npm analog of ``pip install``.
    """
    data = {
        "name": project_slug,
        "private": True,
        "devDependencies": {
            "fast-check": "^3.0.0",
            "tsx": "^4.0.0",
            "typescript": "^5.4.0",
        },
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _render_tsconfig() -> str:
    """Return a ``tsconfig.json`` aligned with notlob's tsc linter flags.

    Mirrors the options ``lint_typescript`` passes to ``tsc --noEmit``
    so an editor / standalone ``tsc`` agrees with ``notlob test``.
    """
    data = {
        "compilerOptions": {
            "target": "ES2020",
            "module": "ES2020",
            "lib": ["ES2020", "DOM"],
            "moduleResolution": "node",
            "noEmit": True,
            "skipLibCheck": True,
            "strict": False,
        },
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _scaffold_files(language: str, project_slug: str) -> list[tuple[str, str]]:
    """Return ``(filename, content)`` toolchain-scaffolding pairs for
    *language*, beyond binding.lob and the starter module.

    notlob's own ecosystem (Python) needs none — ruff/pytest arrive with
    the pip install.  External-toolchain languages declare their tools
    through the language's native manifest, which notlob generates so the
    language is stated once and the user just runs the package manager.
    """
    if language == "typescript":
        return [
            ("package.json", _render_package_json(project_slug)),
            ("tsconfig.json", _render_tsconfig()),
        ]
    return []


def _scaffold_hint(language: str) -> str | None:
    """Return a post-init next-step hint for languages whose toolchain
    installs separately, or ``None``."""
    if language == "typescript":
        return (
            "Next: run `npm install` to fetch the TypeScript toolchain "
            "(tsx, typescript)."
        )
    return None


# ── Build ─────────────────────────────────────────────────────

def _build_header(
    comment_prefix: str,
    mod_addr: str,
    source_name: str,
) -> str:
    """Return a language-appropriate generated-file header block.

    Uses *comment_prefix* (e.g. ``"#"`` for Python, ``"--"`` for
    Haskell) to produce a short three-line comment that identifies the
    origin of the file and discourages direct editing.
    """
    from notlob import __version__
    c = comment_prefix
    return (
        f"{c} Generated by notlob v{__version__}\n"
        f"{c} Source: {mod_addr} ({source_name})\n"
        f"{c} Do not edit — modify the .lob source instead.\n"
    )


def _build_one(
    path:       Path,
    kit,
    output_dir: Path,
    graph:      NameGraph | None = None,
    collisions: list | None      = None,
) -> tuple[Path | None, bool]:
    """Build a single module and write the artifact to *output_dir*.

    Returns ``(output path, is an entry point)``: the path is None on
    error, and a module is an entry point when it has a ``~run``.
    Prints ``BUILD  <out_path>`` on success, or an ERROR line on failure.
    A module whose names collide is not built.

    *graph* is the package graph of the project the module is in, with
    the *collisions* found building it (see :func:`_package_graph`);
    without one the module is built and enriched on its own.
    """
    try:
        module = from_tree(parse_file(path))
    except Exception as exc:
        print(f"ERROR  <parse>  {exc}", file=sys.stderr)
        return None, False

    collision = _collision_of(path, collisions)
    if graph is None:
        try:
            graph = build(module)
            enrich(graph, module, kit.extract_symbols, kit.split_imports)
        except AddressCollisionError as exc:
            collision = exc
    if collision is not None:
        print(f"ERROR  <names>  {collision}", file=sys.stderr)
        return None, False

    runs = [c for c in claims_to_run(graph, module_address(module.title))
            if c.kind == "RUN"]
    deps, deps_err = _dependencies(
        graph, module, find_project_root(path), kit)
    if deps_err:
        print(deps_err, file=sys.stderr)
        return None, False
    try:
        source = kit.build(module, runs, path, deps=deps)
    except Exception as exc:
        print(f"ERROR  <build>  {exc}", file=sys.stderr)
        return None, False
    if not source:
        return None, False  # prose-only module — skip silently, not an error

    mod_addr = module_address(module.title)
    header   = _build_header(kit.comment_prefix, mod_addr, path.name)
    slug     = mod_addr.replace("/", "_")
    out_path = output_dir / f"{slug}.{kit.extension}"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + "\n" + source, encoding="utf-8")
    print(f"BUILD  {out_path}")
    return out_path, bool(runs)


#: Version of the ``~on-build`` manifest (``notlob/schema/build_manifest.json``).
#: Bumped on a breaking change.
_BUILD_MANIFEST_VERSION = 1


def _hook_runner(
    language: str | None,
    root:     Path,
) -> list[str] | None:
    """Return the command list for running a ~on-build hook script."""
    if language == "typescript":
        from notlob.bindings.typescript.runner import _tsx_cmd
        return _tsx_cmd(root)
    # Default: current Python interpreter
    return [sys.executable]


def _run_build_hook(
    binding:      dict,
    root:         Path | None,
    artifacts:    list[Path],
    output_dir:   Path,
    entry_points: list[Path] | None = None,
) -> None:
    """Run the ``~on-build`` hook script if declared in *binding*.

    The hook receives a JSON manifest, written as UTF-8 without escapes,
    to a temporary file whose path is passed as its first argument.  The
    shape is specified by
    ``notlob/schema/build_manifest.json`` (written to ``schema/`` by
    ``notlob docs``).  The manifest contains:

    ``version``
        Version of the manifest's shape (``_BUILD_MANIFEST_VERSION``).
    ``artifacts``
        Absolute paths of all built output files.
    ``entry_points``
        Subset of *artifacts* whose source modules contain ``~run``
        claims (i.e. program entry points, not library modules).
        Hooks that need to identify the main artifact to bundle or
        execute should prefer this list over ``artifacts``.
    ``externals``
        Absolute paths of files declared with ``~external``.
    ``language``
        The binding language string.
    ``project_root``
        Absolute path of the project root directory.
    ``output_dir``
        Absolute path of the output directory.

    The hook's stdout and stderr are forwarded to the terminal.  A
    non-zero exit code prints a warning but does not fail the build.
    """
    hook_name = binding.get("on-build")
    if not hook_name or root is None:
        return

    script_path = root / hook_name
    if not script_path.exists():
        print(
            f"WARN   <build>  ~on-build script not found: {script_path}",
            file=sys.stderr,
        )
        return

    externals = [
        str((root / ext).resolve())
        for ext in binding.get("external", [])
    ]
    ep_paths   = entry_points if entry_points is not None else artifacts
    manifest = {
        "version":      _BUILD_MANIFEST_VERSION,
        "artifacts":    [str(a.resolve()) for a in artifacts],
        "entry_points": [str(e.resolve()) for e in ep_paths],
        "externals":    externals,
        "language":     binding.get("language"),
        "project_root": str(root.resolve()),
        "output_dir":   str(output_dir.resolve()),
    }

    with tempfile.NamedTemporaryFile(
        suffix=".json", mode="w", encoding="utf-8", delete=False,
    ) as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        manifest_path = f.name

    try:
        cmd = _hook_runner(binding.get("language"), root)
        if cmd is None:
            print(
                "WARN   <build>  no runner found for ~on-build script",
                file=sys.stderr,
            )
            return
        # Flush before the subprocess so its output appears after all
        # buffered Python print() calls — prevents misleading ordering
        # when stdout is not a TTY (pipes, tool captures, CI).
        sys.stdout.flush()
        proc = subprocess.run(
            cmd + [str(script_path), manifest_path],
            stdin=subprocess.DEVNULL,
        )
        if proc.returncode != 0:
            print(
                f"WARN   <build>  ~on-build exited {proc.returncode}",
                file=sys.stderr,
            )
        else:
            print(f"HOOK   {script_path.name}")
    finally:
        try:
            os.unlink(manifest_path)
        except OSError:
            pass


def cmd_build(
    path:        Path | None = None,
    output_dir:  Path        = Path("dist"),
    skip_tests:  bool        = False,
) -> int:
    """Assemble *path* (or all project modules) and write to *output_dir*.

    By default, all claims are run before assembly — the build fails if
    any claim fails or produces a lint diagnostic.  Pass
    *skip_tests=True* (``--skip-tests``) to bypass this check.

    When *path* is omitted, discovers the project from CWD and builds
    every module.  Pass a specific *.lob* path to build a single module.

    After assembly, if the project's ``binding.lob`` declares
    ``~on-build <script>``, that script is invoked with a JSON manifest
    describing the artifacts and any ``~external`` files.

    The output filename is ``<slug>.<ext>`` where *slug* is the module
    address with ``/`` replaced by ``_`` and *ext* is the language
    extension from the binding kit (e.g. ``hs``, ``py``, ``ts``).

    ``~run`` claim bodies are included in build artifacts (unlike
    ``notlob test``, which excludes them).  ``~run`` is the program
    entry point and must be present for the artifact to do anything when
    loaded.
    """
    if path is not None:
        binding  = _find_binding(path)
        language = binding.get("language")
        root     = find_project_root(path)
        kit, _   = _get_binding_kit(language)
        if kit.build is None:
            print(
                f"ERROR  <build>  no build support for language {language!r}",
                file=sys.stderr,
            )
            return 1
        graph = collisions = None
        if root is not None:
            graph, collisions = _package_graph(root, binding)
        if not skip_tests:
            print("TEST   (running claims before build)")
            rc = cmd_test(path, graph=graph, collisions=collisions)
            if rc != 0:
                print(
                    "ERROR  <build>  claims failed — build aborted "
                    "(use --skip-tests to override)",
                    file=sys.stderr,
                )
                return 1
        out_path, is_entry = _build_one(
            path, kit, output_dir, graph, collisions)
        if out_path is None:
            return 1
        entry_points = [out_path] if is_entry else []
        _run_build_hook(binding, root, [out_path], output_dir,
                        entry_points=entry_points)
        return 0

    root, binding = _require_root()
    if root is None:
        return 1
    language = binding.get("language")
    kit, _ = _get_binding_kit(language)
    if kit.build is None:
        print(
            f"ERROR  <build>  no build support for language {language!r}",
            file=sys.stderr,
        )
        return 1

    # The one graph of the build: the modules' references are validated
    # against it, the checks read it, and so do the entry points.
    graph, collisions = _package_graph(root, binding)

    if not skip_tests:
        print("TEST   (running claims before build)")
        rc = 0
        for lob_path in sorted(root.glob("**/*.lob")):
            if lob_path.name == "binding.lob":
                continue
            if cmd_test(lob_path, graph=graph, collisions=collisions) != 0:
                rc = 1
        if rc != 0:
            print(
                "ERROR  <build>  claims failed — build aborted "
                "(use --skip-tests to override)",
                file=sys.stderr,
            )
            return 1

    if _run_check_advisory(root, binding, graph, collisions):
        print(
            "ERROR  <check>  semantic check errors — build aborted",
            file=sys.stderr,
        )
        return 1

    artifacts:    list[Path] = []
    entry_points: list[Path] = []
    rc = 0
    for lob_path in sorted(root.glob("**/*.lob")):
        if lob_path.name == "binding.lob":
            continue
        out_path, is_entry = _build_one(
            lob_path, kit, output_dir, graph, collisions)
        if out_path is not None:
            artifacts.append(out_path)
            if is_entry:
                entry_points.append(out_path)
        else:
            rc = 1
    _run_build_hook(binding, root, artifacts, output_dir,
                    entry_points=entry_points)
    return rc


# ── Graph export ──────────────────────────────────────────────

def cmd_graph(
    path:  Path | None = None,
    fmt:   str         = "json",
    level: str | int | None = None,
) -> int:
    """Print the package name-graph to stdout.

    When *path* is omitted, discovers the project from CWD and exports
    the full package graph.  Pass a specific *.lob* path to export that
    file's module graph (or its project graph when it is inside a
    project).

    The language binding (from ``binding.lob``) controls symbol
    extraction.  *fmt* selects the output format: ``"json"`` (default)
    or ``"turtle"`` (RDF Turtle).  Both are the graph itself at a *level*
    of detail, by name or number (``outline``, the default, ``index`` or
    ``full``; see :meth:`notlob.graph.NameGraph.to_dict`).
    """
    try:
        level = parse_level("outline" if level is None else level)
    except ValueError as exc:
        print(f"ERROR  <graph>  {exc}", file=sys.stderr)
        return 1

    if path is not None:
        root    = find_project_root(path)
        binding = _find_binding(path) if root else {}
    else:
        root, binding = _require_root()
        if root is None:
            return 1

    language = (binding or {}).get("language")
    kit, extract_symbols = _get_binding_kit(language)

    if root is not None:
        try:
            graph = build_package(
                root, extract_symbols, call_extractor=kit.extract_calls,
                split_imports=kit.split_imports)
        except AddressCollisionError as exc:
            print(f"ERROR  <names>  {exc}", file=sys.stderr)
            return 1
    else:
        # standalone file — only reachable via an explicit path arg
        try:
            module = from_tree(parse_file(path))
        except Exception as exc:
            print(f"ERROR  <parse>  {exc}", file=sys.stderr)
            return 1
        try:
            graph = build(module)
            enrich(graph, module, extract_symbols, kit.split_imports)
        except AddressCollisionError as exc:
            print(f"ERROR  <names>  {exc}", file=sys.stderr)
            return 1

    if fmt == "turtle":
        sys.stdout.buffer.write(
            graph.to_turtle(level=level).encode("utf-8")
        )
        sys.stdout.buffer.write(b"\n")
    else:
        print(graph.to_json(level=level))
    return 0


# ── Query helpers ─────────────────────────────────────────────

def _require_root(
    hint: Path | None = None,
) -> tuple[Path, dict] | tuple[None, None]:
    """Return *(root, binding)* for the project containing *hint* (CWD).

    Prints an error and returns *(None, None)* when no project root is
    found.
    """
    root = find_project_root(hint or Path.cwd())
    if root is None:
        print(
            "ERROR  <project>  no binding.lob found — "
            "run from inside a notlob project",
            file=sys.stderr,
        )
        return None, None
    return root, _find_binding(root / "binding.lob")


def _require_graph(
    hint: Path | None = None, *, raise_on_collision: bool = False,
):
    """Build the package graph, or return None with an error printed.

    An address collision is printed as an error and gives None, unless
    *raise_on_collision* is set, in which case it propagates so a JSON
    caller can report it as a finding instead.
    """
    root, binding = _require_root(hint)
    if root is None:
        return None
    kit, extract_symbols = _get_binding_kit(
        binding.get("language") if binding else None
    )
    try:
        return build_package(
            root, extract_symbols, call_extractor=kit.extract_calls,
            split_imports=kit.split_imports)
    except AddressCollisionError as exc:
        if raise_on_collision:
            raise
        print(f"ERROR  <names>  {exc}", file=sys.stderr)
        return None


# ── Query commands ────────────────────────────────────────────
#
# Each reads the package graph itself. A list answer is one entry for a
# node: in ``text`` (the default) a line of three columns, the node's
# sigil, its address and where it is; in ``json`` an array of node
# summaries as ``notlob graph`` prints them at ``outline`` (see
# :func:`notlob.graph.node_summary`).

#: The edge kinds a graph holds, for ``query children``.
QUERY_EDGE_KINDS = tuple(k.name for k in EdgeKind)

#: The kinds of node ``outline`` shows, for ``query search``.
QUERY_NODE_KINDS = tuple(
    k.name for k in NodeKind if not KINDS[k].hidden_at_outline)

#: The formats a query answers in.
QUERY_FORMATS = ("text", "json")


def _where(source: Node, line: int | None = None) -> str:
    """``file:line`` for an entry of an answer: the file of *source* and
    *line*, or where *source* starts if there is no line. Blank for a node
    with no file (an external one)."""
    if source.file is None:
        return ""
    line = source.start_line if line is None else line
    return source.file if line is None else f"{source.file}:{line}"


def _columns(rows: list[tuple[str, str, str]]) -> str:
    """*rows*, each a (sigil, address, where), as lines: each column as
    wide as its longest entry and two spaces from the next, trailing
    spaces stripped. A column with nothing in it is left out."""
    widths = [max(map(len, column)) for column in zip(*rows)]
    return "".join(
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths)
                  if width).rstrip() + "\n"
        for row in rows)


def _query_graph(fmt: str):
    """The package graph for a query that answers in *fmt*, or ``None``
    with the reason printed."""
    if fmt not in QUERY_FORMATS:
        print(f"ERROR  <query>  unknown format {fmt!r}: choose text or "
              f"json", file=sys.stderr)
        return None
    return _require_graph()


def _answer(
    graph: NameGraph, address: str | None, entries: list[tuple[Node, str]],
    fmt: str,
) -> int:
    """Print *entries*, each a node and where it is, as *fmt* says.

    ``json`` is the array of the nodes, ``text`` a line a node (see
    :func:`_columns`); an empty list is an empty answer. When *address*,
    what the query was asked about, is not a node of the graph, the
    answer is an error on stderr and exit 1, with ``null`` on stdout in
    ``json``."""
    if address is not None and graph.node(address) is None:
        if fmt == "json":
            print("null")
        print(f"ERROR  <query>  no node at address {address!r}",
              file=sys.stderr)
        return 1
    if fmt == "json":
        print(json.dumps([node_summary(n) for n, _ in entries],
                         indent=2, ensure_ascii=False))
        return 0
    print(_columns([(sigil_of(n), n.address, where)
                    for n, where in entries]), end="")
    return 0


def cmd_query_children(
    address: str, kind_str: str = "CONTAINS", fmt: str = "text",
) -> int:
    """Print the targets of the edges of kind *kind_str* from *address*:
    what *address* contains (the default, a section's paragraphs and code
    blocks included), or what it imports, uses or refers to. Each is
    given where it starts."""
    if kind_str not in QUERY_EDGE_KINDS:
        print(f"ERROR  <query>  unknown edge kind {kind_str!r}: choose "
              f"{', '.join(QUERY_EDGE_KINDS)}", file=sys.stderr)
        return 1
    graph = _query_graph(fmt)
    if graph is None:
        return 1
    return _answer(graph, address, [
        (n, _where(n)) for n in graph.children(address, EdgeKind[kind_str])
    ], fmt)


def cmd_query_resolve(label: str, context: str | None = None) -> int:
    """Resolve *label* (with optional *context* module address).

    Exits 0 and prints the node JSON when the reference resolves;
    exits 1 and prints ``null`` when it does not. Deprecated: it says so
    on stderr, and will be removed in favour of ``query search``.
    """
    print("DEPRECATED  <query>  query resolve will be removed; "
          "use query search", file=sys.stderr)
    graph = _require_graph()
    if graph is None:
        return 1
    node = graph.resolve(label, context)
    print(json.dumps(
        node_summary(node) if node else None, indent=2, ensure_ascii=False))
    return 0 if node else 1


def cmd_query_search(
    pattern: str,
    kind_str: str | None = None,
    fmt: str = "text",
) -> int:
    """Print the nodes ``outline`` shows whose label matches *pattern*
    (fnmatch-style), each where it starts.

    Bare words (no ``*`` or ``?`` wildcards) are automatically wrapped
    as ``*pattern*`` for convenient substring matching.
    """
    if kind_str is not None and kind_str not in QUERY_NODE_KINDS:
        print(f"ERROR  <query>  unknown kind {kind_str!r}: choose "
              f"{', '.join(QUERY_NODE_KINDS)}", file=sys.stderr)
        return 1
    graph = _query_graph(fmt)
    if graph is None:
        return 1
    if "*" not in pattern and "?" not in pattern:
        pattern = f"*{pattern}*"
    kind = NodeKind[kind_str] if kind_str else None
    return _answer(graph, None, [
        (n, _where(n)) for n in graph.search(pattern, kind)
        if not KINDS[n.kind].hidden_at_outline
    ], fmt)


# The queries that follow an edge give each node where the edge is written:
# the file of the edge's source and the line of the edge, or where its
# source starts if it has no line.

def cmd_query_imports(address: str, fmt: str = "text") -> int:
    """Print the modules the module at *address* imports, each at the
    line of the listing that makes it."""
    graph = _query_graph(fmt)
    if graph is None:
        return 1
    return _answer(graph, address, [
        (graph.node(e.target), _where(graph.node(e.source), e.start_line))
        for e in graph.import_edges(address)
    ], fmt)


def cmd_query_imported_by(address: str, fmt: str = "text") -> int:
    """Print the modules that import the module at *address*, each at the
    line of its listing of it."""
    graph = _query_graph(fmt)
    if graph is None:
        return 1
    return _answer(graph, address, [
        (graph.node(graph.module_of(e.source)),
         _where(graph.node(e.source), e.start_line))
        for e in graph.importer_edges(address)
    ], fmt)


def cmd_query_callers(address: str, fmt: str = "text") -> int:
    """Print the nodes with a USES edge pointing at *address*, each at the
    line where it uses it."""
    graph = _query_graph(fmt)
    if graph is None:
        return 1
    return _answer(graph, address, [
        (source, _where(source, e.start_line))
        for e in graph.edges(EdgeKind.USES) if e.target == address
        if (source := graph.node(e.source)) is not None
    ], fmt)


def cmd_query_callees(address: str, fmt: str = "text") -> int:
    """Print the nodes that *address* has a USES edge to, each at the line
    where *address* uses it."""
    graph = _query_graph(fmt)
    if graph is None:
        return 1
    source = graph.node(address)
    return _answer(graph, address, [
        (target, _where(source, e.start_line))
        for e in graph.edges(EdgeKind.USES) if e.source == address
        if (target := graph.node(e.target)) is not None
    ], fmt)


def cmd_query_cites(address: str, fmt: str = "text") -> int:
    """Print the nodes that *address* cites with a prose ``#Label``: those
    in its own paragraphs (a section's citations are its paragraphs'),
    each at the line of the citation."""
    graph = _query_graph(fmt)
    if graph is None:
        return 1
    return _answer(graph, address, [
        (graph.node(e.target), _where(graph.node(e.source), e.start_line))
        for e in cites_edges(graph, address)
    ], fmt)


def cmd_query_cited_by(address: str, fmt: str = "text") -> int:
    """Print the nodes whose prose cites *address*, each once, at the line
    of its first citation: a paragraph that does is given as the section
    that holds it."""
    graph = _query_graph(fmt)
    if graph is None:
        return 1
    return _answer(graph, address, [
        (graph.node(e.source), _where(graph.node(e.source), e.start_line))
        for e in cited_by_edges(graph, address)
    ], fmt)


# ── Check command ─────────────────────────────────────────────

def cmd_check(
    only: set[str] | None = None,
    verbose: bool = False,
    fmt: str = "text",
) -> int:
    """Run semantic consistency checks on the project name graph.

    *fmt* is ``"text"`` (the default) or ``"json"``, the document
    described by ``schema/check_result.json``.

    Returns 1 if any error-severity findings exist, 0 otherwise.
    """
    from notlob.check import coverage_summary, has_errors, run_checks

    json_mode = fmt == "json"
    try:
        graph = _require_graph(raise_on_collision=json_mode)
    except AddressCollisionError as exc:
        # No graph, so no check ran: report the collision as the one
        # finding (as `test --format json` does) so stdout is still a
        # document.
        print(json.dumps({
            "version": _CHECK_JSON_VERSION,
            "findings": [_collision_finding(exc)],
            "counts": {},
        }, indent=2, ensure_ascii=False))
        return 1
    if graph is None:
        return 1
    if verbose and not json_mode:
        print(coverage_summary(graph))
    findings, counts = run_checks(graph, enabled=only)

    if json_mode:
        output = {
            "version": _CHECK_JSON_VERSION,
            "findings": [_finding_dict(f) for f in findings],
            "counts": counts,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        if verbose:
            for name, n in counts.items():
                print(f"CHECK  [{name}]  {n} finding(s)")
        for f in findings:
            prefix = "ERROR" if f.severity == "error" else "CHECK"
            addrs = ", ".join(f.addresses)
            print(f"{prefix}  [{f.check}]  {f.message}")
            print(f"       {addrs}")
        if findings:
            print(f"\n{len(findings)} finding(s)")
        elif not verbose:
            print("CHECK  no findings")
    return 1 if has_errors(findings) else 0


def cmd_weave(
    path:     Path | None = None,
    language: str  | None = None,
) -> int:
    """Render *path* (or all project modules) as Markdown to stdout.

    When *path* is omitted, discovers the project from CWD and renders
    every module in sorted path order, separated by ``---`` dividers.
    Pass a specific *.lob* path to render a single module.

    The language tag for fenced code blocks is resolved in order:
    1. The *language* argument if supplied (from ``--language`` flag).
    2. The ``~language`` declaration in the nearest ``binding.lob``.
    3. The default ``"python"``.
    """
    from notlob.weave import weave_markdown   # lazy — avoids circular dep

    if path is not None:
        try:
            module = from_tree(parse_file(path))
        except Exception as exc:
            print(f"ERROR  <parse>  {exc}", file=sys.stderr)
            return 1
        if language is None:
            binding  = _find_binding(path)
            language = binding.get("language", "python")
        print(weave_markdown(module, language), end="")
        return 0

    root, binding = _require_root()
    if root is None:
        return 1
    if language is None:
        language = (binding or {}).get("language", "python")

    first = True
    for lob_path in sorted(root.glob("**/*.lob")):
        if lob_path.name == "binding.lob":
            continue
        try:
            module = from_tree(parse_file(lob_path))
        except Exception:
            continue
        if not first:
            print("\n---\n")
        print(weave_markdown(module, language), end="")
        first = False
    return 0


def _content_text(graph: NameGraph, root: Path, address: str) -> str:
    """The source of the node at *address*: a header line, the address and
    the span (``address  file:first-last``), then the node's own lines
    from its file under *root*, as written.

    Raises ``ValueError`` with the reason when there is no such node, or
    it has no lines in a ``.lob`` file (an external file), or its file
    cannot be read."""
    node = graph.node(address)
    if node is None:
        raise ValueError(f"no node at address {address!r}")
    if node.file is None or node.start_line is None or node.end_line is None:
        raise ValueError(
            f"{address!r} has no lines in a .lob file to show")
    try:
        lines = (root / node.file).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"cannot read {node.file}: {exc}") from exc
    body = "\n".join(lines[node.start_line - 1:node.end_line])
    return (f"{address}  {node.file}:{node.start_line}-{node.end_line}\n"
            f"{body}\n")


def cmd_query_content(
    address: str, depth: int | None = None, fmt: str = "text",
) -> int:
    """Print the node at *address* as it is written.

    ``text`` (the default) is a header line, the address and the span, and
    then the node's own lines from its file, as written (see
    :func:`_content_text`). ``json`` is the subtree, nested and narrow (see
    :func:`notlob.graph.content_tree`), with ``null`` and exit code 1 when
    the address does not resolve. *depth* counts ``CONTAINS`` steps from
    the node (``0`` the node alone; by default there is no limit) and is
    for ``json`` only: with ``text`` it is an error.
    """
    if fmt not in ("text", "json"):
        print(f"ERROR  <query>  unknown format {fmt!r}: choose text or "
              f"json", file=sys.stderr)
        return 1
    if depth is not None and fmt != "json":
        print("ERROR  <query>  depth is for --format json only",
              file=sys.stderr)
        return 1
    if depth is not None and depth < 0:
        print("ERROR  <query>  depth must be 0 or more", file=sys.stderr)
        return 1
    project, _binding = _require_root()
    if project is None:
        return 1
    graph = _require_graph()
    if graph is None:
        return 1
    if fmt == "json":
        document = content_tree(graph, address, depth)
        print(json.dumps(document, indent=2, ensure_ascii=False))
        return 0 if document else 1
    try:
        text = _content_text(graph, project, address)
    except ValueError as exc:
        print(f"ERROR  <query>  {exc}", file=sys.stderr)
        return 1
    print(text, end="")
    return 0


# ── Docs / Init / New ─────────────────────────────────────────

def cmd_docs(
    output_dir: Path | None = None,
    full:       bool        = False,
) -> int:
    """Write the notlob language reference to *output_dir*.

    Defaults to ``notlob-docs/`` in the current directory.  The
    directory is created if it does not exist.  Prints
    ``DOCS   <path>`` for each file written.

    ``LANGUAGE.md`` refers readers to each binding's ``BINDING.md``, so
    the doc of every registered binding (built-in or third-party; see
    :func:`_binding_docs`) is written too, as ``BINDING-<language>.md``.
    The JSON Schemas for the stable-tier structured output go to
    ``schema/``, and ``grammar.lark``, the formal syntax reference, is
    written with a note that its rule and terminal names may change.

    Pass *full=True* (``--full``) to also write ``DESIGN.md`` —
    the internal architecture and design rationale.
    """
    out_dir = output_dir or Path("notlob-docs")
    out_dir.mkdir(parents=True, exist_ok=True)

    files: list[tuple[str, str]] = []   # (relative path, text)

    def add(name: str, source: Path, header: str = "") -> None:
        files.append((name, header + source.read_text(encoding="utf-8")))

    add("LANGUAGE.md", _DOCS_DIR / "LANGUAGE.md")
    for language, path in _binding_docs():
        add(f"BINDING-{language}.md", path)
    for schema in sorted([*_SCHEMA_DIR.glob("*.json"),
                          *_SCHEMA_DIR.glob("*.ttl")]):
        add(f"schema/{schema.name}", schema)
    add("grammar.lark", _GRAMMAR_PATH, _GRAMMAR_NOTE)
    if full:
        for name in ("DESIGN.md", "USER-AGENTS.md"):
            add(name, _DOCS_DIR / name)

    for name, text in files:
        out_path = out_dir / name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"DOCS   {out_path}")

    return 0


def cmd_init(
    language:   str  = "python",
    bare:       bool = False,
    agents_only: bool = False,
) -> int:
    """Initialise a new notlob project in the current directory.

    Creates ``binding.lob``, a starter ``.lob`` module, and (unless
    *bare* is True) ``AGENTS.md`` plus the language reference in
    ``notlob-docs/``.

    Pass *agents_only* to write only ``AGENTS.md`` and ``notlob-docs/``
    into an existing project.  Requires ``binding.lob`` to already exist.
    Fails if ``binding.lob`` is absent (use plain ``init`` for new projects).
    """
    cwd = Path.cwd()
    binding_path = cwd / "binding.lob"

    if agents_only:
        if not binding_path.exists():
            print(
                "ERROR  <init>  binding.lob not found — "
                "run notlob init (without --agents) to start a new project",
                file=sys.stderr,
            )
            return 1
        project_title = _address_to_title(cwd.name)
        agents_path = cwd / "AGENTS.md"
        agents_path.write_text(
            _render_agents(project_title), encoding="utf-8"
        )
        print("INIT   AGENTS.md")
        cmd_docs()
        agents_content = _render_agents(project_title)
        bar = "-" * 52
        print()
        print(bar)
        print(agents_content.rstrip())
        print(bar)
        return 0

    if binding_path.exists():
        print(
            "ERROR  <init>  binding.lob already exists — "
            "already a notlob project",
            file=sys.stderr,
        )
        return 1

    # Derive project and starter-module names from the directory name.
    dir_name      = cwd.name
    project_title = _address_to_title(dir_name)
    starter_slug  = dir_name.replace("-", "_").replace(" ", "_").lower()
    starter_name  = f"{starter_slug}.lob"
    module_title  = _address_to_title(starter_slug)

    # Write binding.lob
    binding_path.write_text(
        _render_binding(project_title, language), encoding="utf-8"
    )
    print("INIT   binding.lob")

    # Write starter module
    starter_path = cwd / starter_name
    starter_path.write_text(
        _render_starter(module_title), encoding="utf-8"
    )
    print(f"INIT   {starter_name}")

    # Write language toolchain scaffolding (e.g. package.json + tsconfig
    # for TypeScript).  Essential, so written even with --bare.  Never
    # clobber a file the user already has — e.g. adding notlob to an
    # existing Node project.
    for fname, content in _scaffold_files(language, starter_slug):
        target = cwd / fname
        if target.exists():
            print(f"INIT   {fname} exists — leaving as-is")
        else:
            target.write_text(content, encoding="utf-8")
            print(f"INIT   {fname}")

    if not bare:
        # Write AGENTS.md
        agents_path = cwd / "AGENTS.md"
        agents_path.write_text(
            _render_agents(project_title), encoding="utf-8"
        )
        print("INIT   AGENTS.md")

        # Write language reference
        cmd_docs()

        # Print AGENTS.md inline so agents running mid-session get
        # the instructions immediately — AGENTS.md is only auto-loaded
        # by Claude Code at session start, not when first created.
        agents_content = _render_agents(project_title)
        bar = "-" * 52
        print()
        print(bar)
        print(agents_content.rstrip())
        print(bar)

    hint = _scaffold_hint(language)
    if hint:
        print()
        print(hint)

    return 0


def cmd_new(name: str) -> int:
    """Create a new ``.lob`` module named *name*.

    *name* is a module address (e.g. ``roman/numerals``) relative to
    the project root.  The title is derived from the address.  Fails
    if the file already exists or if no project root is found.
    """
    root, _ = _require_root()
    if root is None:
        return 1

    name     = name.removesuffix(".lob")
    lob_path = root / f"{name}.lob"

    if lob_path.exists():
        print(
            f"ERROR  <new>  {lob_path.relative_to(root)} already exists",
            file=sys.stderr,
        )
        return 1

    lob_path.parent.mkdir(parents=True, exist_ok=True)
    title = _address_to_title(name)
    lob_path.write_text(
        _render_starter(title), encoding="utf-8"
    )
    print(f"NEW    {lob_path.relative_to(root)}")
    return 0
