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

import json
import os
import subprocess
import sys
import tempfile
import textwrap
from functools import lru_cache
from importlib.metadata import entry_points
from pathlib import Path

from notlob import (
    build, enrich, from_tree, parse_file, validate_refs,
    Edge, EdgeKind, NodeKind,
)
from notlob.bindings import (
    ClaimResult, LintResult, LintToolUnavailable, Status,
)
from notlob.bindings.python.loader import ModuleCache
from notlob.graph import module_address
from notlob.model import BindingSection, Claim, Subheading
from notlob.project import (
    address_from_path,
    build_package,
    find_project_root, module_lob_refs, resolve_module_path,
)


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

def _result_dict(r: ClaimResult) -> dict:
    """Convert a ClaimResult to a JSON-serialisable dict."""
    d: dict = {
        "address": r.address,
        "line": r.line,
        "status": r.status.name,
    }
    if r.file_path:
        d["file"] = Path(r.file_path).name
    if r.source_line:
        d["source_line"] = r.source_line
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


def _print_result(r: ClaimResult) -> None:
    tag = r.status.name
    loc = ""
    if r.file_path and r.source_line:
        rel = Path(r.file_path).name
        loc = f"{rel}:{r.source_line}  "
    print(f"{tag:5}  {loc}{r.address}  {r.line}")
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


# ── Reference-graph builder ───────────────────────────────────

def _build_ref_graph(module, root, extract_symbols):
    """Build a NameGraph sufficient for validate_refs.

    Builds the structural graph for *module*, enriches it with
    symbols, then merges in a MODULE node for each directly imported
    module and adds the corresponding IMPORTS edge.  Only direct
    imports are added; transitive imports are not needed because
    validate_refs only resolves one hop via step 3.

    *extract_symbols* is the language-specific extractor from the
    binding kit; it is passed explicitly so the ref graph uses the
    same language as the active kit.

    Import errors (missing files) are silently skipped — they will
    surface as claim execution errors later.
    """
    graph    = build(module)
    enrich(graph, module, extract_symbols)
    mod_addr = module_address(module.title)

    if root is not None:
        for dep_addr in module_lob_refs(module):
            try:
                dep_path = resolve_module_path(dep_addr, root)
                dep_mod  = from_tree(parse_file(dep_path))
                graph.merge(build(dep_mod))
                graph.add_edge(Edge(
                    source=mod_addr,
                    target=dep_addr,
                    kind=EdgeKind.IMPORTS,
                ))
            except Exception:
                pass  # missing dep — caught later as a claim error

    return graph


# ── Commands ──────────────────────────────────────────────────

def _collect_run_claims(module) -> list[Claim]:
    """Return all ~run claims (bare, ``on-load``, or ``on-invocation``)
    from the module body and subheadings, in document order.
    """
    claims = []
    for item in module.body:
        if isinstance(item, Claim) and item.sigil.startswith("~run"):
            claims.append(item)
        elif isinstance(item, Subheading):
            for sub_item in item.body:
                if (isinstance(sub_item, Claim)
                        and sub_item.sigil.startswith("~run")):
                    claims.append(sub_item)
    return claims


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
    path: Path,
    keep_dir: Path | None = None,
    args: list[str] | None = None,
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
        source = build_haskell(module, path)
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

    if language == "haskell":
        keep_dir = _resolve_keep_dir(keep_generated_src, binding, root)
        return _cmd_run_haskell(module, path, keep_dir=keep_dir, args=args)

    root = find_project_root(path)

    addr_err = _check_address(module, path, root)
    if addr_err:
        print(f"ERROR  <address>  {addr_err}", file=sys.stderr)
        return 1

    py_kit, _ = _get_binding_kit(language)
    cache = ModuleCache(root) if root else None
    ns: dict = {"__file__": str(path.resolve())}
    old_argv = sys.argv
    sys.argv = [str(path)] + list(args or [])
    try:
        if cache is not None:
            for dep_addr in module_lob_refs(module):
                ns.update(cache.load(dep_addr))
        exec(py_kit.assemble(module), ns)
    except Exception as exc:
        sys.argv = old_argv
        print(f"ERROR  <assembly>  {exc}", file=sys.stderr)
        return 1

    try:
        for claim in _collect_run_claims(module):
            try:
                exec(textwrap.dedent("\n".join(claim.lines)), ns)
            except Exception as exc:
                print(f"ERROR  <run>  {exc}", file=sys.stderr)
                return 1
    finally:
        sys.argv = old_argv

    return 0


def _test_module(
    path:               Path,
    root:               Path | None,
    binding:            dict,
    keep_generated_src: str | None      = None,
    only:               set[str] | None = None,
    json_out:           list | None     = None,
) -> tuple[int, int, int]:
    """Test one module; print per-claim output (or collect into *json_out*).

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
    cache    = ModuleCache(root) if (root and language != "haskell") else None
    keep_dir = _resolve_keep_dir(keep_generated_src, binding, root)

    run_lint     = only is None or "lint"     in only
    run_examples = only is None or "examples" in only
    run_props    = only is None or "props"    in only
    run_tests_   = only is None or "tests"    in only

    doc_errors: list[str] = []

    addr_err = _check_address(module, path, root)
    if addr_err:
        doc_errors.append(f"ERROR  <address>  {addr_err}")

    for ref_err in validate_refs(
        _build_ref_graph(module, root, extract_symbols), module
    ):
        doc_errors.append(f"ERROR  <refs>  {ref_err}")

    if doc_errors:
        for msg in doc_errors:
            print(msg, file=sys.stderr)
        return 0, 1, 0

    # ── Lint ──────────────────────────────────────────────────
    lint_results: list[LintResult] = []
    if run_lint and kit.lint is not None:
        try:
            lint_results = kit.lint(module, root=root)
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
    results = []
    if run_examples:
        results += kit.run_examples(
            module, file_path=path, cache=cache, keep_dir=keep_dir,
        )
    if run_props:
        results += kit.run_properties(
            module, binding=binding, file_path=path,
            cache=cache, keep_dir=keep_dir,
        )
    if run_tests_:
        results += kit.run_tests(
            module, binding=binding, file_path=path,
            cache=cache, keep_dir=keep_dir,
        )

    non_skip = [r for r in results if r.status != Status.SKIP]
    if json_out is not None:
        for r in results:
            json_out.append(_result_dict(r))
        for r in lint_results:
            json_out.append(_lint_dict(r))
    else:
        for r in results:
            _print_result(r)

    n_fail = sum(1 for r in non_skip if r.status != Status.PASS)
    n_pass = len(non_skip) - n_fail
    n_lint = len(lint_results)
    return n_pass, n_fail, n_lint


def cmd_test(
    path:               Path | None      = None,
    keep_generated_src: str | None       = None,
    only:               set[str] | None  = None,
    json_mode:          bool             = False,
) -> int:
    """Run claims in *path* (or all project modules) and return an exit code.

    When *path* is omitted, discovers the project from CWD and tests
    every module.  Pass a specific *.lob* path to test a single module.

    *only* restricts which check types run.  When *None* all checks run.
    Valid values in the set: ``"lint"``, ``"examples"``, ``"props"``,
    ``"tests"``.  Lint failures produce exit code 1 just like claim
    failures.
    """
    json_out: list | None = [] if json_mode else None

    if path is not None:
        root    = find_project_root(path)
        binding = _find_binding(path)
        n_pass, n_fail, n_lint = _test_module(
            path, root, binding, keep_generated_src, only,
            json_out=json_out,
        )
    else:
        root, binding = _require_root()
        if root is None:
            return 1
        n_pass = n_fail = n_lint = 0
        for lob_path in sorted(root.glob("**/*.lob")):
            if lob_path.name == "binding.lob":
                continue
            p, f, lint = _test_module(
                lob_path, root, binding, keep_generated_src, only,
                json_out=json_out,
            )
            n_pass += p
            n_fail += f
            n_lint += lint

    check_errors = False
    check_findings: list[dict] = []
    if path is None:
        if json_mode:
            from notlob.check import has_errors, run_checks
            _kit, _extr = _get_binding_kit(
                binding.get("language") if binding else None,
            )
            graph = build_package(
                root, _extr, call_extractor=_kit.extract_calls,
            )
            findings, _ = run_checks(graph)
            check_findings = [
                {"check": f.check, "message": f.message,
                 "addresses": list(f.addresses),
                 "severity": f.severity}
                for f in findings
            ]
            check_errors = has_errors(findings)
        else:
            check_errors = _run_check_advisory(root, binding)

    if json_mode:
        output = {
            "passed": n_pass,
            "failed": n_fail,
            "lint": n_lint,
            "results": json_out,
        }
        if check_findings:
            output["check_findings"] = check_findings
        print(json.dumps(output, indent=2))
    else:
        parts = [f"{n_pass} passed"]
        if n_fail:
            parts.append(f"{n_fail} failed")
        if n_lint:
            parts.append(f"{n_lint} lint")
        print(f"\n{', '.join(parts)}")

    return 1 if (n_fail or n_lint or check_errors) else 0


def _run_check_advisory(root: Path, binding: dict) -> bool:
    """Run semantic checks and print findings.

    Returns True if any error-severity findings were found.
    """
    from notlob.check import has_errors, run_checks

    kit, extract_symbols = _get_binding_kit(
        binding.get("language") if binding else None,
    )
    graph = build_package(root, extract_symbols, call_extractor=kit.extract_calls)
    findings, _ = run_checks(graph)
    for f in findings:
        prefix = "ERROR" if f.severity == "error" else "CHECK"
        addrs = ", ".join(f.addresses)
        print(f"{prefix}  [{f.check}]  {f.message}")
        print(f"       {addrs}")
    return has_errors(findings)


# ── Init / docs / new helpers ────────────────────────────────

_DOCS_DIR = Path(__file__).parent / "docs"


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
    return json.dumps(data, indent=2) + "\n"


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
    return json.dumps(data, indent=2) + "\n"


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


def _build_one(path: Path, kit, output_dir: Path) -> Path | None:
    """Build a single module and write the artifact to *output_dir*.

    Returns the output path on success, None on error.
    Prints ``BUILD  <out_path>`` on success, or an ERROR line on failure.
    """
    try:
        module = from_tree(parse_file(path))
    except Exception as exc:
        print(f"ERROR  <parse>  {exc}", file=sys.stderr)
        return None

    try:
        source = kit.build(module, path)
    except Exception as exc:
        print(f"ERROR  <build>  {exc}", file=sys.stderr)
        return None
    if not source:
        return None  # prose-only module — skip silently, not an error

    mod_addr = module_address(module.title)
    header   = _build_header(kit.comment_prefix, mod_addr, path.name)
    slug     = mod_addr.replace("/", "_")
    out_path = output_dir / f"{slug}.{kit.extension}"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + "\n" + source, encoding="utf-8")
    print(f"BUILD  {out_path}")
    return out_path


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

    The hook receives a JSON manifest written to a temporary file whose
    path is passed as its first argument.  The manifest contains:

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
        json.dump(manifest, f, indent=2)
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
        if not skip_tests:
            print("TEST   (running claims before build)")
            rc = cmd_test(path)
            if rc != 0:
                print(
                    "ERROR  <build>  claims failed — build aborted "
                    "(use --skip-tests to override)",
                    file=sys.stderr,
                )
                return 1
        out_path = _build_one(path, kit, output_dir)
        if out_path is None:
            return 1
        try:
            module     = from_tree(parse_file(path))
            is_entry   = bool(_collect_run_claims(module))
        except Exception:
            is_entry   = False
        entry_points = [out_path] if is_entry else []
        _run_build_hook(binding, root, [out_path], output_dir,
                        entry_points=entry_points)
        return 0

    root, binding = _require_root()
    if root is None:
        return 1
    language = binding.get("language")
    kit, _   = _get_binding_kit(language)
    if kit.build is None:
        print(
            f"ERROR  <build>  no build support for language {language!r}",
            file=sys.stderr,
        )
        return 1

    if not skip_tests:
        print("TEST   (running claims before build)")
        rc = 0
        for lob_path in sorted(root.glob("**/*.lob")):
            if lob_path.name == "binding.lob":
                continue
            if cmd_test(lob_path) != 0:
                rc = 1
        if rc != 0:
            print(
                "ERROR  <build>  claims failed — build aborted "
                "(use --skip-tests to override)",
                file=sys.stderr,
            )
            return 1

    if _run_check_advisory(root, binding):
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
        out_path = _build_one(lob_path, kit, output_dir)
        if out_path is not None:
            artifacts.append(out_path)
            try:
                module = from_tree(parse_file(lob_path))
                if _collect_run_claims(module):
                    entry_points.append(out_path)
            except Exception:
                pass
        else:
            rc = 1
    _run_build_hook(binding, root, artifacts, output_dir,
                    entry_points=entry_points)
    return rc


# ── Graph export ──────────────────────────────────────────────

def cmd_graph(
    path:            Path | None = None,
    include_content: bool        = False,
    fmt:             str         = "json",
) -> int:
    """Print the package name-graph to stdout.

    When *path* is omitted, discovers the project from CWD and exports
    the full package graph.  Pass a specific *.lob* path to export that
    file's module graph (or its project graph when it is inside a
    project).

    The language binding (from ``binding.lob``) controls symbol
    extraction.  Pass *include_content=True* to attach prose/code to
    every node.  *fmt* selects the output format: ``"json"`` (default)
    or ``"turtle"`` (RDF Turtle).
    """
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
        graph = build_package(root, extract_symbols, call_extractor=kit.extract_calls)
    else:
        # standalone file — only reachable via an explicit path arg
        try:
            module = from_tree(parse_file(path))
        except Exception as exc:
            print(f"ERROR  <parse>  {exc}", file=sys.stderr)
            return 1
        graph = build(module)
        enrich(graph, module, extract_symbols)

    if fmt == "turtle":
        sys.stdout.buffer.write(
            graph.to_turtle(include_content=include_content)
            .encode("utf-8")
        )
        sys.stdout.buffer.write(b"\n")
    else:
        print(graph.to_json(include_content=include_content))
    return 0


# ── Query helpers ─────────────────────────────────────────────

def _node_dict(node, include_content: bool = False) -> dict:
    d: dict = {
        "address": node.address,
        "label":   node.label,
        "kind":    node.kind.name,
    }
    if include_content and node.content is not None:
        d["content"] = node.content
    if node.start_line is not None:
        d["start_line"] = node.start_line
    return d


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


def _require_graph(hint: Path | None = None):
    """Build the package graph, or return None with an error printed."""
    root, binding = _require_root(hint)
    if root is None:
        return None
    kit, extract_symbols = _get_binding_kit(
        binding.get("language") if binding else None
    )
    return build_package(root, extract_symbols, call_extractor=kit.extract_calls)


# ── Query commands ────────────────────────────────────────────

def cmd_query_children(address: str, kind_str: str = "CONTAINS") -> int:
    """Print direct children of *address* as a JSON array."""
    graph = _require_graph()
    if graph is None:
        return 1
    kind    = EdgeKind[kind_str]
    results = list(graph.children(address, kind))
    print(json.dumps([_node_dict(n) for n in results], indent=2))
    return 0


def cmd_query_resolve(label: str, context: str | None = None) -> int:
    """Resolve *label* (with optional *context* module address).

    Exits 0 and prints the node JSON when the reference resolves;
    exits 1 and prints ``null`` when it does not.
    """
    graph = _require_graph()
    if graph is None:
        return 1
    node = graph.resolve(label, context)
    print(json.dumps(_node_dict(node) if node else None, indent=2))
    return 0 if node else 1


def cmd_query_search(
    pattern: str,
    kind_str: str | None = None,
) -> int:
    """Print nodes whose label matches *pattern* (fnmatch-style).

    Bare words (no ``*`` or ``?`` wildcards) are automatically wrapped
    as ``*pattern*`` for convenient substring matching.
    """
    graph = _require_graph()
    if graph is None:
        return 1
    if "*" not in pattern and "?" not in pattern:
        pattern = f"*{pattern}*"
    kind    = NodeKind[kind_str] if kind_str else None
    results = list(graph.search(pattern, kind))
    print(json.dumps([_node_dict(n) for n in results], indent=2))
    return 0


def cmd_query_imports(address: str) -> int:
    """Print modules imported by *address* as a JSON array."""
    graph = _require_graph()
    if graph is None:
        return 1
    results = list(graph.children(address, EdgeKind.IMPORTS))
    print(json.dumps([_node_dict(n) for n in results], indent=2))
    return 0


def cmd_query_imported_by(address: str) -> int:
    """Print modules that import *address* as a JSON array."""
    graph = _require_graph()
    if graph is None:
        return 1
    results = list(graph.parents(address, EdgeKind.IMPORTS))
    print(json.dumps([_node_dict(n) for n in results], indent=2))
    return 0


def cmd_query_callers(address: str) -> int:
    """Print symbols with a USES edge pointing at *address*."""
    graph = _require_graph()
    if graph is None:
        return 1
    results = list(graph.parents(address, EdgeKind.USES))
    print(json.dumps([_node_dict(n) for n in results], indent=2))
    return 0


def cmd_query_callees(address: str) -> int:
    """Print symbols that *address* has a USES edge to."""
    graph = _require_graph()
    if graph is None:
        return 1
    results = list(graph.children(address, EdgeKind.USES))
    print(json.dumps([_node_dict(n) for n in results], indent=2))
    return 0


def cmd_query_references(address: str) -> int:
    """Print nodes that *address* mentions via prose #Label references."""
    graph = _require_graph()
    if graph is None:
        return 1
    results = list(graph.children(address, EdgeKind.REFERENCES))
    print(json.dumps([_node_dict(n) for n in results], indent=2))
    return 0


def cmd_query_referenced_by(address: str) -> int:
    """Print nodes whose prose contains a #Label reference to *address*."""
    graph = _require_graph()
    if graph is None:
        return 1
    results = list(graph.parents(address, EdgeKind.REFERENCES))
    print(json.dumps([_node_dict(n) for n in results], indent=2))
    return 0


# ── Check command ─────────────────────────────────────────────

def cmd_check(
    only: set[str] | None = None,
    verbose: bool = False,
    json_mode: bool = False,
) -> int:
    """Run semantic consistency checks on the project name graph.

    Returns 1 if any error-severity findings exist, 0 otherwise.
    """
    from notlob.check import coverage_summary, has_errors, run_checks

    graph = _require_graph()
    if graph is None:
        return 1
    if verbose and not json_mode:
        print(coverage_summary(graph))
    findings, counts = run_checks(graph, enabled=only)

    if json_mode:
        output = {
            "findings": [
                {"check": f.check, "message": f.message,
                 "addresses": list(f.addresses),
                 "severity": f.severity}
                for f in findings
            ],
            "counts": counts,
        }
        print(json.dumps(output, indent=2))
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


def cmd_query_content(address: str) -> int:
    """Print the node at *address* with its source content as JSON.

    Returns exit code 0 when the address resolves, 1 (with ``null``)
    when it does not.  This is the primary F3-style lookup: given a
    known address, retrieve its prose and/or code.
    """
    graph = _require_graph()
    if graph is None:
        return 1
    node = graph.node(address)
    print(json.dumps(
        _node_dict(node, include_content=True) if node else None,
        indent=2,
    ))
    return 0 if node else 1


# ── Docs / Init / New ─────────────────────────────────────────

def cmd_docs(
    output_dir: Path | None = None,
    full:       bool        = False,
) -> int:
    """Write the notlob language reference to *output_dir*.

    Defaults to ``notlob-docs/`` in the current directory.  The
    directory is created if it does not exist.  Prints
    ``DOCS   <path>`` for each file written.

    Pass *full=True* (``--full``) to also write ``DESIGN.md`` —
    the internal architecture and design rationale.
    """
    out_dir = output_dir or Path("notlob-docs")
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in (
        ["LANGUAGE.md", "DESIGN.md", "USER-AGENTS.md"] if full
        else ["LANGUAGE.md"]
    ):
        content  = (_DOCS_DIR / name).read_text(encoding="utf-8")
        out_path = out_dir / name
        out_path.write_text(content, encoding="utf-8")
        print(f"DOCS   {out_path}")

    return 0


def cmd_init(
    language: str = "python",
    bare:     bool = False,
) -> int:
    """Initialise a new notlob project in the current directory.

    Creates ``binding.lob``, a starter ``.lob`` module, and (unless
    *bare* is True) ``AGENTS.md`` plus the language reference in
    ``notlob-docs/``.

    Fails if ``binding.lob`` already exists.
    """
    cwd = Path.cwd()
    binding_path = cwd / "binding.lob"
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
