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
import textwrap
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Iterator

from .bindings import Extractor
from .model import (
    AppendixSection, Claim, CodeBlock, Module,
    ProseBlock, Ref, Subheading,
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


# ── Node ─────────────────────────────────────────────────────

class NodeKind(Enum):
    MODULE     = auto()
    SUBHEADING = auto()
    SYMBOL     = auto()    # symbols: code-level defined name
    PROPERTY   = auto()    # symbols: named ~property claim


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

    def __repr__(self) -> str:
        return f"<{self.kind.name} {self.address!r}>"


# ── Edge ─────────────────────────────────────────────────────

class EdgeKind(Enum):
    CONTAINS = auto()   # module → subheading
    DEFINES  = auto()   # module/subheading → symbol
    IMPORTS  = auto()   # module → module


@dataclass(frozen=True)
class Edge:
    source: str       # address of the source node
    target: str       # address of the target node
    kind:   EdgeKind


# ── Graph ────────────────────────────────────────────────────

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
            raise ValueError(
                f"Address collision: {node.address!r} already "
                f"registered as {existing.kind.name}, "
                f"cannot add as {node.kind.name}. "
                f"All named things share one namespace per module."
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
            nodes.append(d)
        return {
            "nodes": nodes,
            "edges": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "kind":   edge.kind.name,
                }
                for edge in self._edges
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

    def __len__(self) -> int:
        return len(self._nodes)

    def __repr__(self) -> str:
        return (
            f"<NameGraph {len(self._nodes)} nodes,"
            f" {len(self._edges)} edges>"
        )


# ── Content helpers ──────────────────────────────────────────

def _prose_text(body: list) -> str | None:
    """Concatenate ProseBlock text from direct *body* items.

    Inline refs are re-serialised with their sigil (``#Label``).
    Subheadings in *body* are ignored — they carry their own content.
    """
    parts: list[str] = []
    for item in body:
        if isinstance(item, ProseBlock):
            for span in item.spans:
                if isinstance(span, str):
                    parts.append(span)
                else:
                    parts.append(
                        ("##" if span.sub else "#") + span.label
                    )
    text = "".join(parts).strip()
    return text or None


def _code_text(body: list) -> str | None:
    """Concatenate dedented CodeBlock text from direct *body* items.

    Multiple blocks are joined with a blank line between them.
    Subheadings in *body* are ignored — they carry their own content.
    """
    blocks = [
        textwrap.dedent("\n".join(item.lines))
        for item in body
        if isinstance(item, CodeBlock)
    ]
    return "\n\n".join(blocks) if blocks else None


def _node_content(prose: str | None, code: str | None) -> dict | None:
    """Build a content dict from *prose* and *code*, or return None."""
    d: dict[str, str] = {}
    if prose:
        d["prose"] = prose
    if code:
        d["code"] = code
    return d or None


# ── Structure ────────────────────────────────────────────────

def build(module: Module) -> NameGraph:
    """Build a structural NameGraph from a Module.

    Creates a node for the module and one for each subheading,
    with CONTAINS edges from the module to its subheadings.
    Content (prose and module-level code) is attached to each node.
    """
    graph = NameGraph()
    addr  = module_address(module.title)

    graph.add_node(Node(
        address=addr,
        label=module.title,
        kind=NodeKind.MODULE,
        content=_node_content(
            _prose_text(module.body),
            _code_text(module.body),
        ),
    ))

    for item in module.body:
        if isinstance(item, Subheading):
            _add_subheading(graph, addr, item)

    return graph


def _add_subheading(
    graph:       NameGraph,
    module_addr: str,
    sub:         Subheading,
) -> None:
    sub_addr = subheading_address(module_addr, sub.title)
    graph.add_node(Node(
        address=sub_addr,
        label=sub.title,
        kind=NodeKind.SUBHEADING,
        content=_node_content(
            _prose_text(sub.body),
            _code_text(sub.body),
        ),
    ))
    graph.add_edge(Edge(
        source=module_addr,
        target=sub_addr,
        kind=EdgeKind.CONTAINS,
    ))


# ── Symbol enrichment ────────────────────────────────────────

def enrich(
    graph:     NameGraph,
    module:    Module,
    extractor: Extractor,
) -> None:
    """Enrich a structural graph with symbol nodes.

    Walks the module body and extracts symbols from each code block
    using the provided language-specific extractor.  Symbols defined
    in a module-level code block get a DEFINES edge from the module
    node; those inside a subheading get one from the subheading node.

    The symbol's address is always module-scoped:
        roman/numerals#from_roman
    even when defined inside ##Decoding.  The DEFINES edge records
    the definition site.

    Raises ValueError if a symbol name collides with an existing
    subheading label in the same module.
    """
    mod_addr = module_address(module.title)

    for item in module.body:
        if isinstance(item, CodeBlock):
            _add_symbols(graph, item, mod_addr, mod_addr, extractor)
        elif isinstance(item, Claim):
            _add_named_property(graph, item, mod_addr, extractor)
        elif isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            for sub_item in item.body:
                if isinstance(sub_item, CodeBlock):
                    _add_symbols(
                        graph, sub_item,
                        mod_addr, sub_addr,
                        extractor,
                    )
                elif isinstance(sub_item, Claim):
                    _add_named_property(
                        graph, sub_item, sub_addr, extractor,
                    )


def _add_symbols(
    graph:          NameGraph,
    block:          CodeBlock,
    mod_addr:       str,
    containing_addr: str,
    extractor:      Extractor,
) -> None:
    for info in extractor(block.lines):
        addr = symbol_address(mod_addr, info.name)
        graph.add_node(Node(
            address=addr,
            label=info.name,
            kind=NodeKind.SYMBOL,
            content=_node_content(None, info.source),
        ))
        graph.add_edge(Edge(
            source=containing_addr,
            target=addr,
            kind=EdgeKind.DEFINES,
        ))


def _add_named_property(
    graph:           NameGraph,
    claim:           Claim,
    containing_addr: str,
    extractor:       Extractor,
) -> None:
    """Register a named ~property claim and its non-_ symbols.

    Unnamed ~property claims (no sigil parameter) are silently ignored
    here; the runner addresses them by ordinal at execution time.
    """
    parts = claim.sigil.split(None, 1)
    if len(parts) < 2:
        return  # unnamed — no property node

    name = parts[1].strip()
    prop_addr = property_address(containing_addr, name)
    claim_src = textwrap.dedent("\n".join(claim.lines))
    graph.add_node(Node(
        address=prop_addr,
        label=name,
        kind=NodeKind.PROPERTY,
        content=_node_content(None, claim_src or None),
    ))
    graph.add_edge(Edge(
        source=containing_addr,
        target=prop_addr,
        kind=EdgeKind.DEFINES,
    ))

    for info in extractor(claim.lines):
        if info.name == '_':
            continue   # anonymous witness — not extracted
        sym_addr = f"{prop_addr}#{info.name}"
        graph.add_node(Node(
            address=sym_addr,
            label=info.name,
            kind=NodeKind.SYMBOL,
            content=_node_content(None, info.source),
        ))
        graph.add_edge(Edge(
            source=prop_addr,
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

    Walks every :class:`~notlob.model.ProseBlock` in the module body
    (including those inside subheadings and appendix sections) and
    calls :meth:`NameGraph.resolve` on each :class:`~notlob.model.Ref`.

    ``#Label`` references are validated via the full three-step
    resolution order.  ``##Label`` references are validated against
    subheadings of the current module only.

    An unresolved reference is a first-class error; the returned list
    is empty when all references resolve.
    """
    mod_addr = module_address(module.title)
    errors   = list(_ref_errors(graph, module.body, mod_addr, mod_addr))
    if module.post_text:
        for sec in module.post_text.sections:
            if isinstance(sec, AppendixSection):
                errors.extend(
                    _ref_errors(graph, sec.body, mod_addr, mod_addr)
                )
    return errors


def _ref_errors(
    graph:    NameGraph,
    body:     list,
    mod_addr: str,
    loc_addr: str,
) -> Iterator[RefError]:
    """Yield RefErrors for each unresolved Ref in *body*."""
    for item in body:
        if isinstance(item, ProseBlock):
            for span in item.spans:
                if isinstance(span, Ref) and not _resolves(
                    graph, span, mod_addr
                ):
                    yield RefError(location=loc_addr, ref=span)
        elif isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            yield from _ref_errors(
                graph, item.body, mod_addr, sub_addr
            )


def _resolves(graph: NameGraph, ref: Ref, mod_addr: str) -> bool:
    """Return True if *ref* resolves against *graph* in *mod_addr*."""
    if ref.sub:
        # ##Label: only a subheading of the current module
        node = graph.node(f"{mod_addr}#{ref.label}")
        return node is not None and node.kind == NodeKind.SUBHEADING
    return graph.resolve(ref.label, context=mod_addr) is not None
