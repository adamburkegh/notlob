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
    AppendixSection, BulletBlock, Claim, CodeBlock, Module, NamedTest,
    ProseBlock, Ref, Subheading, TestGroup, TestsSection,
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
    EXAMPLE    = auto()    # claims: ~example block
    RUN        = auto()    # claims: ~run entry-point block
    TEST       = auto()    # claims: #Tests group, bare assertions, or ~test <name>
    EXTERNAL   = auto()    # external file declared with ~external in binding.lob


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
        base: str = "https://notlob.dev/project/",
        include_content: bool = False,
    ) -> str:
        """Serialise the graph as RDF in Turtle syntax.

        *base* is the base URI for the project; node addresses become
        URI fragments relative to it.  *include_content* attaches prose
        and code literals when present.

        No external dependency — Turtle is emitted as plain strings.
        """
        ns = "https://notlob.dev/ns#"
        lines = [
            f"@base <{base}> .",
            f"@prefix notlob: <{ns}> .",
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
            "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
            "",
        ]

        def _uri(address: str) -> str:
            return "<" + address.replace(" ", "%20") + ">"

        def _lit(s: str) -> str:
            escaped = (s.replace("\\", "\\\\")
                        .replace('"', '\\"')
                        .replace("\n", "\\n"))
            return f'"{escaped}"'

        def _long_lit(s: str) -> str:
            escaped = s.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
            return f'"""{escaped}"""'

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
        elif isinstance(item, BulletBlock):
            parts.append("\n".join(item.items))
    text = "".join(parts).strip()
    return text or None


def _bullet_block_count(body: list) -> int:
    """Count BulletBlock items in *body* (subheadings excluded)."""
    return sum(1 for item in body if isinstance(item, BulletBlock))


def _code_text(body: list) -> str | None:
    """Concatenate dedented CodeBlock and ~run claim text from *body*.

    Multiple blocks are joined with a blank line between them.
    Subheadings in *body* are ignored — they carry their own content.
    ``~run`` claims are included because they contain executable code
    that may reference imported symbols.
    """
    blocks: list[str] = []
    for item in body:
        if isinstance(item, CodeBlock):
            blocks.append(textwrap.dedent("\n".join(item.lines)))
        elif isinstance(item, Claim) and item.sigil == "~run":
            blocks.append(textwrap.dedent("\n".join(item.lines)))
    return "\n\n".join(blocks) if blocks else None


def _node_content(
    prose: str | None,
    code: str | None,
    bullet_block_count: int = 0,
) -> dict | None:
    """Build a content dict from *prose*, *code*, and bullet count."""
    d: dict = {}
    if prose:
        d["prose"] = prose
    if code:
        d["code"] = code
    if bullet_block_count:
        d["bullet_block_count"] = bullet_block_count
    return d or None


# ── Structure ────────────────────────────────────────────────

def build(module: Module) -> NameGraph:
    """Build a structural NameGraph from a Module.

    Creates a node for the module and one for each subheading,
    with CONTAINS edges from the module to its subheadings.
    Also creates TEST nodes for #Tests groups.
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
            _bullet_block_count(module.body),
        ),
        start_line=module.start_line,
    ))

    for item in module.body:
        if isinstance(item, Subheading):
            _add_subheading(graph, addr, item)

    _add_tests(graph, module, addr)

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
            _bullet_block_count(sub.body),
        ),
        start_line=sub.start_line,
    ))
    graph.add_edge(Edge(
        source=module_addr,
        target=sub_addr,
        kind=EdgeKind.CONTAINS,
    ))


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
        source = "\n".join(item.lines).strip()
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
            source = "\n".join(bare_lines).strip()
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
        source = "\n".join(bare_lines).strip()
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

    example_n = 0
    run_n = 0
    prop_n = 0
    for item in module.body:
        if isinstance(item, CodeBlock):
            _add_symbols(graph, item, mod_addr, mod_addr, extractor)
        elif isinstance(item, Claim):
            if item.sigil == "~example":
                example_n += 1
                _add_example(graph, item, mod_addr, example_n)
            elif item.sigil == "~run":
                run_n += 1
                _add_run(graph, item, mod_addr, run_n)
            else:
                prop_n += 1
                _add_property(
                    graph, item, mod_addr, prop_n, extractor,
                )
        elif isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            sub_example_n = 0
            sub_run_n = 0
            sub_prop_n = 0
            for sub_item in item.body:
                if isinstance(sub_item, CodeBlock):
                    _add_symbols(
                        graph, sub_item,
                        mod_addr, sub_addr,
                        extractor,
                    )
                elif isinstance(sub_item, Claim):
                    if sub_item.sigil == "~example":
                        sub_example_n += 1
                        _add_example(
                            graph, sub_item, sub_addr, sub_example_n,
                        )
                    elif sub_item.sigil == "~run":
                        sub_run_n += 1
                        _add_run(
                            graph, sub_item, sub_addr, sub_run_n,
                        )
                    else:
                        sub_prop_n += 1
                        _add_property(
                            graph, sub_item, sub_addr, sub_prop_n,
                            extractor,
                        )


def add_references_edges(
    graph:   NameGraph,
    modules: "list",
) -> None:
    """Populate REFERENCES edges from prose ``#Label`` cross-references.

    Walks each module's body and subheading bodies for
    :class:`~notlob.model.ProseBlock` items, then resolves each
    :class:`~notlob.model.Ref` against the graph.  Successfully resolved
    references become ``EdgeKind.REFERENCES`` edges from the containing
    MODULE or SUBHEADING node to the resolved target node.

    *start_line* on each edge is taken directly from ``Ref.start_line``.

    Must be called after all ``enrich()`` and IMPORTS passes so that
    ``graph.resolve()`` has the full import context available.
    """
    from .model import ProseBlock, Ref, Subheading

    seen: set[tuple[str, str]] = set()

    def _emit(source_addr: str, ref: "Ref", context: str) -> None:
        node = graph.resolve(ref.label, context=context)
        if node is None:
            return
        key = (source_addr, node.address)
        if key not in seen:
            graph.add_edge(Edge(
                source=source_addr,
                target=node.address,
                kind=EdgeKind.REFERENCES,
                start_line=ref.start_line,
            ))
            seen.add(key)

    def _walk_body(body: list, source_addr: str, context: str) -> None:
        for item in body:
            if isinstance(item, ProseBlock):
                for span in item.spans:
                    if isinstance(span, Ref):
                        _emit(source_addr, span, context)

    for module in modules:
        mod_addr = module_address(module.title)
        _walk_body(module.body, mod_addr, mod_addr)
        for item in module.body:
            if isinstance(item, Subheading):
                sub_addr = subheading_address(mod_addr, item.title)
                _walk_body(item.body, sub_addr, mod_addr)


def add_uses_edges(
    graph:          NameGraph,
    call_extractor: "Callable[[str], list[tuple[str, int]]]",
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
            start_line=block.start_line,
        ))
        graph.add_edge(Edge(
            source=containing_addr,
            target=addr,
            kind=EdgeKind.DEFINES,
        ))


def _add_property(
    graph:           NameGraph,
    claim:           Claim,
    containing_addr: str,
    ordinal:         int,
    extractor:       Extractor,
) -> None:
    """Register a ~property claim (named or unnamed) and its symbols."""
    parts = claim.sigil.split(None, 1)
    if len(parts) > 1:
        name = parts[1].strip()
        prop_addr = property_address(containing_addr, name)
        label = name
    else:
        prop_addr = claim_address(containing_addr, "property", ordinal)
        label = f"property#{ordinal}"

    claim_src = textwrap.dedent("\n".join(claim.lines))
    graph.add_node(Node(
        address=prop_addr,
        label=label,
        kind=NodeKind.PROPERTY,
        content=_node_content(None, claim_src or None),
        start_line=claim.start_line,
    ))
    graph.add_edge(Edge(
        source=containing_addr,
        target=prop_addr,
        kind=EdgeKind.DEFINES,
    ))

    for info in extractor(claim.lines):
        if info.name == '_':
            continue
        sym_addr = f"{prop_addr}#{info.name}"
        graph.add_node(Node(
            address=sym_addr,
            label=info.name,
            kind=NodeKind.SYMBOL,
            content=_node_content(None, info.source),
            start_line=claim.start_line,
        ))
        graph.add_edge(Edge(
            source=prop_addr,
            target=sym_addr,
            kind=EdgeKind.DEFINES,
        ))


def _add_example(
    graph:           NameGraph,
    claim:           Claim,
    containing_addr: str,
    ordinal:         int,
) -> None:
    """Register a ~example claim as a node."""
    addr = claim_address(containing_addr, "example", ordinal)
    source = textwrap.dedent("\n".join(claim.lines)).strip()
    graph.add_node(Node(
        address=addr,
        label=f"example#{ordinal}",
        kind=NodeKind.EXAMPLE,
        content=_node_content(None, source or None),
        start_line=claim.start_line,
    ))
    graph.add_edge(Edge(
        source=containing_addr,
        target=addr,
        kind=EdgeKind.DEFINES,
    ))


def _add_run(
    graph:           NameGraph,
    claim:           Claim,
    containing_addr: str,
    ordinal:         int,
) -> None:
    """Register a ~run claim as a node."""
    addr = claim_address(containing_addr, "run", ordinal)
    source = textwrap.dedent("\n".join(claim.lines)).strip()
    graph.add_node(Node(
        address=addr,
        label=f"run#{ordinal}",
        kind=NodeKind.RUN,
        content=_node_content(None, source or None),
        start_line=claim.start_line,
    ))
    graph.add_edge(Edge(
        source=containing_addr,
        target=addr,
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
