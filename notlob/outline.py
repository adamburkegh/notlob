"""The shape of a file, in its own words.

A line for each heading, symbol and claim, indented by what is written in
what, with the line it is written on in a column on the right; at
``index``, and under the node that holds each, a line for every
cross-reference (``uses``, ``cites``, ``imports``) and every declaration.
This is what ``notlob graph`` prints for a reader. It works on any node of
the graph: an :class:`Entry` is a line of the outline, and
:func:`render_entries` lays a list of them out.
"""

from __future__ import annotations

from typing import NamedTuple

from notlob.graph import (
    KINDS, EdgeKind, NameGraph, Node, NodeKind, parse_level, sigil_of,
)

#: The edges that are a line of the outline, at the line they are written.
_REFERENCES = (EdgeKind.USES, EdgeKind.CITES, EdgeKind.IMPORTS)


class Entry(NamedTuple):
    """A line of the outline: *words* indented *depth* steps, and the
    *line* of its file it is written on."""
    depth: int
    words:  str
    line:   int | None


def _words(node: Node, level: str) -> str | None:
    """What the line of *node* says, or ``None`` when it has none: what
    ``outline`` leaves out has no line, nor has a run of bare assertions,
    and a declaration is a line from ``index`` on. A heading, group or
    symbol says its name; a claim or a named test its sigil and then its
    name, if it has one."""
    if node.kind == NodeKind.DECLARATION:
        if level == "outline":
            return None
        return " ".join(filter(None, (f"~{node.declares}", node.value)))
    if KINDS[node.kind].hidden_at_outline:
        return None
    if KINDS[node.kind].sigil is not None:
        sigil = sigil_of(node)
        return " ".join(filter(None, (sigil, node.name))) if sigil else None
    return node.label


def _below(graph: NameGraph, address: str, level: str) -> list[Node]:
    """What is written in the node at *address* that has a line, in line
    order; what has none passes what it holds up to the node above it."""
    found: list[Node] = []
    for child in graph.children(address):
        if _words(child, level) is None:
            found += _below(graph, child.address, level)
        else:
            found.append(child)
    return sorted(found, key=lambda n: n.start_line or 0)


def _name(graph: NameGraph, address: str) -> str | None:
    """What a reference calls its target: what follows the last ``#`` of
    its address, or a module's title."""
    node = graph.node(address)
    if node is None:
        return None
    if node.kind == NodeKind.MODULE:
        return node.label
    return address.rsplit("#", 1)[-1]


def _holder(graph: NameGraph, source: str, level: str) -> Node | None:
    """The node with a line that a reference from *source* belongs to:
    *source* itself, or the nearest node above it that has one (a
    paragraph's citation is its section's)."""
    node = graph.node(source)
    while node is not None and _words(node, level) is None:
        node = graph.parent_of(node.address)
    return node


def _references(
    graph: NameGraph, level: str,
) -> dict[str, list[tuple[int, str]]]:
    """The reference lines of each node that holds some, as (line, words)
    in line order. A reference repeated in one node is one line, the
    first."""
    first: dict[tuple[str, EdgeKind, str], tuple[int, str]] = {}
    for edge in graph.edges():
        if edge.kind not in _REFERENCES or edge.start_line is None:
            continue
        name = _name(graph, edge.target)
        holder = _holder(graph, edge.source, level)
        if name is None or holder is None:
            continue
        key = (holder.address, edge.kind, edge.target)
        if key not in first or edge.start_line < first[key][0]:
            first[key] = (edge.start_line,
                          f"{edge.kind.name.lower()} {name}")
    held: dict[str, list[tuple[int, str]]] = {}
    for (address, _, _), reference in first.items():
        held.setdefault(address, []).append(reference)
    return {address: sorted(found, key=lambda r: r[0])
            for address, found in held.items()}


def outline_entries(
    graph: NameGraph, address: str, level: str | int = "outline",
) -> list[Entry]:
    """The lines of the outline of the node at *address*, at *level* (see
    :data:`notlob.graph.LEVELS`): the node, then what is written in it,
    each indented a step past what holds it, in line order. ``outline``
    is the structural lines; from ``index`` on the references and
    declarations are lines too, under the node that holds them.

    Raises ``KeyError`` for an address that is no node, and ``ValueError``
    for a level that is none of these."""
    level = parse_level(level)
    root = graph.node(address)
    if root is None:
        raise KeyError(address)
    held = _references(graph, level) if level != "outline" else {}
    entries: list[Entry] = []

    def walk(node: Node, depth: int) -> None:
        entries.append(Entry(
            depth, _words(node, level) or node.label, node.start_line))
        items: list[tuple[int, int, Node | str]] = [
            (child.start_line or 0, 0, child)
            for child in _below(graph, node.address, level)]
        items += [(line, 1, words)
                  for line, words in held.get(node.address, [])]
        for line, _, item in sorted(items, key=lambda i: i[:2]):
            if isinstance(item, str):
                entries.append(Entry(depth + 1, item, line))
            else:
                walk(item, depth + 1)

    walk(root, 0)
    return entries


def render_entries(entries: list[Entry]) -> str:
    """*entries* as lines: each indented two spaces a step, with its line
    number right aligned in a column two spaces past the longest of them."""
    if not entries:
        return ""
    texts = ["  " * e.depth + e.words for e in entries]
    width = max(map(len, texts))
    digits = max((len(str(e.line)) for e in entries if e.line is not None),
                 default=0)
    return "".join(
        f"{text.ljust(width)}  {e.line:>{digits}}\n" if e.line is not None
        else f"{text}\n"
        for text, e in zip(texts, entries))


def project_outline(
    graph: NameGraph, level: str | int = "outline",
    lone_file: str | None = None,
) -> str:
    """The outline of each module of *graph*, each under its file on a
    line alone (relative to the project root; *lone_file* for a module
    built on its own), with a blank line between."""
    return "\n".join(
        f"{module.file or lone_file or module.address}\n"
        + render_entries(outline_entries(graph, module.address, level))
        for module in graph.nodes(NodeKind.MODULE))
