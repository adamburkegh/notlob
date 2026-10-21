"""notlob.graph — Name-graph: structure, symbols, and cross-references.

Structure:        module and subheading nodes from document structure.
Symbols:          symbol nodes from code blocks via a language binding.
Cross-references: REFERENCES edges from prose ``#Label`` mentions
                  (not yet implemented).
Package graph:    IMPORTS edges from ``#References`` lob-ref declarations;
                  ``build_package()`` lives in ``notlob.project`` because
                  it requires file-system access.

Node addresses
--------------
Every node has a globally unique address computed deterministically
from its position in the package hierarchy.  The # character is the
universal separator between a module address and any named thing
within it — subheadings and symbols share the same scheme:

  Module:     title → lowercase, spaces → slashes
              "Pricing Discounts" → "pricing/discounts"

  Subheading: module_address + "#" + label  (label preserved as-is)
              "pricing/discounts#Stacking Discounts"

  Symbol:     module_address + "#" + name
              "pricing/discounts#apply_discount"

Addresses are machine identifiers; labels are the human-readable
names as written in source.  A name collision between a symbol and
a subheading (same label, same module) is an error: all named
things share one namespace per module.

This scheme is isomorphic to URI fragment addressing.

Edge vocabulary
---------------
  CONTAINS   — module → subheading          (structure)
  DEFINES    — module/subheading → symbol   (symbols)
  REFERENCES — node → node                  (cross-references; planned)
  IMPORTS    — module → module              (package graph)

Usage::

    from notlob import parse_file, from_tree
    from notlob.graph import build, enrich, NameGraph
    from notlob.bindings.python import extract_symbols

    module = from_tree(parse_file("examples/roman/numerals.lob"))
    graph  = build(module)
    enrich(graph, module, extract_symbols)

    node = graph.node("roman/numerals#to_roman")
    for sym in graph.children("roman/numerals", EdgeKind.DEFINES):
        print(sym.address)
"""

from __future__ import annotations

import fnmatch
import json
import re
import textwrap
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Iterator, NamedTuple

from .bindings import Extractor
from .model import (
    AppendixSection, BulletBlock, Claim, CodeBlock, Module, NamedTest,
    ProseBlock, Ref, ReferencesSection, Subheading, TestGroup,
    TestsSection,
)


# ── Address computation ──────────────────────────────────────

def module_address(title: str) -> str:
    """Derive a module address from its title.

    "Pricing Discounts" -> "pricing/discounts"
    "Roman Numerals"    -> "roman/numerals"
    "Pricing"           -> "pricing"
    """
    return title.lower().replace(" ", "/")


def subheading_address(module_addr: str, label: str) -> str:
    """Derive a subheading address from its module and label.

    ("pricing/discounts", "Stacking Discounts")
        -> "pricing/discounts#Stacking Discounts"
    """
    return f"{module_addr}#{label}"


def symbol_address(module_addr: str, name: str) -> str:
    """Derive a symbol address from its module and name.

    ("roman/numerals", "to_roman") -> "roman/numerals#to_roman"

    Symbols and subheadings share the # scheme; a collision between
    a symbol name and a subheading label in the same module is an
    error.
    """
    return f"{module_addr}#{name}"


def property_address(containing_addr: str, name: str) -> str:
    """Derive a named property address from its container and name.

    ("roman/numerals#Round-Trip", "commutativity")
        -> "roman/numerals#Round-Trip#commutativity"
    """
    return f"{containing_addr}#{name}"


def claim_address(containing_addr: str, kind: str, n: int) -> str:
    """Derive a claim address from its container, kind, and ordinal.

    Claims are anonymous; the ordinal counts claims of the same kind
    within the containing node (module or subheading).

    ("roman/numerals#Decoding", "example", 1)
        -> "roman/numerals#Decoding#example#1"
    ("roman/numerals", "property", 2)
        -> "roman/numerals#property#2"
    """
    return f"{containing_addr}#{kind}#{n}"


def appendix_address(module_addr: str, n: int) -> str:
    """Derive an ``#Appendix`` section's address from its module and its
    1-based position among the module's appendices.

    ("roman/numerals", 1) -> "roman/numerals#appendix#1"

    An Appendix has an optional, free-text title, so it is addressed by
    position, like a claim, which also keeps it clear of the module's
    one namespace of symbol and subheading names.
    """
    return claim_address(module_addr, "appendix", n)


# ── Node ─────────────────────────────────────────────────────

class NodeKind(Enum):
    MODULE     = auto()
    SUBHEADING = auto()
    SYMBOL     = auto()    # symbols: code-level defined name
    PROPERTY   = auto()    # symbols: named ~property claim
    EXAMPLE    = auto()    # claims: ~example block
    RUN        = auto()    # claims: ~run entry-point block
    TEST       = auto()    # claims: #Tests group, bare assertions, or ~test <name>
    EXTERNAL   = auto()    # external file declared with ~external in binding.lob
    APPENDIX   = auto()    # an #Appendix section: a body of its own, with a title


@dataclass(frozen=True)
class Node:
    """A named node in the name-graph.

    address  globally unique machine identifier (tooling-derived)
    label    human-readable name as written in source
    kind     what type of named thing this node represents
    content  optional source payload; populated by enrich() when
             present.  Keys: ``prose`` (str) and/or ``code`` (str).
             Excluded from equality and hash so two nodes with the
             same address/label/kind are considered identical
             regardless of whether content has been attached.
    """
    address: str
    label:   str
    kind:    NodeKind
    content: dict | None = field(
        default=None, hash=False, compare=False,
    )
    start_line: int | None = field(
        default=None, hash=False, compare=False,
    )

    def __repr__(self) -> str:
        return f"<{self.kind.name} {self.address!r}>"


# ── Edge ─────────────────────────────────────────────────────

class EdgeKind(Enum):
    CONTAINS      = auto()   # module → subheading
    DEFINES       = auto()   # module/subheading → symbol
    IMPORTS       = auto()   # module → module
    USES_EXTERNAL = auto()   # binding module → external file
    USES          = auto()   # symbol → symbol (statically visible reference)
    REFERENCES    = auto()   # module/subheading → any node (prose #Label mention)


@dataclass(frozen=True)
class Edge:
    source:     str             # address of the source node
    target:     str             # address of the target node
    kind:       EdgeKind
    start_line: int | None = field(default=None, hash=False, compare=False)


# ── Turtle serialisation helpers ─────────────────────────────

#: Characters that may not appear in an IRI reference, plus ``%`` (so a
#: literal percent survives a round trip). Space and control characters
#: are covered by ``ord(ch) <= 0x20``.
_IRI_ENCODE = frozenset('<>"{}|\\^`%\x7f')


def _turtle_iri(address: str) -> str:
    """*address* as a Turtle IRI reference.

    Addresses are free text (a subheading title can hold spaces, quotes,
    ``#``, ``:``), so they are made safe as a relative IRI reference:

    * characters not allowed in an IRI (and ``%``) are percent-encoded;
    * only the first ``#`` is the fragment separator, later ones are
      encoded (a fragment may not contain ``#``);
    * a ``:`` in the first path segment is encoded, or ``foo:/bar``
      would be read as scheme ``foo``.

    Non-ASCII text is kept. The exact address is also emitted as the
    ``notlob:address`` literal, so nothing is lost to the encoding.
    """
    text = "".join(
        "".join(f"%{b:02X}" for b in ch.encode("utf-8"))
        if ch in _IRI_ENCODE or ord(ch) <= 0x20 else ch
        for ch in address
    )
    head, sep, fragment = text.partition("#")
    text = head + sep + fragment.replace("#", "%23")
    first_segment = re.match(r"[^/?#]*", text).group(0)
    text = first_segment.replace(":", "%3A") + text[len(first_segment):]
    return f"<{text}>"


def _turtle_lit(s: str) -> str:
    """*s* as a one-line Turtle string literal."""
    escaped = (s.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "\\r"))
    return f'"{escaped}"'


def _turtle_long_lit(s: str) -> str:
    """*s* as a triple-quoted Turtle string literal.

    Every quote is escaped, not only a run of three: a long literal that
    ends in a quote has four in a row at its close, which is ambiguous,
    and escaping is always valid.
    """
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"""{escaped}"""'


# ── Graph ────────────────────────────────────────────────────

class AddressCollisionError(ValueError):
    """Two differently-kinded nodes claim the same address.

    Raised by :meth:`NameGraph.add_node` -- e.g. a ``##Layout``
    subheading and a ``class Layout`` symbol in the same module both
    resolve to ``mod#Layout``. All named things share one namespace
    per module, so this is a real document error, not a crash: a
    caller should catch it and report a clean ``ERROR`` line (it is a
    plain exception, with structured fields, specifically so callers
    don't need to parse the message text to do that) rather than let
    it propagate as an uncaught traceback.
    """

    def __init__(
        self,
        address:       str,
        existing_kind: "NodeKind",
        new_kind:      "NodeKind",
        existing_line: int | None,
        new_line:      int | None,
    ) -> None:
        self.address       = address
        self.existing_kind = existing_kind
        self.new_kind      = new_kind
        self.existing_line = existing_line
        self.new_line      = new_line

        def _at(kind: "NodeKind", line: int | None) -> str:
            name = kind.name.lower()
            return f"{name} (line {line})" if line is not None else name

        super().__init__(
            f"Address collision: {address!r} names both a "
            f"{_at(existing_kind, existing_line)} and a "
            f"{_at(new_kind, new_line)} -- all named things share "
            f"one namespace per module."
        )


class NameGraph:
    """A typed graph of named nodes and their relationships.

    Nodes are keyed by address; edges are stored as a list and
    also indexed by source for efficient child lookup.
    """

    def __init__(self) -> None:
        self._nodes:  dict[str, Node]        = {}
        self._edges:  list[Edge]             = []
        self._out:    dict[str, list[Edge]]  = {}

    # ── Mutation ─────────────────────────────────────────────

    def add_node(self, node: Node) -> None:
        existing = self._nodes.get(node.address)
        if existing is not None and existing.kind != node.kind:
            raise AddressCollisionError(
                node.address, existing.kind, node.kind,
                existing.start_line, node.start_line,
            )
        self._nodes[node.address] = node

    def add_edge(self, edge: Edge) -> None:
        self._edges.append(edge)
        self._out.setdefault(edge.source, []).append(edge)

    def merge(self, other: NameGraph) -> None:
        """Absorb all nodes and edges from another graph."""
        for node in other._nodes.values():
            self.add_node(node)
        for edge in other._edges:
            self.add_edge(edge)

    # ── Query ─────────────────────────────────────────────────

    def node(self, address: str) -> Node | None:
        """Return the node with this address, or None."""
        return self._nodes.get(address)

    def nodes(
        self,
        kind: NodeKind | None = None,
    ) -> Iterator[Node]:
        """Iterate over all nodes, optionally filtered by kind."""
        for node in self._nodes.values():
            if kind is None or node.kind == kind:
                yield node

    def children(
        self,
        address: str,
        kind: EdgeKind = EdgeKind.CONTAINS,
    ) -> Iterator[Node]:
        """Yield nodes directly reachable from address via kind."""
        for edge in self._out.get(address, []):
            if edge.kind == kind:
                target = self._nodes.get(edge.target)
                if target:
                    yield target

    def body(self, address: str) -> list[dict]:
        """The body items of the node at *address*, in document order.

        A module, a subheading and an ``#Appendix`` each have a body; its
        items are ``{"kind": "prose", "text", "refs", "start_line"}``,
        ``{"kind": "code", "text", "start_line"}``,
        ``{"kind": "bullets", "items", "start_line"}`` and
        ``{"kind": "claim", "address", "start_line"}`` (the claim's own
        node holds its sigil and lines). Subheadings are not body items:
        they are nodes, reached through ``CONTAINS``. Empty for an
        unknown address or a node that holds no body.
        """
        node = self._nodes.get(address)
        if node is None or not node.content:
            return []
        return list(node.content.get("body", []))

    def claims(self, module_address_: str) -> list[Node]:
        """The claim nodes (EXAMPLE, PROPERTY, RUN) of the module at
        *module_address_*, in document order. A claim's node holds its
        ``sigil`` and ``code`` (the claim's lines, dedented; leading blank
        lines kept so the first line is at ``start_line + 1``)."""
        found: list[Node] = []
        for holder in self.body_holders(module_address_):
            for entry in self.body(holder.address):
                if entry["kind"] == "claim":
                    node = self._nodes.get(entry["address"])
                    if node is not None:
                        found.append(node)
        return found

    def body_holders(self, module_address_: str) -> list[Node]:
        """The module at *module_address_* and the nodes under it that
        hold a body (its subheadings and ``#Appendix`` sections, and
        theirs), in document order. Empty for an unknown module."""
        root = self._nodes.get(module_address_)
        if root is None:
            return []
        found: list[Node] = []

        def walk(node: Node) -> None:
            found.append(node)
            for child in self.children(node.address, EdgeKind.CONTAINS):
                if child.kind in (NodeKind.SUBHEADING, NodeKind.APPENDIX):
                    walk(child)

        walk(root)
        return found

    def resolve(
        self,
        label:   str,
        context: str | None = None,
    ) -> Node | None:
        """Resolve a #label reference to a node.

        Implements the three-step resolution order from DESIGN.md:
          1. Symbol defined in the current module.
          2. Subheading of the current module.
          3. A module explicitly imported by the current module
             (requires an IMPORTS edge from *context*).

        *context* is a module address (e.g. ``"roman/numerals"``).
        When context is given, step 3 is restricted to modules
        reachable via a declared IMPORTS edge — unimported modules
        are invisible even if they exist in the same package graph.

        Without context, only a full MODULE scan is attempted
        (useful for tooling / package-level lookup; never for
        validating in-source cross-references).

        Symbols and subheadings share the ``#`` address space; a
        collision is an error at add_node time, so steps 1 and 2
        reduce to a single address lookup distinguished by NodeKind.
        """
        if context is not None:
            # Steps 1 & 2: symbol or subheading in the current module
            addr = f"{context}#{label}"
            node = self._nodes.get(addr)
            if node is not None:
                if node.kind in (NodeKind.SYMBOL, NodeKind.SUBHEADING):
                    return node
            # Step 3: explicitly imported module (IMPORTS edges)
            for edge in self._out.get(context, []):
                if edge.kind == EdgeKind.IMPORTS:
                    target = self._nodes.get(edge.target)
                    if target and target.label == label:
                        return target
        else:
            # No context: scan all MODULE nodes (tooling use only)
            for node in self._nodes.values():
                if node.label == label and node.kind == NodeKind.MODULE:
                    return node
        return None

    def search(
        self,
        pattern: str,
        kind: NodeKind | None = None,
    ) -> Iterator[Node]:
        """Yield nodes whose label matches *pattern* (fnmatch-style).

        ``*discount*`` matches any label containing "discount".
        ``apply_*`` matches any label starting with "apply_".
        Matching is case-sensitive.  Pass *kind* to restrict results.
        """
        for node in self._nodes.values():
            if kind is not None and node.kind != kind:
                continue
            if fnmatch.fnmatch(node.label, pattern):
                yield node

    def parents(
        self,
        address: str,
        kind: EdgeKind = EdgeKind.IMPORTS,
    ) -> Iterator[Node]:
        """Yield nodes that have an edge of *kind* pointing to *address*.

        The complement of :meth:`children`: where ``children`` follows
        edges forward, ``parents`` follows them in reverse.  Primarily
        useful for ``IMPORTS`` edges — finding every module that imports
        a given module.
        """
        for edge in self._edges:
            if edge.kind == kind and edge.target == address:
                source = self._nodes.get(edge.source)
                if source:
                    yield source

    # ── Serialisation ─────────────────────────────────────────

    def to_dict(self, include_content: bool = False) -> dict:
        """Serialise the graph to a plain dict.

        The returned structure conforms to the JSON Schema at
        ``notlob/schema/name_graph.json``::

            {
                "nodes": [{"address": ..., "label": ..., "kind": ...}, ...],
                "edges": [{"source": ..., "target": ..., "kind": ...}, ...]
            }

        Pass *include_content=True* to attach each node's ``content``
        dict when present.  The lean default omits content entirely,
        keeping the output suitable for structural queries and large
        packages.
        """
        nodes = []
        for node in self._nodes.values():
            d: dict = {
                "address": node.address,
                "label":   node.label,
                "kind":    node.kind.name,
            }
            if include_content and node.content is not None:
                d["content"] = node.content
            if node.start_line is not None:
                d["start_line"] = node.start_line
            nodes.append(d)
        def _edge_dict(edge: "Edge") -> dict:
            d = {"source": edge.source, "target": edge.target,
                 "kind": edge.kind.name}
            if edge.start_line is not None:
                d["start_line"] = edge.start_line
            return d

        return {
            "nodes": nodes,
            "edges": [_edge_dict(edge) for edge in self._edges
            ],
        }

    def to_json(
        self,
        indent: int = 2,
        include_content: bool = False,
    ) -> str:
        """Serialise the graph to a JSON string.

        *indent* controls pretty-printing; pass ``None`` for compact
        single-line output.  *include_content* is forwarded to
        :meth:`to_dict`.
        """
        return json.dumps(
            self.to_dict(include_content=include_content),
            indent=indent,
        )

    def to_turtle(
        self,
        base: str | None = None,
        include_content: bool = False,
    ) -> str:
        """Serialise the graph as RDF in Turtle syntax.

        The vocabulary (``notlob:``) is declared in
        ``notlob/schema/notlob.ttl`` under the informal ``urn:notlob:ns:``
        namespace. Node addresses become relative IRI references (see
        :func:`_turtle_iri`), so they resolve against wherever the
        document is loaded; pass *base* to emit an ``@base`` and put the
        project's nodes under an IRI of your own. There is no default
        base: project data does not belong in notlob's namespace.
        *include_content* attaches prose and code literals when present.

        No external dependency — Turtle is emitted as plain strings.
        """
        ns = "urn:notlob:ns:"
        lines = [f"@base <{base}> ."] if base else []
        lines += [
            f"@prefix notlob: <{ns}> .",
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
            "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
            "",
        ]

        _uri, _lit, _long_lit = _turtle_iri, _turtle_lit, _turtle_long_lit

        for node in self._nodes.values():
            uri = _uri(node.address)
            kind_class = f"notlob:{node.kind.name.capitalize()}"
            lines.append(f"{uri} a {kind_class} ;")
            lines.append(f"    rdfs:label {_lit(node.label)} ;")
            lines.append(f"    notlob:address {_lit(node.address)} ;")
            if node.start_line is not None:
                lines.append(
                    f"    notlob:startLine {node.start_line} ;"
                )
            if include_content and node.content:
                if node.content.get("prose"):
                    lines.append(
                        f"    notlob:prose {_long_lit(node.content['prose'])} ;"
                    )
                if node.content.get("code"):
                    lines.append(
                        f"    notlob:code {_long_lit(node.content['code'])} ;"
                    )
            lines[-1] = lines[-1][:-2] + "."
            lines.append("")

        for edge in self._edges:
            pred = f"notlob:{edge.kind.name.lower()}"
            lines.append(
                f"{_uri(edge.source)} {pred} {_uri(edge.target)} ."
            )

        lines.append("")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._nodes)

    def __repr__(self) -> str:
        return (
            f"<NameGraph {len(self._nodes)} nodes,"
            f" {len(self._edges)} edges>"
        )


# ── Content helpers ──────────────────────────────────────────

def _prose_text(body: list) -> str | None:
    """Concatenate ProseBlock and BulletBlock text from direct *body* items.

    Inline refs are re-serialised with their sigil (``#Label``).
    Bullet items are included as plain text so symbol search covers them.
    Subheadings in *body* are ignored — they carry their own content.
    Blocks are separated by a blank line, so one paragraph's last
    sentence is not glued to the next paragraph's first.
    """
    blocks: list[str] = []
    for item in body:
        if isinstance(item, ProseBlock):
            parts: list[str] = []
            for span in item.spans:
                if isinstance(span, str):
                    parts.append(span)
                else:
                    parts.append(
                        ("##" if span.sub else "#") + span.label
                    )
            blocks.append("".join(parts))
        elif isinstance(item, BulletBlock):
            blocks.append("\n".join(item.items))
    text = "\n\n".join(b.strip() for b in blocks if b.strip())
    return text or None


def _bullet_block_count(body: list) -> int:
    """Count BulletBlock items in *body* (subheadings excluded)."""
    return sum(1 for item in body if isinstance(item, BulletBlock))


def _code_text(body: list) -> str | None:
    """Concatenate the dedented CodeBlock text from *body*.

    Multiple blocks are joined with a blank line between them.
    Subheadings in *body* are ignored — they carry their own content.
    Claims are not included: each is a node of its own, and appears in
    the node's body in its place.
    """
    blocks: list[str] = []
    for item in body:
        if isinstance(item, CodeBlock):
            blocks.append(textwrap.dedent("\n".join(item.lines)))
    return "\n\n".join(blocks) if blocks else None


def _node_content(
    prose: str | None,
    code: str | None,
    bullet_block_count: int = 0,
    body: list[dict] | None = None,
    imports: list[dict] | None = None,
) -> dict | None:
    """Build a content dict.

    *prose* and *code* are the node's prose and code concatenated (what
    checks and ``query content`` have always read); *body* is its body
    items in order, and *imports* a module's ``#References`` lines.
    """
    d: dict = {}
    if prose:
        d["prose"] = prose
    if code:
        d["code"] = code
    if bullet_block_count:
        d["bullet_block_count"] = bullet_block_count
    if body:
        d["body"] = body
    if imports:
        d["imports"] = imports
    return d or None


# ── Structure ────────────────────────────────────────────────
#
# A module, a subheading and an #Appendix each have a body (the grammar's
# `body`, `_sub_item*` and `body_item*`), and each is a node. A node's
# body is held on the node as an ordered list of body items (prose, code,
# bullets, claims) so the graph is a complete index of the document: see
# DESIGN.md, "The name-graph is complete". `build` is the only place the
# parse tree is walked to find bodies; everything else reads the graph.

class _BodyHolder(NamedTuple):
    """A node that holds a body, and the body items directly in it
    (subheadings are nodes of their own and are not repeated here)."""
    address:    str
    kind:       NodeKind
    label:      str
    parent:     str | None
    start_line: int | None
    items:      list


def _body_holders(module: Module) -> list[_BodyHolder]:
    """The nodes of *module* that hold a body, in document order: the
    module, its subheadings, then each ``#Appendix`` (numbered from 1 in
    order of appearance) and its subheadings."""
    mod_addr = module_address(module.title)

    def direct(body: list) -> list:
        return [i for i in body if not isinstance(i, Subheading)]

    def subheadings(body: list, parent: str) -> list[_BodyHolder]:
        return [
            _BodyHolder(
                subheading_address(mod_addr, item.title),
                NodeKind.SUBHEADING, item.title, parent, item.start_line,
                list(item.body),
            )
            for item in body if isinstance(item, Subheading)
        ]

    holders = [_BodyHolder(
        mod_addr, NodeKind.MODULE, module.title, None, module.start_line,
        direct(module.body),
    )]
    holders += subheadings(module.body, mod_addr)

    n = 0
    sections = module.post_text.sections if module.post_text else []
    for section in sections:
        if not isinstance(section, AppendixSection):
            continue
        n += 1
        addr = appendix_address(mod_addr, n)
        holders.append(_BodyHolder(
            addr, NodeKind.APPENDIX, section.title.lstrip("#").strip(),
            mod_addr, section.start_line, direct(section.body),
        ))
        holders += subheadings(section.body, addr)
    return holders


def claims_of(module: Module) -> list[Node]:
    """The claim nodes of *module*, in document order, from the graph's
    structural layer (:func:`build`), which needs no language binding.
    What the claim collectors, ``notlob run`` and ``collect_run_bodies``
    read: addresses and numbering have one owner, the graph."""
    return build(module).claims(module_address(module.title))


def claim_lines(claim: Node) -> list[str]:
    """The lines of a claim node's source (empty if it has none). Line
    ``i`` is at source line ``claim.start_line + 1 + i``."""
    return (claim.content or {}).get("code", "").splitlines()


def _claim_identity(
    claim: Claim, holder_addr: str, counts: dict[str, int],
) -> tuple[str, str, NodeKind]:
    """``(address, label, kind)`` of *claim* in the body at *holder_addr*.
    *counts* numbers the holder's claims of each kind as they go by."""
    if claim.sigil == "~example":
        counts["example"] += 1
        n = counts["example"]
        return (claim_address(holder_addr, "example", n),
                f"example#{n}", NodeKind.EXAMPLE)
    if claim.sigil.startswith("~run"):          # ~run, ~run on-load, ...
        counts["run"] += 1
        n = counts["run"]
        return (claim_address(holder_addr, "run", n),
                f"run#{n}", NodeKind.RUN)
    counts["property"] += 1
    n = counts["property"]
    parts = claim.sigil.split(None, 1)
    if len(parts) > 1:
        name = parts[1].strip()
        return property_address(holder_addr, name), name, NodeKind.PROPERTY
    return (claim_address(holder_addr, "property", n),
            f"property#{n}", NodeKind.PROPERTY)


def _prose_entry(block: ProseBlock) -> dict:
    text = "".join(
        span if isinstance(span, str)
        else ("##" if span.sub else "#") + span.label
        for span in block.spans
    )
    refs = [
        {"label": s.label, "sub": s.sub, "start_line": s.start_line}
        for s in block.spans if isinstance(s, Ref)
    ]
    return {"kind": "prose", "text": text, "refs": refs,
            "start_line": block.start_line}


def _body_entries(
    items: list, holder_addr: str,
) -> tuple[list[dict], list[tuple[Claim, str, str, NodeKind]]]:
    """The body items of one node as graph entries, in order, and the
    claims among them with their identities (to become claim nodes)."""
    entries: list[dict] = []
    claims:  list[tuple[Claim, str, str, NodeKind]] = []
    counts = {"example": 0, "run": 0, "property": 0}
    for item in items:
        if isinstance(item, ProseBlock):
            entries.append(_prose_entry(item))
        elif isinstance(item, CodeBlock):
            entries.append({
                "kind": "code",
                "text": textwrap.dedent("\n".join(item.lines)),
                "start_line": item.start_line,
            })
        elif isinstance(item, BulletBlock):
            entries.append({"kind": "bullets", "items": list(item.items),
                            "start_line": item.start_line})
        elif isinstance(item, Claim):
            addr, label, kind = _claim_identity(item, holder_addr, counts)
            entries.append({"kind": "claim", "address": addr,
                            "start_line": item.start_line})
            claims.append((item, addr, label, kind))
    return entries, claims


def _module_imports(module: Module) -> list[dict]:
    """The module's ``#References`` lines, one entry per non-blank line:
    a lob-ref (``#Title``) or a language import, with its source line."""
    if module.post_text is None:
        return []
    for section in module.post_text.sections:
        if isinstance(section, ReferencesSection):
            lines = section.line_numbers
            return [
                {"text": line.strip(),
                 "lob_ref": line.strip().startswith("#"),
                 "start_line": lines[i] if i < len(lines) else None}
                for i, line in enumerate(section.lines) if line.strip()
            ]
    return []


def build(module: Module) -> NameGraph:
    """Build a structural NameGraph from a Module.

    Creates a node for each node that holds a body: the module, each
    subheading, and each ``#Appendix``, with CONTAINS edges from a node
    to those inside it (the module to its subheadings and Appendices, an
    Appendix to its subheadings); and a node for every claim, defined by
    the node whose body it is written in and numbered within it
    (``mod#example#1``, ``mod#Sub#example#1``,
    ``mod#appendix#1#example#1``). Also creates TEST nodes for #Tests
    groups. Needs no language binding.

    Each body-holding node carries its prose and code (concatenated, as
    ``prose`` and ``code``) and its body items in order (``body``); the
    module node also carries its ``#References`` lines (``imports``). See
    :meth:`NameGraph.body`.
    """
    graph = NameGraph()
    addr  = module_address(module.title)

    for holder in _body_holders(module):
        entries, claims = _body_entries(holder.items, holder.address)
        graph.add_node(Node(
            address=holder.address,
            label=holder.label,
            kind=holder.kind,
            content=_node_content(
                _prose_text(holder.items),
                _code_text(holder.items),
                _bullet_block_count(holder.items),
                body=entries,
                imports=(_module_imports(module)
                         if holder.kind == NodeKind.MODULE else None),
            ),
            start_line=holder.start_line,
        ))
        if holder.parent is not None:
            graph.add_edge(Edge(
                source=holder.parent,
                target=holder.address,
                kind=EdgeKind.CONTAINS,
            ))
        for claim, claim_addr, label, kind in claims:
            code = textwrap.dedent("\n".join(claim.lines)).rstrip()
            content = {"sigil": claim.sigil}
            if code:
                content["code"] = code
            graph.add_node(Node(
                address=claim_addr,
                label=label,
                kind=kind,
                content=content,
                start_line=claim.start_line,
            ))
            graph.add_edge(Edge(
                source=holder.address,
                target=claim_addr,
                kind=EdgeKind.DEFINES,
            ))

    _add_tests(graph, module, addr)

    return graph


def _assertion_source(lines: list[str]) -> str:
    """The source of a block of ``#Tests`` assertion lines, dedented as a
    whole: stripping first would leave the first line unindented and the
    rest indented, which no language parses, so every consumer of the
    node's code (call extraction, the ``USES`` edges) saw nothing."""
    return textwrap.dedent("\n".join(lines)).strip()


def _add_named_tests(
    graph: NameGraph,
    items: list,
    containing_addr: str,
) -> None:
    """Register each NamedTest in *items* as its own TEST node.

    One address per ~test block (`containing_addr#name`), matching
    ~example's own addressing: every assertion line inside the block
    shares that one address, distinguished by source line, not by a
    per-line ordinal suffix.
    """
    for item in items:
        if not isinstance(item, NamedTest):
            continue
        addr = property_address(containing_addr, item.name)
        source = _assertion_source(item.lines)
        graph.add_node(Node(
            address=addr,
            label=item.name,
            kind=NodeKind.TEST,
            content=_node_content(None, source or None),
            start_line=item.start_line,
        ))
        graph.add_edge(Edge(
            source=containing_addr,
            target=addr,
            kind=EdgeKind.DEFINES,
        ))


def _add_tests(
    graph:  NameGraph,
    module: Module,
    mod_addr: str,
) -> None:
    """Register #Tests groups (and bare assertions) as TEST nodes."""
    if module.post_text is None:
        return
    tests_section = next(
        (s for s in module.post_text.sections
         if isinstance(s, TestsSection)),
        None,
    )
    if tests_section is None:
        return

    tests_addr = f"{mod_addr}#Tests"
    has_bare = False
    for item in tests_section.items:
        if isinstance(item, str):
            has_bare = True
        elif isinstance(item, TestGroup):
            group_addr = f"{tests_addr}#{item.title}"
            bare_lines = [i for i in item.items if isinstance(i, str)]
            source = _assertion_source(bare_lines)
            graph.add_node(Node(
                address=group_addr,
                label=item.title,
                kind=NodeKind.TEST,
                content=_node_content(None, source or None),
                start_line=item.start_line,
            ))
            graph.add_edge(Edge(
                source=mod_addr,
                target=group_addr,
                kind=EdgeKind.DEFINES,
            ))
            _add_named_tests(graph, item.items, group_addr)
        # ProseBlock items are commentary, not addressable nodes.

    if has_bare:
        bare_lines = [
            item for item in tests_section.items
            if isinstance(item, str)
        ]
        source = _assertion_source(bare_lines)
        bare_start = None
        if tests_section.line_offsets:
            first_bare_idx = next(
                (i for i, item in enumerate(tests_section.items)
                 if isinstance(item, str)), None,
            )
            if first_bare_idx is not None:
                bare_start = tests_section.line_offsets.get(first_bare_idx)
        graph.add_node(Node(
            address=tests_addr,
            label="Tests",
            kind=NodeKind.TEST,
            content=_node_content(None, source or None),
            start_line=bare_start,
        ))
        graph.add_edge(Edge(
            source=mod_addr,
            target=tests_addr,
            kind=EdgeKind.DEFINES,
        ))


# ── Symbol enrichment ────────────────────────────────────────

def enrich(
    graph:     NameGraph,
    module:    Module,
    extractor: Extractor,
) -> None:
    """Enrich a structural graph with symbol nodes.

    Reads the graph, not the parse tree: for each node of the module that
    holds a body (the module, its subheadings, each ``#Appendix`` and
    its subheadings) it extracts symbols from each code body item using
    the provided language-specific extractor, and from each ``~property``
    claim. Symbols defined in a body get a DEFINES edge from the node
    that holds it. (The claim nodes themselves are made by
    :func:`build`; they need no language binding.)

    The symbol's address is always module-scoped:
        roman/numerals#from_roman
    even when defined inside ##Decoding or an Appendix.  The DEFINES edge
    records the definition site.

    Raises ValueError if a symbol name collides with an existing
    subheading label in the same module.
    """
    mod_addr = module_address(module.title)

    for holder in graph.body_holders(mod_addr):
        for entry in graph.body(holder.address):
            if entry["kind"] == "code":
                _add_symbols(
                    graph, entry["text"].splitlines(), entry["start_line"],
                    mod_addr, holder.address, extractor,
                )
            elif entry["kind"] == "claim":
                claim = graph.node(entry["address"])
                if claim is not None and claim.kind == NodeKind.PROPERTY:
                    _add_property_symbols(graph, claim, extractor)


def add_references_edges(graph: NameGraph) -> None:
    """Populate REFERENCES edges from prose ``#Label`` cross-references.

    Reads the graph: for every module in it, the prose body items of
    each node that holds a body carry their references as data
    (``label``, ``sub``, ``start_line``), and each is resolved against
    the graph.  Successfully resolved references become
    ``EdgeKind.REFERENCES`` edges from the node that holds the prose
    (MODULE, SUBHEADING or APPENDIX) to the resolved target node.

    *start_line* on each edge is the reference's source line.

    Must be called after all ``enrich()`` and IMPORTS passes so that
    ``graph.resolve()`` has the full import context available.
    """
    seen: set[tuple[str, str]] = set()

    for module_node in list(graph.nodes(kind=NodeKind.MODULE)):
        mod_addr = module_node.address
        for holder in graph.body_holders(mod_addr):
            for entry in graph.body(holder.address):
                if entry["kind"] != "prose":
                    continue
                for ref in entry["refs"]:
                    target = graph.resolve(ref["label"], context=mod_addr)
                    if target is None:
                        continue
                    key = (holder.address, target.address)
                    if key not in seen:
                        graph.add_edge(Edge(
                            source=holder.address,
                            target=target.address,
                            kind=EdgeKind.REFERENCES,
                            start_line=ref["start_line"],
                        ))
                        seen.add(key)


def add_uses_edges(
    graph:          NameGraph,
    call_extractor: Callable[[str], list[tuple[str, int]]],
) -> None:
    """Populate USES edges from statically visible symbol references.

    Builds a name → address index from all SYMBOL nodes, then for each
    SYMBOL node whose content carries source text, calls *call_extractor*
    and adds a ``EdgeKind.USES`` edge for every returned name that resolves
    to a known symbol address.

    Each edge carries ``start_line`` — the absolute .lob file line of the
    first call site, computed as ``symbol.start_line + (source_line - 1)``.
    When ``symbol.start_line`` is None the field is omitted.

    Both intra-module and cross-module references are handled identically:
    the lookup is name-based across the whole graph.  Unresolved names
    (builtins, parameters, dynamic calls) produce no edge and no error.

    Must be called after all ``enrich()`` passes so the full symbol index
    is available.
    """
    # Build name → [address] index over all known symbols.
    name_index: dict[str, list[str]] = {}
    for node in graph.nodes(kind=NodeKind.SYMBOL):
        name_index.setdefault(node.label, []).append(node.address)

    # first_call: (source_addr, target_addr) → earliest source-relative line
    first_call: dict[tuple[str, str], int] = {}
    for node in (
        *graph.nodes(kind=NodeKind.SYMBOL),
        *graph.nodes(kind=NodeKind.RUN),
        *graph.nodes(kind=NodeKind.TEST),
        *graph.nodes(kind=NodeKind.EXAMPLE),
        *graph.nodes(kind=NodeKind.PROPERTY),
    ):
        source = (node.content or {}).get("code")
        if not source:
            continue
        for ref_name, src_line in call_extractor(source):
            for target_addr in name_index.get(ref_name, []):
                key = (node.address, target_addr)
                if key not in first_call or src_line < first_call[key]:
                    first_call[key] = src_line

    for (src_addr, tgt_addr), src_line in first_call.items():
        src_node = graph.node(src_addr)
        abs_line: int | None = None
        if src_node is not None and src_node.start_line is not None:
            abs_line = src_node.start_line + (src_line - 1)
        graph.add_edge(Edge(
            source=src_addr,
            target=tgt_addr,
            kind=EdgeKind.USES,
            start_line=abs_line,
        ))


def _add_symbols(
    graph:           NameGraph,
    lines:           list[str],
    start_line:      int | None,
    mod_addr:        str,
    containing_addr: str,
    extractor:       Extractor,
) -> None:
    """Symbol nodes for the code in *lines* (a code body item's text),
    defined by the node at *containing_addr*."""
    for info in extractor(lines):
        addr = symbol_address(mod_addr, info.name)
        graph.add_node(Node(
            address=addr,
            label=info.name,
            kind=NodeKind.SYMBOL,
            content=_node_content(None, info.source),
            start_line=start_line,
        ))
        graph.add_edge(Edge(
            source=containing_addr,
            target=addr,
            kind=EdgeKind.DEFINES,
        ))


def _add_property_symbols(
    graph:     NameGraph,
    prop:      Node,
    extractor: Extractor,
) -> None:
    """The named functions defined inside a ``~property`` claim become
    SYMBOL nodes under the property node (``_``, the anonymous witness,
    is skipped). The property node itself is made by :func:`build`."""
    code = (prop.content or {}).get("code", "")
    for info in extractor(code.splitlines()):
        if info.name == '_':
            continue
        sym_addr = f"{prop.address}#{info.name}"
        graph.add_node(Node(
            address=sym_addr,
            label=info.name,
            kind=NodeKind.SYMBOL,
            content=_node_content(None, info.source),
            start_line=prop.start_line,
        ))
        graph.add_edge(Edge(
            source=prop.address,
            target=sym_addr,
            kind=EdgeKind.DEFINES,
        ))


# ── Cross-reference validation ────────────────────────────────

@dataclass(frozen=True)
class RefError:
    """An unresolved inline cross-reference in prose.

    *location* is the address of the containing node (module or
    subheading).  *ref* is the ``Ref`` that could not be resolved.
    """
    location: str
    ref:      Ref

    def __str__(self) -> str:
        sigil = "##" if self.ref.sub else "#"
        return (
            f"{self.location}: "
            f"unresolved reference {sigil}{self.ref.label}"
        )


def validate_refs(
    graph:  NameGraph,
    module: Module,
) -> list[RefError]:
    """Return a list of unresolved prose cross-references in *module*.

    Reads the prose body items of every node of the module that holds a
    body (the module, its subheadings, and any ``#Appendix`` with its
    subheadings) from *graph*, and calls :meth:`NameGraph.resolve` on
    each reference.

    ``#Label`` references are validated via the full three-step
    resolution order.  ``##Label`` references are validated against
    subheadings of the current module only.

    An unresolved reference is a first-class error; the returned list
    is empty when all references resolve. A :class:`RefError`'s
    ``location`` is the address of the node whose prose holds it.
    """
    mod_addr = module_address(module.title)
    errors: list[RefError] = []
    for holder in graph.body_holders(mod_addr):
        for entry in graph.body(holder.address):
            if entry["kind"] != "prose":
                continue
            for data in entry["refs"]:
                ref = Ref(
                    label=data["label"], sub=data["sub"],
                    start_line=data["start_line"],
                )
                if not _resolves(graph, ref, mod_addr):
                    errors.append(RefError(location=holder.address, ref=ref))
    return errors


def _resolves(graph: NameGraph, ref: Ref, mod_addr: str) -> bool:
    """Return True if *ref* resolves against *graph* in *mod_addr*."""
    if ref.sub:
        # ##Label: only a subheading of the current module
        node = graph.node(f"{mod_addr}#{ref.label}")
        return node is not None and node.kind == NodeKind.SUBHEADING
    return graph.resolve(ref.label, context=mod_addr) is not None
