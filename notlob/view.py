"""The view: a start, a depth and a rank over the tree of a graph.

A view gives the nodes, the edges and the bodies at or below its rank (see
:class:`~notlob.graph.Rank`), once, for any writer to write: no writer
decides what a level holds, or knows what one is.

* **Containment.** A ``CONTAINS`` edge is always the tree's. Where the view
  hides what holds a node, it gives ``CONTAINS_INDIRECTLY`` from the
  nearest node above that it shows.
* **References.** An edge's source is the nearest node at or above where
  it is written that an ``outline`` shows, the same at every rank; where
  the view does not show that node (it starts below it, or its depth stops
  short of it), the nearest it does. References merge on source, target
  and kind, and their lines join, in order, each once.
* **Ends.** An edge is in the view only if both its ends are.
* **Depth** counts the steps the view shows.
* **Lines.** A line is in the body of the written node that holds it;
  where the view does not show that node, it is in the body of the
  deepest node the view shows that covers it (see
  :func:`~notlob.graph.bodies`).

A view made from a preset (see :func:`level_view`) carries the preset's
name as its ``level``, which is for the JSON writer and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .graph import (
    EDGE_RANKS, KINDS, PRESETS, Edge, EdgeKind, NameGraph, Node, NodeKind,
    Rank, bodies,
)


@dataclass(frozen=True)
class ViewNode:
    """A node of a view. The names of the fields are the document's: each
    is written once, in snake_case, and a format with a convention of its
    own converts the name.

    kind        what the node is
    name        the name its address is built from, if it has one
    file        the ``.lob`` file, on the root of a tree of the view
    start_line  the line it begins on in its file
    body        its own written lines, at the rank that has them
    """
    address:    str
    kind:       NodeKind
    name:       str | None = None
    mode:       str | None = None
    declares:   str | None = None
    value:      str | None = None
    file:       str | None = None
    start_line: int | None = None
    body:       str | None = None


@dataclass(frozen=True)
class ViewEdge:
    """An edge of a view: *lines* are every line a reference is written
    on, in order, each once."""
    source: str
    target: str
    kind:   EdgeKind
    lines:  tuple[int, ...] = ()


@dataclass(frozen=True)
class View:
    """What a graph shows at a rank: *nodes* in the order they are written,
    depth first, each tree after the one before; *tree*, the containment
    edges into every node but a root, in that order; and *references*.
    *level* is the name of the preset it was made from, or ``None``."""
    level:      str | None
    nodes:      tuple[ViewNode, ...]
    tree:       tuple[ViewEdge, ...]
    references: tuple[ViewEdge, ...]


def view(
    graph: NameGraph, start: str | None = None, depth: int | None = None,
    rank: int = Rank.BODY,
) -> View:
    """The view of *graph* at *rank*: the tree of the node at address
    *start* (every tree of the graph, the project, by default), down
    *depth* steps of those the view shows (``0`` the start alone, ``None``
    all of them).

    Raises ``KeyError`` for a *start* that is no node."""
    roots = _roots(graph, start, rank)
    found: list[Node] = []
    edges: list[tuple[str, str, EdgeKind]] = []

    def walk(node: Node, remaining: int | None) -> None:
        found.append(node)
        if remaining == 0:
            return
        for child in _held(graph, node.address, rank):
            parent = graph.parent_of(child.address)
            direct = parent is not None and parent.address == node.address
            edges.append((node.address, child.address, (
                EdgeKind.CONTAINS if direct
                else EdgeKind.CONTAINS_INDIRECTLY)))
            walk(child, None if remaining is None else remaining - 1)

    for root in roots:
        walk(root, depth)
    shown = {node.address for node in found}
    held = bodies(graph, shown) if rank >= Rank.BODY else {}
    top = {root.address for root in roots}
    return View(
        None,
        tuple(_view_node(node, held.get(node.address), node.address in top)
              for node in found),
        tuple(ViewEdge(source, target, kind) for source, target, kind in edges),
        tuple(_references(graph, shown, top, rank)))


def level_name(level: str | int | None) -> str:
    """The name of *level*, given as a name or as its rank (``1`` to
    ``4``, or the digit as a string); ``outline`` for ``None``.

    Raises ``ValueError``, naming the choices, for anything else."""
    names = {rank: name for name, rank in PRESETS.items()}
    if level is None:
        return next(iter(PRESETS))
    if isinstance(level, str) and level in PRESETS:
        return level
    number = int(level) if isinstance(level, str) and level.isdigit() else level
    if isinstance(number, int) and not isinstance(number, bool):
        if number in names:
            return names[number]
    raise ValueError(
        f"unknown level {level!r}: choose {', '.join(PRESETS)} "
        f"(or {', '.join(map(str, names))})")


def level_view(
    graph: NameGraph, level: str | int | None, start: str | None = None,
    depth: int | None = None,
) -> View:
    """The view of a named level, by name or rank: the preset's rank, and
    its name for the view to carry. Raises ``ValueError`` for a level that
    is not one."""
    name = level_name(level)
    return replace(view(graph, start, depth, PRESETS[name]), level=name)


def answer_node(node: Node) -> ViewNode:
    """The node as a query prints it: the view's node at ``outline``, and
    its ``file`` as well, for an answer stands on its own, with no module
    beside it to look it up in."""
    return _view_node(node, None, True)


def _roots(graph: NameGraph, start: str | None, rank: int) -> list[Node]:
    """The nodes the walk starts at: the one at *start*, or every node no
    node holds that the rank shows, the lower ranks first (each file's
    tree, then what is derived outside any)."""
    if start is not None:
        node = graph.node(start)
        if node is None:
            raise KeyError(start)
        return [node]
    found = [n for n in graph.nodes()
             if graph.parent_of(n.address) is None
             and KINDS[n.kind].rank <= rank]
    return sorted(found, key=lambda n: KINDS[n.kind].rank)


def _held(graph: NameGraph, address: str, rank: int) -> list[Node]:
    """What the view shows directly below the node at *address*, in the
    order written: each child at or below *rank*, and for each that is
    above it, what that holds in turn."""
    found: list[Node] = []
    for child in graph.children(address):
        if KINDS[child.kind].rank <= rank:
            found.append(child)
        else:
            found += _held(graph, child.address, rank)
    return sorted(found, key=lambda n: n.start_line or 0)


def _view_node(node: Node, body: str | None, is_root: bool) -> ViewNode:
    return ViewNode(
        address=node.address, kind=node.kind, name=node.name,
        mode=node.mode, declares=node.declares, value=node.value,
        file=node.file if is_root else None, start_line=node.start_line,
        body=body)


def _source(
    graph: NameGraph, address: str, shown: set[str], roots: set[str],
) -> str | None:
    """The address of the node a reference written at *address* starts at:
    the nearest node at or above it that the view shows and an ``outline``
    shows (or that is a root of the view), or ``None`` if there is none."""
    node = graph.node(address)
    while node is not None:
        if node.address in shown and (
                KINDS[node.kind].rank <= Rank.STRUCTURE
                or node.address in roots):
            return node.address
        node = graph.parent_of(node.address)
    return None


def _references(
    graph: NameGraph, shown: set[str], roots: set[str], rank: int,
) -> list[ViewEdge]:
    """The references of *graph* at *rank*, each from the node that holds
    it, merged on source, target and kind, with both ends among *shown*."""
    lines: dict[tuple[str, str, EdgeKind], set[int]] = {}
    for edge in graph.edges():
        if edge.kind == EdgeKind.CONTAINS or EDGE_RANKS[edge.kind] > rank:
            continue
        source = _source(graph, edge.source, shown, roots)
        if source is None or edge.target not in shown:
            continue
        lines.setdefault((source, edge.target, edge.kind),
                         set()).update(edge.lines)
    return [ViewEdge(source, target, kind, tuple(sorted(found)))
            for (source, target, kind), found in lines.items()]


# ── Citations ────────────────────────────────────────────────

def _citations(graph: NameGraph) -> list[Edge]:
    """The ``CITES`` edges as the view at the rank of the references has
    them: from the node an ``outline`` shows that holds the paragraph, each
    with every line it is written on."""
    return [Edge(e.source, e.target, EdgeKind.CITES, e.lines)
            for e in view(graph, rank=Rank.REFERENCES).references
            if e.kind == EdgeKind.CITES]


def cites_edges(graph: NameGraph, address: str) -> list[Edge]:
    """The ``CITES`` edges from the node at *address*, in the order first
    found, one to each node it cites (the first): those named in its
    paragraphs (a section's citations are its paragraphs'), or, for a
    block itself, in it."""
    node = graph.node(address)
    if node is None:
        return []
    if KINDS[node.kind].rank > Rank.STRUCTURE:
        edges = list(graph.edges(EdgeKind.CITES))
    else:
        edges = _citations(graph)
    found: dict[str, Edge] = {}
    for edge in edges:
        if edge.source == address and graph.node(edge.target) is not None:
            found.setdefault(edge.target, edge)
    return list(found.values())


def cited_by_edges(graph: NameGraph, address: str) -> list[Edge]:
    """The ``CITES`` edges into the node at *address*, one from each node
    that cites it (the first), in the order first found: a paragraph that
    does is given as the section that holds it."""
    found: dict[str, Edge] = {}
    for edge in _citations(graph):
        if edge.target == address and graph.node(edge.source) is not None:
            found.setdefault(edge.source, edge)
    return list(found.values())


def cites_of(graph: NameGraph, address: str) -> list[Node]:
    """The nodes that the node at *address* cites (see
    :func:`cites_edges`)."""
    return [graph.node(e.target) for e in cites_edges(graph, address)]


def cited_by(graph: NameGraph, address: str) -> list[Node]:
    """The nodes that cite the node at *address* (see
    :func:`cited_by_edges`)."""
    return [graph.node(e.source) for e in cited_by_edges(graph, address)]
