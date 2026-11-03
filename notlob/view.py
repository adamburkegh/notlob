"""The view: a start, a depth and a rank over the tree of a graph.

A view gives the nodes, the edges and the bodies at or below its rank (see
:class:`~notlob.graph.Rank`), once, for any writer to write: no writer
decides what a level holds, or knows what one is.

* **Containment.** A ``CONTAINS`` edge is always the tree's. Where the view
  hides what holds a node, it gives ``CONTAINS_INDIRECTLY`` from the
  nearest node above that it shows.
* **References.** An edge's source is the nearest node at or above where
  it is written that has the lowest rank, which an ``outline`` shows: the
  same at every rank. References merge on source, target and kind, and
  their lines join, in order, each once.
* **Ends.** An edge is in the view only if both its ends are.
* **Depth** counts the steps the view shows.

A view made from a preset (see :func:`level_view`) carries the preset's
name as its ``level``, which is for the JSON writer and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .graph import (
    EDGE_RANKS, KINDS, PRESETS, EdgeKind, NameGraph, Node, NodeKind, Rank,
)


@dataclass(frozen=True)
class ViewNode:
    """A node of a view. The names of the fields are the document's: each
    is written once, in snake_case, and a format with a convention of its
    own converts the name.

    kind        what the node is
    name        the name its address is built from, if it has one
    file        the ``.lob`` file, on the root of a file's tree only
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
    """An edge of a view: *kind* is spelled as the document spells it
    (``CONTAINS``, ``CONTAINS_INDIRECTLY``, ``USES``, ...), and *lines*
    are every line a reference is written on, in order, each once."""
    source: str
    target: str
    kind:   str
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
    nodes: list[ViewNode] = []
    tree: list[ViewEdge] = []

    def walk(node: Node, remaining: int | None) -> None:
        nodes.append(_view_node(graph, node, rank))
        if remaining == 0:
            return
        for child in _held(graph, node.address, rank):
            parent = graph.parent_of(child.address)
            kind = ("CONTAINS" if parent is not None
                    and parent.address == node.address
                    else "CONTAINS_INDIRECTLY")
            tree.append(ViewEdge(node.address, child.address, kind))
            walk(child, None if remaining is None else remaining - 1)

    for root in roots:
        walk(root, depth)
    shown = {n.address for n in nodes}
    return View(None, tuple(nodes), tuple(tree),
                tuple(_references(graph, shown, rank)))


def level_view(
    graph: NameGraph, level: str, start: str | None = None,
    depth: int | None = None,
) -> View:
    """The view of a named level: the preset's rank, and its name for the
    view to carry. Raises ``ValueError`` for a level that is not one."""
    if level not in PRESETS:
        raise ValueError(
            f"unknown level {level!r}: choose {', '.join(PRESETS)}")
    return replace(view(graph, start, depth, PRESETS[level]), level=level)


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


def _view_node(graph: NameGraph, node: Node, rank: int) -> ViewNode:
    is_root = graph.parent_of(node.address) is None
    return ViewNode(
        address=node.address, kind=node.kind, name=node.name,
        mode=node.mode, declares=node.declares, value=node.value,
        file=node.file if is_root else None, start_line=node.start_line,
        body=node.body if rank >= Rank.BODY else None)


def _lifted(graph: NameGraph, address: str) -> str | None:
    """The address of the nearest node at or above *address* that has the
    lowest rank, or ``None`` if there is none."""
    node = graph.node(address)
    while node is not None and KINDS[node.kind].rank > Rank.STRUCTURE:
        node = graph.parent_of(node.address)
    return None if node is None else node.address


def _references(
    graph: NameGraph, shown: set[str], rank: int,
) -> list[ViewEdge]:
    """The references of *graph* at *rank*, each from the node that holds
    it, merged on source, target and kind, with both ends among *shown*."""
    lines: dict[tuple[str, str, str], set[int]] = {}
    for edge in graph.edges():
        if edge.kind == EdgeKind.CONTAINS:
            continue
        if EDGE_RANKS[edge.kind.name] > rank:
            continue
        source = _lifted(graph, edge.source)
        if source not in shown or edge.target not in shown:
            continue
        lines.setdefault((source, edge.target, edge.kind.name),
                         set()).update(edge.lines)
    return [ViewEdge(source, target, kind, tuple(sorted(found)))
            for (source, target, kind), found in lines.items()]
