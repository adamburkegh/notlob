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
import sys
import textwrap
from pathlib import Path

from notlob import (
    build, enrich, from_tree, parse_file, validate_refs,
    Edge, EdgeKind, NodeKind,
)
from notlob.bindings import ClaimResult, LintResult, Status
from notlob.bindings.python import extract_symbols as _py_extract, kit as _py_kit
from notlob.bindings.python.loader import ModuleCache
from notlob.graph import module_address
from notlob.model import BindingSection, Claim, Subheading
from notlob.project import (
    address_from_path,
    build_package,
    find_project_root, module_lob_refs, resolve_module_path,
)


# ── Language dispatch ─────────────────────────────────────────

def _get_binding_kit(language: str | None):
    """Return ``(kit, extract_symbols)`` for the given language name.

    Defaults to the Python kit for ``None`` or unrecognised languages.
    Adding a new language binding requires only a new branch here.
    """
    if language == "haskell":
        from notlob.bindings.haskell import (   # lazy: avoids import if unused
            kit as _hs_kit,
            extract_symbols as _hs_extract,
        )
        return _hs_kit, _hs_extract
    # default — python
    return _py_kit, _py_extract


# ── Binding resolution ────────────────────────────────────────

def _parse_binding_declarations(lines: list[str]) -> dict[str, str]:
    """Extract ~sigil declarations from a #Binding section's lines."""
    result: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("~"):
            parts = stripped[1:].split(None, 1)
            key = parts[0]
            value = parts[1].strip() if len(parts) > 1 else ""
            result[key] = value
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
                    return _parse_binding_declarations(section.lines)
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

def _print_result(r: ClaimResult) -> None:
    tag = r.status.name
    print(f"{tag:5}  {r.address}  {r.line}")
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
    """Return all ~run claims from the module body and subheadings,
    in document order.
    """
    claims = []
    for item in module.body:
        if isinstance(item, Claim) and item.sigil == "~run":
            claims.append(item)
        elif isinstance(item, Subheading):
            for sub_item in item.body:
                if (isinstance(sub_item, Claim)
                        and sub_item.sigil == "~run"):
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
) -> int:
    """Assemble a Haskell module (with inlined deps) and run with runghc.

    The assembled source must define ``main :: IO ()``.  If no ``main``
    is present GHC will report a link error, which surfaces here as a
    non-zero exit code with the compiler message on stderr.

    If *keep_dir* is set the assembled source is also written there as
    ``<module-address-slugified>.hs`` before execution.
    """
    from notlob.bindings.haskell.assemble import assemble_with_deps
    from notlob.bindings.haskell.runner import (
        _load_dep_modules, _run_harness,
    )

    dep_modules = _load_dep_modules(module, path)
    source      = assemble_with_deps(module, dep_modules)
    if not source:
        print("ERROR  <assembly>  module contains no code", file=sys.stderr)
        return 1

    if keep_dir is not None:
        from notlob.graph import module_address as _mod_addr
        slug = _mod_addr(module.title).replace("/", "_")
        keep_path = keep_dir / f"{slug}.hs"
    else:
        keep_path = None

    stdout, stderr, rc = _run_harness(source, keep_path=keep_path)
    if stdout:
        print(stdout, end="")
    if rc != 0:
        if stderr:
            print(stderr, end="", file=sys.stderr)
        return 1
    return 0


def cmd_run(path: Path, keep_generated_src: str | None = None) -> int:
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
        return _cmd_run_haskell(module, path, keep_dir=keep_dir)

    root = find_project_root(path)

    addr_err = _check_address(module, path, root)
    if addr_err:
        print(f"ERROR  <address>  {addr_err}", file=sys.stderr)
        return 1

    py_kit = _py_kit
    cache = ModuleCache(root) if root else None
    ns: dict = {"__file__": str(path.resolve())}
    try:
        if cache is not None:
            for dep_addr in module_lob_refs(module):
                ns.update(cache.load(dep_addr))
        exec(py_kit.assemble(module), ns)
    except Exception as exc:
        print(f"ERROR  <assembly>  {exc}", file=sys.stderr)
        return 1

    for claim in _collect_run_claims(module):
        try:
            exec(textwrap.dedent("\n".join(claim.lines)), ns)
        except Exception as exc:
            print(f"ERROR  <run>  {exc}", file=sys.stderr)
            return 1

    return 0


def _test_module(
    path:               Path,
    root:               Path | None,
    binding:            dict,
    keep_generated_src: str | None      = None,
    only:               set[str] | None = None,
) -> tuple[int, int, int]:
    """Test one module; print per-claim output.

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
        lint_results = kit.lint(module, root=root)
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
) -> int:
    """Run claims in *path* (or all project modules) and return an exit code.

    When *path* is omitted, discovers the project from CWD and tests
    every module.  Pass a specific *.lob* path to test a single module.

    *only* restricts which check types run.  When *None* all checks run.
    Valid values in the set: ``"lint"``, ``"examples"``, ``"props"``,
    ``"tests"``.  Lint failures produce exit code 1 just like claim
    failures.
    """
    if path is not None:
        root    = find_project_root(path)
        binding = _find_binding(path)
        n_pass, n_fail, n_lint = _test_module(
            path, root, binding, keep_generated_src, only,
        )
    else:
        root, binding = _require_root()
        if root is None:
            return 1
        n_pass = n_fail = n_lint = 0
        for lob_path in sorted(root.glob("**/*.lob")):
            if lob_path.name == "binding.lob":
                continue
            p, f, l = _test_module(
                lob_path, root, binding, keep_generated_src, only,
            )
            n_pass += p
            n_fail += f
            n_lint += l

    parts = [f"{n_pass} passed"]
    if n_fail:
        parts.append(f"{n_fail} failed")
    if n_lint:
        parts.append(f"{n_lint} lint")
    print(f"\n{', '.join(parts)}")

    return 1 if (n_fail or n_lint) else 0


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


def _build_one(path: Path, kit, output_dir: Path) -> int:
    """Build a single module and write the artifact to *output_dir*.

    Returns 0 on success, 1 on error.  Prints ``BUILD  <out_path>`` on
    success, or an ERROR line on failure.
    """
    try:
        module = from_tree(parse_file(path))
    except Exception as exc:
        print(f"ERROR  <parse>  {exc}", file=sys.stderr)
        return 1

    source = kit.build(module, path)
    if not source:
        print("ERROR  <assembly>  module contains no code", file=sys.stderr)
        return 1

    mod_addr = module_address(module.title)
    header   = _build_header(kit.comment_prefix, mod_addr, path.name)
    slug     = mod_addr.replace("/", "_")
    out_path = output_dir / f"{slug}.{kit.extension}"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + "\n" + source, encoding="utf-8")
    print(f"BUILD  {out_path}")
    return 0


def cmd_build(path: Path | None = None, output_dir: Path = Path("dist")) -> int:
    """Assemble *path* (or all project modules) and write to *output_dir*.

    When *path* is omitted, discovers the project from CWD and builds
    every module.  Pass a specific *.lob* path to build a single module.

    The output filename is ``<slug>.<ext>`` where *slug* is the module
    address with ``/`` replaced by ``_`` and *ext* is the language
    extension from the binding kit (e.g. ``hs``, ``py``).

    Each binding's ``build`` callable owns the assembly strategy — e.g.
    Haskell inlines dependencies; Python writes the module's own source.
    """
    if path is not None:
        binding  = _find_binding(path)
        language = binding.get("language")
        kit, _   = _get_binding_kit(language)
        if kit.build is None:
            print(
                f"ERROR  <build>  no build support for language "
                f"{language!r}",
                file=sys.stderr,
            )
            return 1
        return _build_one(path, kit, output_dir)

    root, binding = _require_root()
    if root is None:
        return 1
    language = binding.get("language")
    kit, _   = _get_binding_kit(language)
    if kit.build is None:
        print(
            f"ERROR  <build>  no build support for language "
            f"{language!r}",
            file=sys.stderr,
        )
        return 1
    rc = 0
    for lob_path in sorted(root.glob("**/*.lob")):
        if lob_path.name == "binding.lob":
            continue
        if _build_one(lob_path, kit, output_dir) != 0:
            rc = 1
    return rc


# ── Graph export ──────────────────────────────────────────────

def cmd_graph(
    path:            Path | None = None,
    include_content: bool        = False,
) -> int:
    """Print the package name-graph as JSON to stdout.

    When *path* is omitted, discovers the project from CWD and exports
    the full package graph.  Pass a specific *.lob* path to export that
    file's module graph (or its project graph when it is inside a
    project).

    The language binding (from ``binding.lob``) controls symbol
    extraction.  Pass *include_content=True* to attach prose/code to
    every node.
    """
    if path is not None:
        root    = find_project_root(path)
        binding = _find_binding(path) if root else {}
    else:
        root, binding = _require_root()
        if root is None:
            return 1

    language = (binding or {}).get("language")
    _, extract_symbols = _get_binding_kit(language)

    if root is not None:
        graph = build_package(root, extract_symbols)
    else:
        # standalone file — only reachable via an explicit path arg
        try:
            module = from_tree(parse_file(path))
        except Exception as exc:
            print(f"ERROR  <parse>  {exc}", file=sys.stderr)
            return 1
        graph = build(module)
        enrich(graph, module, extract_symbols)

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
    _, extract_symbols = _get_binding_kit(
        binding.get("language") if binding else None
    )
    return build_package(root, extract_symbols)


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
