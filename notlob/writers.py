"""The writers of a view: JSON, Turtle and text.

Each takes a :class:`~notlob.view.View` and nothing else, and writes what
it holds: it never asks the graph, a kind's rank or what a level is. What
a view holds is decided once, in :mod:`notlob.view`.

* **JSON** is the document of ``schema/name_graph_next.json``.
* **Turtle** gives a node's kind as its class and its other fields as
  literals, named in camelCase from the JSON's. Every edge is a triple with
  its kind, in camelCase, for the predicate; an edge with lines also has an
  ``rdf:Statement`` about that triple, which carries them as
  ``notlob:lines``, one value a line (RDF 1.1 reification).
* **Text** is for a reader: each file's path on a line alone and its lines
  under it, a blank line between files. A line's words are on the left,
  indented two spaces a step, and its line numbers right aligned in a
  column. Where the view has bodies, a file is its bodies, each at its
  line.
"""

from __future__ import annotations

import json
from dataclasses import fields

from .graph import (
    DOCUMENT_VERSION, KINDS, NodeKind, _turtle_iri, _turtle_lit,
    _turtle_long_lit, turtle_class_name,
)
from .view import View, ViewEdge, ViewNode

#: The namespace of the vocabulary, declared in ``schema/notlob.ttl``.
_NAMESPACE = "urn:notlob:ns:"


# ── JSON ─────────────────────────────────────────────────────

def write_json(view: View) -> str:
    """*view* as the JSON document."""
    doc: dict = {"version": DOCUMENT_VERSION}
    if view.level is not None:
        doc["level"] = view.level
    doc["nodes"] = [_json_node(node) for node in view.nodes]
    doc["edges"] = [_json_edge(edge) for edge in (*view.tree,
                                                  *view.references)]
    return json.dumps(doc, indent=2, ensure_ascii=False)


def _json_node(node: ViewNode) -> dict:
    found = {f.name: getattr(node, f.name) for f in fields(ViewNode)}
    return {name: value.name if isinstance(value, NodeKind) else value
            for name, value in found.items() if value is not None}


def _json_edge(edge: ViewEdge) -> dict:
    found = {"source": edge.source, "target": edge.target,
             "kind": edge.kind}
    if edge.lines:
        found["lines"] = list(edge.lines)
    return found


# ── Turtle ───────────────────────────────────────────────────

def _camel(word: str) -> str:
    """A snake_case or UPPER_SNAKE word in camelCase."""
    first, *rest = word.lower().split("_")
    return first + "".join(part.title() for part in rest)


def write_turtle(view: View) -> str:
    """*view* as RDF in Turtle syntax. Node addresses become relative IRI
    references (see ``notlob.graph._turtle_iri``); the exact address is
    also the ``notlob:address`` literal."""
    out = [f"@prefix notlob: <{_NAMESPACE}> .",
           "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
           ""]
    for node in view.nodes:
        out += _turtle_node(node)
        out.append("")
    for edge in (*view.tree, *view.references):
        subject, predicate = _turtle_iri(edge.source), (
            f"notlob:{_camel(edge.kind)}")
        target = _turtle_iri(edge.target)
        out.append(f"{subject} {predicate} {target} .")
        if edge.lines:
            lines = ", ".join(map(str, edge.lines))
            out.append(f"[] a rdf:Statement ; rdf:subject {subject} ; "
                       f"rdf:predicate {predicate} ; rdf:object {target} ; "
                       f"notlob:lines {lines} .")
    out.append("")
    return "\n".join(out)


def _turtle_node(node: ViewNode) -> list[str]:
    parts = [f"a notlob:{turtle_class_name(node.kind)}"]
    for f in fields(ViewNode):
        value = getattr(node, f.name)
        if f.name == "kind" or value is None:
            continue
        parts.append(f"notlob:{_camel(f.name)} {_turtle_value(value)}")
    head = f"{_turtle_iri(node.address)} {parts[0]} ;"
    return [head] + [f"    {p} ;" for p in parts[1:-1]] + [
        f"    {parts[-1]} ."]


def _turtle_value(value: str | int) -> str:
    if isinstance(value, int):
        return str(value)
    return _turtle_long_lit(value) if "\n" in value else _turtle_lit(value)


# ── Text ─────────────────────────────────────────────────────

def write_text(view: View) -> str:
    """*view* as text for a reader: each file under its path, a blank line
    between files."""
    children: dict[str, list[str]] = {}
    for edge in view.tree:
        children.setdefault(edge.source, []).append(edge.target)
    held: dict[str, list[ViewEdge]] = {}
    for edge in view.references:
        held.setdefault(edge.source, []).append(edge)
    nodes = {node.address: node for node in view.nodes}
    with_bodies = any(node.body is not None for node in view.nodes)

    def walk(node: ViewNode, depth: int, rows: list) -> None:
        where = "" if node.start_line is None else str(node.start_line)
        rows.append((depth, _words(node), where))
        items = [(nodes[a].start_line or 0, 0, nodes[a])
                 for a in children.get(node.address, [])]
        items += [(edge.lines[0] if edge.lines else 0, 1, edge)
                  for edge in held.get(node.address, [])]
        for _, _, item in sorted(items, key=lambda i: i[:2]):
            if isinstance(item, ViewEdge):
                words = f"{_verb(item.kind)} {_target(nodes[item.target])}"
                rows.append((depth + 1, words,
                             ", ".join(map(str, item.lines))))
            else:
                walk(item, depth + 1, rows)

    def below(node: ViewNode) -> list[ViewNode]:
        found = [node]
        for address in children.get(node.address, []):
            found += below(nodes[address])
        return found

    blocks = []
    for node in view.nodes:
        if node.file is None:
            continue
        if with_bodies:
            body = _file_lines(below(node))
        else:
            rows: list = []
            walk(node, 0, rows)
            body = _laid_out(rows)
        blocks.append(f"{node.file}\n{body}")
    return "\n".join(blocks)


def _words(node: ViewNode) -> str:
    """What the line of *node* says: a claim or test its sigil and its name,
    a declaration what it declares, any other node its name, and one with
    only a positional address the end of it (``prose#1``)."""
    sigil = KINDS[node.kind].sigil
    if sigil is not None:
        return " ".join(filter(None, (sigil, node.name)))
    if node.declares is not None:
        return " ".join(filter(None, (f"~{node.declares}", node.value)))
    if node.name is not None:
        return node.name
    parts = node.address.split("#")
    return "#".join(parts[-2:]) if parts[-1].isdigit() else parts[-1]


def _target(node: ViewNode) -> str:
    """What a reference calls the node it names."""
    return node.name if node.name is not None else _words(node)


def _verb(kind: str) -> str:
    """The word a reference says: the first of its kind's (``uses`` for
    ``USES_EXTERNAL``)."""
    return kind.lower().split("_")[0]


def _laid_out(rows: list[tuple[int, str, str]]) -> str:
    """*rows* as lines: each indented two spaces a step, with its numbers
    right aligned in a column two spaces past the longest of them."""
    texts = ["  " * depth + words for depth, words, _ in rows]
    width = max(map(len, texts))
    digits = max(len(where) for _, _, where in rows)
    return "".join(
        f"{text.ljust(width)}  {where:>{digits}}\n" if where
        else f"{text}\n"
        for text, (_, _, where) in zip(texts, rows))


def _file_lines(nodes: list[ViewNode]) -> str:
    """The bodies of *nodes*, each at its line, as the file they are
    from: the lines between them are blank."""
    placed: dict[int, str] = {}
    for node in nodes:
        if node.body is None or node.start_line is None:
            continue
        for number, text in enumerate(node.body.split("\n"),
                                      node.start_line):
            placed[number] = text
    if not placed:
        return ""
    return "".join(f"{placed.get(number, '')}\n"
                   for number in range(1, max(placed) + 1))
