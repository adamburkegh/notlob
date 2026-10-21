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

import textwrap
from pathlib import Path
from typing import Callable

from .graph import (
    module_address,
    add_references_edges, add_uses_edges, build, enrich,
    Edge, EdgeKind, Node, NodeKind, NameGraph,
)
from .model import Module, ReferencesSection



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


def _module_lob_refs_with_lines(
    module: "Module",
) -> list[tuple[str, int | None]]:
    """Like :func:`module_lob_refs` but returns (address, line_number) pairs."""
    if module.post_text is None:
        return []
    for section in module.post_text.sections:
        if isinstance(section, ReferencesSection):
            result = []
            for line, lineno in zip(section.lines, section.line_numbers or []):
                stripped = line.strip()
                if stripped.startswith("#"):
                    label = stripped[1:].strip()
                    if label:
                        result.append((module_address(label), lineno))
            return result
    return []


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


class LobRefCycleError(Exception):
    """Modules whose code needs each other: there is no order in which
    their code can be loaded. *cycle* is the addresses, first repeated at
    the end (``["ping", "pong", "ping"]``)."""

    def __init__(self, cycle: list[str]) -> None:
        self.cycle = cycle
        super().__init__(
            "circular code dependency: " + " -> ".join(cycle)
            + " (each module's code uses a name the next one defines; "
            "a module listed in #References but only mentioned in prose "
            "is a citation and does not make a cycle)"
        )


def _defined_names(module: Module, kit) -> set[str]:
    """The top-level names *module*'s own code defines: its body,
    subheadings and ``#Appendix``, not its claims."""
    graph = build(module)
    names: set[str] = set()
    for holder in graph.body_holders(module_address(module.title)):
        for entry in graph.body(holder.address):
            if entry["kind"] == "code":
                names.update(
                    s.name for s in kit.extract_symbols(
                        entry["text"].splitlines()))
    names.discard("_")
    return names


def _used_names(module: Module, kit) -> set[str]:
    """The names *module*'s code statically refers to: its own code and
    its claims' (a claim that calls another module's function counts as
    using that module). Strings and comments do not count: this is the
    binding's call extraction, the same one the name-graph's ``USES``
    edges come from."""
    graph = build(module)
    chunks: list[str] = []
    for holder in graph.body_holders(module_address(module.title)):
        chunks += [e["text"] for e in graph.body(holder.address)
                   if e["kind"] == "code"]
    chunks += [
        (n.content or {}).get("code", "") for n in graph.nodes()
        if n.kind in (NodeKind.EXAMPLE, NodeKind.RUN, NodeKind.TEST,
                      NodeKind.PROPERTY)
    ]
    used: set[str] = set()
    for chunk in chunks:
        used.update(name for name, _ in
                    kit.extract_calls(textwrap.dedent(chunk)))
    # A name the module defines itself is its own, even if another module
    # defines the same name: it is not a use of that module.
    return used - _defined_names(module, kit)


def _is_descendant(address: str, ancestor: str) -> bool:
    """Whether module *address* is below module *ancestor* in the address
    tree (``gutenberg/hamlet`` is below ``gutenberg``)."""
    return address.startswith(ancestor + "/")


def _plan(
    module: Module, root: Path, kit=None,
) -> tuple[list[tuple[str, Module | None]], list[str] | None]:
    """``(order, cycle)``: the modules whose code *module* needs, and what
    those need, dependencies first, each once, as ``(address, parsed
    module or None)`` (``None`` marks one that could not be found or
    parsed); and, if there is no order, the addresses of a cycle of need
    (first repeated at the end).

    Which ``#References`` entries are followed is decided entry by entry
    (DESIGN.md, "Listing, citing and loading"). A listing is followed when
    the listing module *needs* the listed one: its code (body and claims)
    refers to a name the listed module's code defines, less names the
    listing module defines itself. A listing that is not needed is a
    citation and loads nothing. When that cannot be told, because there is
    no *kit*, the binding's reference extraction is not complete
    (``kit.complete_references``), or either module cannot be read, the
    address tree decides: a listing of a descendant is a citation, and
    any other listing is followed."""
    from .parser import parse_file
    from .model import from_tree as _from_tree

    root_addr = module_address(module.title)
    parsed: dict[str, Module | None] = {root_addr: module}
    defined: dict[str, set[str]] = {}
    used:    dict[str, set[str]] = {}

    def load(addr: str) -> Module | None:
        if addr not in parsed:
            try:
                parsed[addr] = _from_tree(
                    parse_file(resolve_module_path(addr, root)))
            except Exception:
                parsed[addr] = None
        return parsed[addr]

    def follows(user: str, listed: str) -> bool:
        user_mod, listed_mod = load(user), load(listed)
        if (kit is None or not kit.complete_references
                or kit.extract_calls is None
                or user_mod is None or listed_mod is None):
            return not _is_descendant(listed, user)
        if listed not in defined:
            defined[listed] = _defined_names(listed_mod, kit)
        if user not in used:
            used[user] = _used_names(user_mod, kit)
        return bool(defined[listed] & used[user])

    visited: set[str] = set()
    stack:   list[str] = [root_addr]
    order:   list[tuple[str, Module | None]] = []
    cycle:   list[str] | None = None

    def visit(addr: str) -> None:
        nonlocal cycle
        visited.add(addr)
        stack.append(addr)
        dep = load(addr)
        if dep is not None:
            for child in module_lob_refs(dep):
                if not follows(addr, child):
                    continue
                if child in stack:
                    if cycle is None:
                        cycle = stack[stack.index(child):] + [child]
                elif child not in visited:
                    visit(child)
        stack.pop()
        order.append((addr, dep))

    for child in module_lob_refs(module):
        if not follows(root_addr, child):
            continue
        if child in stack:
            cycle = cycle or [root_addr, root_addr]
        elif child not in visited:
            visit(child)
    return order, cycle


def lob_ref_cycle(
    module: Module, root: Path, kit=None,
) -> list[str] | None:
    """The addresses of a cycle among the modules whose code *module*
    needs (see :func:`_plan`), or ``None``. A cycle made only of citations
    is not one."""
    return _plan(module, root, kit)[1]


def _dependency_order(
    module: Module, root: Path, kit=None,
) -> list[tuple[str, Module | None]]:
    order, cycle = _plan(module, root, kit)
    if cycle is not None:
        raise LobRefCycleError(cycle)
    return order


def transitive_lob_refs(
    module: Module, root: Path, kit=None,
) -> list[str]:
    """Return all transitive lob dependencies in topological order (deps first).

    Performs a depth-first traversal of the dependency graph rooted at
    *module*, following each module's own ``#References`` recursively.
    The root module itself is excluded — callers assemble it separately.
    Duplicate nodes are emitted only once, in the order first encountered
    via DFS post-order. Cycles: see :func:`_plan`; a code cycle raises
    :class:`LobRefCycleError`.
    """
    return [addr for addr, _ in _dependency_order(module, root, kit)]


def load_dependency_modules(
    module: Module, root: Path, kit=None,
) -> list[Module]:
    """The modules *module*'s code needs in order to run, parsed: its
    lob-refs, theirs, and so on, each once, dependencies first.

    This is what every binding's runner and builder inlines before the
    module itself. Loading is transitive because a module that works on
    its own must work when something else uses it: ``Top`` lists only
    ``Middle``, but ``Middle``'s code needs ``Base``. (What ``Top`` may
    *use* is a separate matter: it should use only what it lists, which
    lint enforces; loading everything does not widen that.) A dependency
    that cannot be found or parsed is skipped; its absence surfaces where
    it is used, as a name error or a compile error.

    Loading follows need, not listing: a module is loaded when the code of
    the module that lists it uses a name it defines. A listing the code
    does not use is a citation and loads nothing, so modules may list each
    other (an overview that cites its parts, parts that list the
    overview). Pass the binding's *kit* to tell; without it the address
    tree decides (see :func:`_plan`). If each module's code does use the
    other there is no order, and :class:`LobRefCycleError` is raised.
    """
    return [dep for _, dep in _dependency_order(module, root, kit)
            if dep is not None]


def build_package(
    root:            Path,
    extractor:       Callable | None = None,
    call_extractor:  Callable | None = None,
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
    call_extractor:
        Optional language-specific call extractor for USES edge population.
        Pass ``notlob.bindings.python.extract_calls`` for Python projects.
        Requires *extractor* to also be set (symbols must exist before
        USES edges can be resolved).

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
        for dep_addr, ref_line in _module_lob_refs_with_lines(module):
            key = (importer, dep_addr)
            if key in seen:
                continue
            if graph.node(dep_addr) is not None:
                graph.add_edge(Edge(
                    source=importer,
                    target=dep_addr,
                    kind=EdgeKind.IMPORTS,
                    start_line=ref_line,
                ))
                seen.add(key)

    # Third pass: add EXTERNAL nodes from binding.lob declarations.
    _add_external_nodes(graph, root)

    # Fourth pass: add REFERENCES edges from prose #Label cross-references.
    add_references_edges(graph)

    # Fifth pass: add USES edges from statically visible call references.
    if call_extractor is not None:
        add_uses_edges(graph, call_extractor)

    return graph


def _add_external_nodes(graph: NameGraph, root: Path) -> None:
    """Add EXTERNAL nodes and USES edges from ``binding.lob`` declarations.

    Reads ``~external`` declarations from the project's ``binding.lob``
    and adds a ``NodeKind.EXTERNAL`` node for each declared file, with a
    ``EdgeKind.USES_EXTERNAL`` edge from the binding module (whose address is
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

    binding_section: BindingSection | None = None
    if bmod.post_text:
        for section in bmod.post_text.sections:
            if isinstance(section, BindingSection):
                binding_section = section
                break

    # Pair each external filename with its declaration line.
    external_files: list[tuple[str, int | None]] = list(zip(
        binding_section.externals if binding_section else [],
        binding_section.external_lines if binding_section else [],
    ))
    on_build = binding_section.on_build if binding_section else None
    if on_build:
        on_build_line = binding_section.on_build_line if binding_section else None
        external_files.append((on_build, on_build_line))

    for filename, decl_line in external_files:
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
            kind=EdgeKind.USES_EXTERNAL,
            start_line=decl_line,
        ))
