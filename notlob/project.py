"""notlob.project — Project-level utilities.

A notlob project is rooted at the directory containing ``binding.lob``.
This module provides the tools for locating the project root, resolving
module addresses to filesystem paths, and building the package graph.

A ``#References`` section holds two kinds of line, which the grammar tells
apart: lob module listings, which use the ``#Title`` syntax — the same
``#`` dereference operator used in prose — and the bound language's import
statements::

    #References
        #Roman Numerals
        from decimal import Decimal
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .graph import (
    module_address,
    add_bodies, add_cites_edges, add_uses_edges, build, enrich,
    AddressCollisionError, Edge, EdgeKind, Node, NodeKind, NameGraph,
)
from .model import Module, ReferencesSection



class ProjectParseError(Exception):
    """One or more ``.lob`` files of a project do not parse. *failures* is
    a line for each, ``file:line: reason`` with the file relative to the
    project root (see :func:`parse_failure`)."""

    def __init__(self, failures: list[str]):
        self.failures = failures
        super().__init__("\n".join(failures))


def parse_failure(path: Path, root: Path, exc: Exception) -> str:
    """The failure of the file at *path* under *root* to parse, as one
    line, ``file:line: reason`` (``file: reason`` when the error knows no
    line), the file relative to *root* with ``/`` separators. The reason is
    the first line of the error's message: Lark's goes on to list what it
    expected, from a set whose order changes between runs."""
    from .parser import LobSyntaxError

    try:
        file = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        file = path.as_posix()
    if isinstance(exc, LobSyntaxError):
        return f"{file}:{exc.line}: {exc.reason}"
    reason = (str(exc).splitlines() or [type(exc).__name__])[0]
    line = getattr(exc, "line", None)
    return f"{file}:{line}: {reason}" if line else f"{file}: {reason}"


def parse_project(root: Path) -> list[tuple[Path, Module]]:
    """Every ``.lob`` file under *root*, ``binding.lob`` included, parsed
    to its :class:`~notlob.model.Module`: ``(path, module)`` in sorted path
    order, each module holding the text of its file (its ``source``, which
    is where the graph's bodies come from). The one place a project's
    files are read. If any do not parse,
    all of them have been read first, and :class:`ProjectParseError` lists
    each failure."""
    from .parser import parse
    from .model import from_tree

    parsed: list[tuple[Path, Module]] = []
    unparsed: list[str] = []
    for path in sorted(root.glob("**/*.lob")):
        try:
            source = path.read_text(encoding="utf-8")
            parsed.append((path, from_tree(parse(source), source)))
        except Exception as exc:
            unparsed.append(parse_failure(path, root, exc))
    if unparsed:
        raise ProjectParseError(unparsed)
    return parsed


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


def module_lob_refs(module: Module) -> list[str]:
    """Return lob module addresses listed in *module*'s ``#References``,
    in the order written: the section's listings, which the grammar tells
    from its import lines.  Returns an empty list if the module has no
    post-text or no ``#References`` section.
    """
    if module.post_text is None:
        return []
    for section in module.post_text.sections:
        if isinstance(section, ReferencesSection):
            return [module_address(listing.title)
                    for listing in section.listings]
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


def _used_in_code(graph: NameGraph) -> dict[str, dict[str, set[str]]]:
    """For each module, the names of other modules' own code that its
    tree uses, by the module that defines them: ``{user: {defining
    module: names}}``, read from the ``USES`` edges.

    A name is another module's own code when its symbol is written in a
    code block of that module, and not when a ``~property`` there
    defines it."""
    found: dict[str, dict[str, set[str]]] = {}
    for edge in graph.edges(EdgeKind.USES):
        target = graph.node(edge.target)
        holder = graph.parent_of(edge.target)
        if (target is None or target.kind != NodeKind.SYMBOL
                or holder is None or holder.kind != NodeKind.CODE):
            continue
        user = graph.module_of(edge.source)
        defining = graph.module_of(edge.target)
        if user is None or defining is None or user == defining:
            continue
        found.setdefault(user, {}).setdefault(defining, set()).add(
            target.label)
    return found


def _defined_in_code(graph: NameGraph) -> dict[str, set[str]]:
    """For each module, the names its own code defines: the symbols
    written in its code blocks."""
    found: dict[str, set[str]] = {}
    for symbol in graph.nodes(NodeKind.SYMBOL):
        holder = graph.parent_of(symbol.address)
        if holder is not None and holder.kind == NodeKind.CODE:
            found.setdefault(graph.module_of(symbol.address), set()).add(
                symbol.label)
    return found


def load_order(graph: NameGraph, address: str, kit=None) -> list[str]:
    """The modules the code of the module at *address* needs, and what
    they need, dependencies first, each once. Raises
    :class:`LobRefCycleError` naming a cycle of need.

    Loading follows need, not listing (DESIGN.md, "Listing, citing and
    loading"). Module A *needs* module B when A lists B in
    ``#References`` (an ``IMPORTS`` edge) and the code of A, its claims
    and its tests included, uses a name B's own code defines (a ``USES``
    edge into a code block of B), less the names A's own code defines.
    A listing that is not needed is a citation and loads nothing.

    That is read from *graph*, which must have been built with the
    binding's symbol and call extractors. When the binding's reference
    extraction is not complete (``kit.complete_references``), or *kit* is
    ``None`` or extracts no calls, use cannot be told and the address
    tree decides: a listing of a module below the listing module
    (``gutenberg/hamlet`` is below ``gutenberg``) is a citation, and any
    other is needed."""
    complete = (kit is not None and kit.complete_references
                and kit.extract_calls is not None)
    used = _used_in_code(graph) if complete else {}
    defined = _defined_in_code(graph) if complete else {}

    def needs(user: str) -> list[str]:
        listed = [node.address for node in graph.imports_of(user)]
        if not complete:
            return [dep for dep in listed
                    if not dep.startswith(user + "/")]
        own = defined.get(user, set())
        return [dep for dep in listed
                if used.get(user, {}).get(dep, set()) - own]

    visited: set[str] = set()
    stack: list[str] = [address]
    order: list[str] = []

    def visit(module: str) -> None:
        visited.add(module)
        stack.append(module)
        for dep in needs(module):
            if dep in stack:
                raise LobRefCycleError(stack[stack.index(dep):] + [dep])
            if dep not in visited:
                visit(dep)
        stack.pop()
        order.append(module)

    for dep in needs(address):
        if dep in stack:
            raise LobRefCycleError([address, address])
        if dep not in visited:
            visit(dep)
    return order


def load_dependencies(
    graph: NameGraph, address: str, root: Path, kit=None,
) -> list[Module]:
    """The modules the code of the module at *address* needs
    (:func:`load_order`), parsed from their files under *root*, in that
    order. This is what a command hands a binding as ``deps``. A module
    that cannot be read is skipped; its absence shows where it is used.
    Raises :class:`LobRefCycleError`."""
    from .parser import parse_file
    from .model import from_tree

    modules: list[Module] = []
    for dep in load_order(graph, address, kit):
        node = graph.node(dep)
        path = (root / node.file if node is not None and node.file
                else resolve_module_path(dep, root))
        try:
            modules.append(from_tree(parse_file(path)))
        except Exception:
            pass
    return modules


def _module_graph(
    module:     Module,
    path:       Path,
    root:       Path,
    extractor:  Callable | None,
    collisions: list | None,
    split_imports: Callable | None = None,
) -> NameGraph:
    """The graph of the module at *path* in a package, its tree and, when
    there is an *extractor*, its symbols and import statements, and the
    ``body`` of each node written in it (see :func:`add_bodies`).

    A name that collides raises, unless a list of *collisions* is given.
    Then the module keeps its tree without symbols and ``(path, error)``
    is appended to the list, for the first collision found in it."""
    file = path.relative_to(root).as_posix()
    if collisions is None:
        graph = build(module, file)
        if extractor is not None:
            enrich(graph, module, extractor, split_imports)
        add_bodies(graph, module)
        return graph
    found: list[AddressCollisionError] = []
    graph = build(module, file, collisions=found)
    if not found and extractor is not None:
        try:
            enrich(graph, module, extractor, split_imports)
        except AddressCollisionError as exc:
            found.append(exc)
            graph = build(module, file, collisions=[])
    add_bodies(graph, module)
    if found:
        collisions.append((path, found[0]))
    return graph


def build_package(
    root:            Path,
    extractor:       Callable | None = None,
    call_extractor:  Callable | None = None,
    collisions:      list | None = None,
    split_imports:   Callable | None = None,
) -> NameGraph:
    """Build a package-level NameGraph.

    Discovers every ``*.lob`` file under *root*, constructs a
    structural graph for each (with symbol enrichment when *extractor*
    is supplied), merges them into a single graph, then adds ``IMPORTS``
    edges from each module's listings in ``#References``, each starting
    at the line that makes it.

    A file that fails to parse is an error: after every file has been
    read, :class:`ProjectParseError` says which failed and where, and no
    graph is made. (A graph without a module would leave what is checked,
    tested and queried quietly short of it.)

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
    split_imports:
        Optional language-specific splitter of the import lines of
        ``#References`` into statements, for the ``IMPORT`` nodes
        (see :data:`notlob.bindings.ImportSplitter`); used with
        *extractor*, by the same binding.
    collisions:
        Optional list to collect name collisions in.  Without one, the
        first module whose names collide raises
        :class:`~notlob.graph.AddressCollisionError` and no graph is
        made.  With one, such a module keeps its tree but gets no
        symbols, ``(path, error)`` is appended for it, and the other
        modules are built whole.

    Returns
    -------
    NameGraph
        A merged graph containing all discoverable nodes and all
        declared ``IMPORTS`` edges.
    """
    graph:   NameGraph    = NameGraph()
    modules: list[Module] = []

    for path, module in parse_project(root):
        mod_graph = _module_graph(
            module, path, root, extractor, collisions, split_imports)
        graph.merge(mod_graph)
        modules.append(module)

    # Second pass: add IMPORTS edges once all modules are in the graph,
    # each from the listing that makes it.
    seen: set[tuple[str, str]] = set()
    for module in modules:
        importer = module_address(module.title)
        section = graph.post_section(importer, NodeKind.REFERENCES)
        if section is None:
            continue
        listings = [n for n in graph.children(section.address)
                    if n.kind == NodeKind.LISTING]
        for listing, dep in zip(listings, module_lob_refs(module)):
            key = (importer, dep)
            if key in seen:
                continue
            if graph.node(dep) is not None:
                graph.add_edge(Edge(
                    source=listing.address,
                    target=dep,
                    kind=EdgeKind.IMPORTS,
                    lines=(() if listing.start_line is None
                           else (listing.start_line,)),
                ))
                seen.add(key)

    # Third pass: add EXTERNAL nodes for the files binding.lob declares.
    _add_external_nodes(graph)

    # Fourth pass: add CITES edges from prose #Label cross-references.
    add_cites_edges(graph)

    # Fifth pass: add USES edges from statically visible call references.
    if call_extractor is not None:
        add_uses_edges(graph, call_extractor)

    return graph


def _add_external_nodes(graph: NameGraph) -> None:
    """Add EXTERNAL nodes and USES_EXTERNAL edges for the files
    ``binding.lob`` declares.

    Reads the ``~external`` and ``~on-build`` declarations of the
    ``binding.lob`` that is in *graph* and adds a ``NodeKind.EXTERNAL``
    node for each declared file, with an ``EdgeKind.USES_EXTERNAL`` edge
    from the declaration that names it (so a declared file appears in
    ``notlob query`` output). Nothing is added if ``binding.lob`` is not
    in the graph or declares no file.
    """
    for declaration in list(graph.nodes(NodeKind.DECLARATION)):
        if (declaration.file != "binding.lob" or not declaration.value
                or declaration.declares not in ("external", "on-build")):
            continue
        addr = declaration.value   # the file, relative to the project root
        if graph.node(addr) is None:
            graph.add_node(Node(
                address=addr,
                label=addr,
                kind=NodeKind.EXTERNAL,
                name=addr,
            ))
        graph.add_edge(Edge(
            source=declaration.address,
            target=addr,
            kind=EdgeKind.USES_EXTERNAL,
            lines=(() if declaration.start_line is None
                   else (declaration.start_line,)),
        ))
