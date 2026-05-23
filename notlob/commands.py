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
from notlob.bindings.python import extract_symbols, kit
from notlob.bindings.python.loader import ModuleCache
from notlob.bindings.python.runner import ClaimResult, Status
from notlob.graph import module_address
from notlob.model import BindingSection, Claim, Subheading
from notlob.project import (
    address_from_path,
    build_package,
    find_project_root, module_lob_refs, resolve_module_path,
)


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


# ── Reference-graph builder ───────────────────────────────────

def _build_ref_graph(module, root):
    """Build a NameGraph sufficient for validate_refs.

    Builds the structural graph for *module*, enriches it with
    symbols, then merges in a MODULE node for each directly imported
    module and adds the corresponding IMPORTS edge.  Only direct
    imports are added; transitive imports are not needed because
    validate_refs only resolves one hop via step 3.

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


def cmd_run(path: Path) -> int:
    """Assemble and execute *path*; return an exit code."""
    try:
        module = from_tree(parse_file(path))
    except Exception as exc:
        print(f"ERROR  <parse>  {exc}", file=sys.stderr)
        return 1

    root = find_project_root(path)

    addr_err = _check_address(module, path, root)
    if addr_err:
        print(f"ERROR  <address>  {addr_err}", file=sys.stderr)
        return 1

    cache = ModuleCache(root) if root else None
    ns: dict = {"__file__": str(path.resolve())}
    try:
        if cache is not None:
            for dep_addr in module_lob_refs(module):
                ns.update(cache.load(dep_addr))
        exec(kit.assemble(module), ns)
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


def cmd_test(path: Path) -> int:
    """Run all claims in *path* and return an exit code."""
    try:
        module = from_tree(parse_file(path))
    except Exception as exc:
        print(f"ERROR  <parse>  {exc}", file=sys.stderr)
        return 1

    binding = _find_binding(path)
    root    = find_project_root(path)
    cache   = ModuleCache(root) if root else None

    doc_errors: list[str] = []

    addr_err = _check_address(module, path, root)
    if addr_err:
        doc_errors.append(f"ERROR  <address>  {addr_err}")

    for ref_err in validate_refs(_build_ref_graph(module, root), module):
        doc_errors.append(f"ERROR  <refs>  {ref_err}")

    if doc_errors:
        for msg in doc_errors:
            print(msg, file=sys.stderr)
        return 1

    results = (
        kit.run_examples(module, file_path=path, cache=cache)
        + kit.run_properties(module, binding=binding, file_path=path,
                             cache=cache)
        + kit.run_tests(module, binding=binding, file_path=path,
                        cache=cache)
    )

    for r in results:
        _print_result(r)

    n_fail = sum(1 for r in results if r.status != Status.PASS)
    n_pass = len(results) - n_fail
    if n_fail:
        print(f"\n{n_pass} passed, {n_fail} failed")
    else:
        print(f"\n{n_pass} passed")

    return 1 if n_fail else 0


# ── Graph export ──────────────────────────────────────────────

def cmd_graph(path: Path) -> int:
    """Print the package name-graph as JSON to stdout.

    When *path* is inside a notlob project (a ``binding.lob`` is
    found), the full package graph is built and exported.  For a
    standalone file the single-module graph is used instead.
    """
    root = find_project_root(path)
    if root is not None:
        graph = build_package(root, extract_symbols)
    else:
        try:
            module = from_tree(parse_file(path))
        except Exception as exc:
            print(f"ERROR  <parse>  {exc}", file=sys.stderr)
            return 1
        graph = build(module)
        enrich(graph, module, extract_symbols)

    print(graph.to_json())
    return 0


# ── Query helpers ─────────────────────────────────────────────

def _node_dict(node) -> dict:
    return {
        "address": node.address,
        "label":   node.label,
        "kind":    node.kind.name,
    }


def _require_graph(hint: Path | None = None):
    """Build the package graph, or return None with an error printed."""
    root = find_project_root(hint or Path.cwd())
    if root is None:
        print(
            "ERROR  <project>  no binding.lob found — "
            "run from inside a notlob project",
            file=sys.stderr,
        )
        return None
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
    """Print nodes whose label matches *pattern* (fnmatch-style)."""
    graph = _require_graph()
    if graph is None:
        return 1
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
