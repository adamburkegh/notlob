"""notlob.project — Project-level utilities.

A notlob project is rooted at the directory containing ``binding.lob``.
This module provides the tools for locating the project root, resolving
module addresses to filesystem paths, and parsing the two kinds of line
that can appear in a ``#References`` section: lob module references and
Python import statements.

Lob module references use the ``#Title`` syntax — the same ``#``
dereference operator used in prose::

    #References
        #Roman Numerals
        from decimal import Decimal

Lines whose stripped content starts with ``#`` are lob module references;
all other non-blank lines are Python imports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .graph import (
    module_address,
    build, enrich,
    Edge, EdgeKind, Node, NodeKind, NameGraph,
)
from .model import Module, ReferencesSection


def _parse_binding_lines(lines: list[str]) -> dict:
    """Extract ``~sigil value`` declarations from a ``#Binding`` section.

    Most sigils are single-valued and stored as ``str``.  ``~external``
    may appear multiple times and is stored as ``list[str]``.
    """
    result: dict = {}
    externals: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("~"):
            parts = stripped[1:].split(None, 1)
            key   = parts[0]
            value = parts[1].strip() if len(parts) > 1 else ""
            if key == "external":
                externals.append(value)
            else:
                result[key] = value
    if externals:
        result["external"] = externals
    return result


def find_project_root(path: Path) -> Path | None:
    """Walk up from *path* to find the nearest ``binding.lob``.

    If *path* is a directory it is checked first, then its ancestors.
    If *path* is a file, the search starts from its parent directory.

    Returns the directory containing ``binding.lob``, or ``None`` if no
    ``binding.lob`` is found before the filesystem root.
    """
    resolved = path.resolve()
    candidates = (
        [resolved, *resolved.parents]
        if resolved.is_dir()
        else resolved.parents
    )
    for d in candidates:
        if (d / "binding.lob").exists():
            return d
    return None


def resolve_module_path(address: str, root: Path) -> Path:
    """Translate a module address to a ``.lob`` filesystem path.

    ``"roman/numerals"`` under *root* → ``root/roman/numerals.lob``.
    """
    return root / Path(address).with_suffix(".lob")


def address_from_path(path: Path, root: Path) -> str:
    """Compute the expected module address from a ``.lob`` file path.

    This is the inverse of :func:`resolve_module_path`: given a file
    path under a project root, return the module address that the
    module's title *should* produce via
    :func:`notlob.graph.module_address`.

    ``root/gutenberg/titus.lob`` → ``"gutenberg/titus"``

    A module whose title-derived address does not match this value is
    misnamed: it cannot be reliably referenced from other modules.
    """
    return path.relative_to(root).with_suffix("").as_posix()


def parse_lob_refs(lines: list[str]) -> list[str]:
    """Return module addresses declared in a ``#References`` line list.

    A lob reference line is one whose stripped content starts with ``#``,
    e.g. ``    #Roman Numerals``.  The label after ``#`` is converted to
    a module address via :func:`notlob.graph.module_address`.

    Lines that are blank or start with anything other than ``#`` are
    ignored (they are Python imports, handled by
    :func:`parse_python_imports`).
    """
    refs = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            label = stripped[1:].strip()
            if label:
                refs.append(module_address(label))
    return refs


def parse_python_imports(lines: list[str]) -> list[str]:
    """Return the Python import lines from a ``#References`` line list.

    This is the complement of :func:`parse_lob_refs`: every line whose
    stripped content does *not* start with ``#``.  Blank lines are
    preserved so that dedent/strip in the assembler works as before.
    """
    return [line for line in lines if not line.strip().startswith("#")]


def module_lob_refs(module: Module) -> list[str]:
    """Return lob module addresses declared in *module*'s ``#References``.

    Convenience wrapper around :func:`parse_lob_refs` that locates the
    ``ReferencesSection`` in the module's post-text.  Returns an empty
    list if the module has no post-text or no ``#References`` section.
    """
    if module.post_text is None:
        return []
    for section in module.post_text.sections:
        if isinstance(section, ReferencesSection):
            return parse_lob_refs(section.lines)
    return []


def build_package(
    root:      Path,
    extractor: Callable | None = None,
) -> NameGraph:
    """Build a package-level NameGraph.

    Discovers every ``*.lob`` file under *root*, constructs a
    structural graph for each (with symbol enrichment when *extractor*
    is supplied), merges them into a single graph, then adds ``IMPORTS``
    edges derived from each module's ``#References`` lob-ref
    declarations.

    Files that fail to parse are silently skipped — a partial package
    graph is better than an error that blocks all tooling.

    Duplicate ``IMPORTS`` edges (the same ref declared twice) are
    suppressed.  An ``IMPORTS`` edge is only added when the referenced
    module is also present in the graph; dangling references (pointing
    at a missing file) produce no edge.

    Parameters
    ----------
    root:
        The project root — the directory containing ``binding.lob``.
    extractor:
        Optional language-specific symbol extractor for symbol enrichment.
        Pass ``notlob.bindings.python.extract_symbols`` for Python
        projects.

    Returns
    -------
    NameGraph
        A merged graph containing all discoverable nodes and all
        declared ``IMPORTS`` edges.
    """
    # Local import avoids a top-level circular dependency through
    # __init__.py; parser and model are stable leaf modules.
    from .parser import parse_file
    from .model import from_tree

    graph:   NameGraph          = NameGraph()
    modules: list[Module]       = []

    for path in sorted(root.glob("**/*.lob")):
        try:
            module = from_tree(parse_file(path))
        except Exception:
            continue
        mod_graph = build(module)
        if extractor is not None:
            enrich(mod_graph, module, extractor)
        graph.merge(mod_graph)
        modules.append(module)

    # Second pass: add IMPORTS edges once all modules are in the graph.
    seen: set[tuple[str, str]] = set()
    for module in modules:
        importer = module_address(module.title)
        for dep_addr in module_lob_refs(module):
            key = (importer, dep_addr)
            if key in seen:
                continue
            if graph.node(dep_addr) is not None:
                graph.add_edge(Edge(
                    source=importer,
                    target=dep_addr,
                    kind=EdgeKind.IMPORTS,
                ))
                seen.add(key)

    # Third pass: add EXTERNAL nodes from binding.lob declarations.
    _add_external_nodes(graph, root)

    return graph


def _add_external_nodes(graph: NameGraph, root: Path) -> None:
    """Add EXTERNAL nodes and USES edges from ``binding.lob`` declarations.

    Reads ``~external`` declarations from the project's ``binding.lob``
    and adds a ``NodeKind.EXTERNAL`` node for each declared file, with a
    ``EdgeKind.USES`` edge from the binding module (whose address is
    derived from the ``binding.lob`` title) to the external node.

    Files declared with ``~on-build`` are also added as EXTERNAL nodes
    with a USES edge, so they appear in ``notlob query`` output.

    Silently skips if ``binding.lob`` cannot be parsed or has no
    ``~external`` / ``~on-build`` declarations.
    """
    binding_path = root / "binding.lob"
    if not binding_path.exists():
        return

    try:
        from .parser import parse_file
        from .model import from_tree, BindingSection
        bmod = from_tree(parse_file(binding_path))
        binding_addr = module_address(bmod.title)
    except Exception:
        return

    declarations: dict = {}
    if bmod.post_text:
        for section in bmod.post_text.sections:
            if isinstance(section, BindingSection):
                declarations = _parse_binding_lines(section.lines)
                break

    external_files: list[str] = list(declarations.get("external", []))
    on_build = declarations.get("on-build")
    if on_build:
        external_files.append(on_build)

    for filename in external_files:
        addr = filename   # address is the filename relative to project root
        if graph.node(addr) is None:
            graph.add_node(Node(
                address=addr,
                label=filename,
                kind=NodeKind.EXTERNAL,
            ))
        graph.add_edge(Edge(
            source=binding_addr,
            target=addr,
            kind=EdgeKind.USES,
        ))
