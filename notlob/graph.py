"""notlob.graph — Name-graph: structure, symbols, and cross-references.

The graph is the parse tree of a package, with cross-references.  Every
element of a ``.lob`` file is a node, and each file is one tree: a module
at the root, and below it the elements it holds, in the order they are
written.  Text is held once, on the leaves (a paragraph, a code block, a
bullet list, a claim, a run of assertions); every other node holds the
first and last line it occupies.

Tree:             :func:`build` makes a module's tree; :func:`enrich` adds
                  the symbols its code defines, through a language
                  binding.
Cross-references: ``CITES`` edges from the paragraph that holds a
                  ``#Label`` to the node it names
                  (:func:`add_cites_edges`); ``USES`` edges from code
                  to the symbols it calls (:func:`add_uses_edges`).
Package graph:    ``IMPORTS`` edges from ``#References`` lob-ref
                  declarations; ``build_package()`` lives in
                  ``notlob.project`` because it requires file-system
                  access.

Node addresses
--------------
Every node has a globally unique address, computed from where it is
written.  The ``#`` character separates a module address from anything
within it.  A named node is addressed by the scope its name belongs to
(:func:`named_address`; a module, and a ``~property``, ``#Tests`` and
``##group`` in it, are scopes) and its name, and a positional one by its
kind and position among its siblings of that kind
(:func:`positional_address`).  What each kind is, such as whether it
opens a scope, is stated once in :data:`KINDS`:

  Module:     title → lowercase, spaces → slashes
              "Pricing Discounts" → "pricing/discounts"

  Subheading: module_address + "#" + name  (name preserved as-is)
              "pricing/discounts#Stacking Discounts"

  Symbol:     module_address + "#" + name, wherever in the module it is
              written: "pricing/discounts#apply_discount"

  Appendix:   module_address + "#" + its title, or "Appendix" if bare
              "pricing/discounts#Glossary"

  Positional: parent_address + "#" + kind + "#" + n, counted from 1
              "pricing/discounts#prose#2", "pricing/discounts#example#1"

Addresses are machine identifiers; a name is the human-readable name as
written in source, and a node addressed by position has none.  A name
collision between nodes of different kinds (a symbol and a subheading in
one module) is an error: all named things share one namespace per module.
The post-text (what follows ``---``) is a node in the tree but no part of
an address: ``#Tests`` and the appendices are addressed as if they hung
from the module.

This scheme is isomorphic to URI fragment addressing.

Edge vocabulary
---------------
  CONTAINS      — parent → child, where a node is written; the tree
  CONTAINS_INDIRECTLY
                — a node → what is written in it, through nodes a view
                  does not show; only a view writes one (see
                  :mod:`notlob.view`)
  CITES         — paragraph → the node a ``#Label`` in it names
  USES          — code → a symbol it refers to by name
  IMPORTS       — module → module
  USES_EXTERNAL — binding module → a file it declares

Usage::

    from notlob import parse_file, from_tree
    from notlob.graph import build, enrich
    from notlob.bindings.python import extract_symbols

    module = from_tree(parse_file("examples/roman/roman/numerals.lob"))
    graph  = build(module)
    enrich(graph, module, extract_symbols)

    node = graph.node("roman/numerals#to_roman")
    for child in graph.children("roman/numerals"):
        print(child.kind.name, child.address)
"""

from __future__ import annotations

import fnmatch
import textwrap
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Iterator

from .bindings import (
    ClaimToRun, Extractor, ImportSplitter, SymbolInfo, default_split_imports,
)
from .model import (
    AppendixSection, BindingSection, BulletBlock, Claim, CodeBlock, Module,
    NamedTest, ProseBlock, Ref, ReferencesSection, Subheading, TestGroup,
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


def named_address(scope: str, name: str) -> str:
    """The address of a node a document names, from the address of the
    scope the name belongs to (see :meth:`NameGraph.scope_of`).

    ("pricing/discounts", "Stacking Discounts")
        -> "pricing/discounts#Stacking Discounts"
    ("roman/numerals", "to_roman") -> "roman/numerals#to_roman"

    A module is a scope, and so are a ``~property``, ``#Tests`` and a
    ``##group`` in it. Everything named in one scope shares its
    namespace: a symbol and a subheading of one name collide.
    """
    return f"{scope}#{name}"


def positional_address(parent: str, kind: NodeKind, n: int) -> str:
    """The address of a node the document does not name, from the address
    of the nearest container it is written in that is not a region of
    the tree, its *kind*'s segment and its ordinal *n* among the nodes
    of that kind written there, counted from 1. The ordinal is left off
    for a kind that is not numbered.

    ("roman/numerals#Decoding", EXAMPLE, 1)
        -> "roman/numerals#Decoding#example#1"
    ("roman/numerals", POST_TEXT, 1) -> "roman/numerals#post-text"

    Raises ``ValueError`` for a kind with no segment, which is always
    named.
    """
    facts = KINDS[kind]
    if facts.segment is None:
        raise ValueError(f"{kind.name} nodes are named, not positional")
    address = f"{parent}#{facts.segment}"
    return f"{address}#{n}" if facts.numbered else address


# ── Node ─────────────────────────────────────────────────────

class NodeKind(Enum):
    """What a node is. A kind says what the node is, not whether it is
    named: ``PROPERTY`` covers the named and the anonymous."""
    MODULE     = auto()    # a .lob file: the root of its tree
    SUBHEADING = auto()    # a ##Subheading
    SYMBOL     = auto()    # a name defined in code: function, class, constant
    PROPERTY   = auto()    # a ~property claim, named or not
    EXAMPLE    = auto()    # an ~example claim
    RUN        = auto()    # a ~run claim, of any mode
    TEST       = auto()    # a ~test <name>
    TEST_LINES = auto()    # a run of bare assertions in a test group
    EXTERNAL   = auto()    # a file declared with ~external, outside the trees
    PROSE      = auto()    # a paragraph (leaf)
    CODE       = auto()    # an indented code block (leaf)
    BULLETS    = auto()    # a bullet list (leaf)
    APPENDIX   = auto()    # an #Appendix section
    TESTS      = auto()    # the #Tests section
    POST_TEXT  = auto()    # everything after the --- separator
    TEST_GROUP = auto()    # a ##group in #Tests, which holds tests
    REFERENCES = auto()    # the #References section
    BINDING    = auto()    # the #Binding section (binding.lob)
    LISTING    = auto()    # a module listed in #References: #Title
    IMPORT     = auto()    # one import statement of the bound language
    DECLARATION = auto()   # a ~language, ~external, ... in #Binding


class Rank:
    """The scale a view is cut on: one scale of natural numbers, with names
    for the common ranks. Every node, edge and body has a rank, and a view
    shows what is at or below its own. It is defined here and nowhere else:
    a ``rank`` in :data:`KINDS`, the same for the edge kinds in
    :data:`EDGE_RANKS`, and the bodies at :attr:`BODY`."""
    STRUCTURE  = 1     # the nodes an outline shows, and the tree
    REFERENCES = 2     # the references, with the declarations they start at
    BLOCK      = 3     # the blocks of a file: paragraphs, code, listings
    BODY       = 4     # each node's own written lines


@dataclass(frozen=True)
class KindFacts:
    """What is true of every node of a kind. A kind is an adjective, and
    each of these is one the code asks in more than one place.

    rank             where a view starts to show it: see :class:`Rank`
    opens_scope      a name written in a node of this kind belongs to it
    claim            an ``~example``, ``~property`` or ``~run``
    runnable         a binding runs it: a claim, or a test
    section          a section of the document
    region           a region of the tree, no part of an address
    text_in_holder   its text is lines of the node that holds it
    segment          its part of an address when it is positional; ``None``
                     for a kind that is always named
    numbered         a positional address has an ordinal after the segment
    sigil            the sigil that begins it in its file, ``None`` for a kind
                     with none
    heading          the word a reader's text says before its name, ``None``
                     for a kind with none
    """
    rank:           int
    opens_scope:    bool = False
    claim:          bool = False
    runnable:       bool = False
    section:        bool = False
    region:         bool = False
    text_in_holder: bool = False
    segment:        str | None = None
    numbered:       bool = False
    sigil:          str | None = None
    heading:        str | None = None


#: The facts of each kind, one row for every :class:`NodeKind`.
KINDS: dict[NodeKind, KindFacts] = {
    NodeKind.MODULE: KindFacts(Rank.STRUCTURE, opens_scope=True),
    NodeKind.SUBHEADING: KindFacts(Rank.STRUCTURE, section=True),
    NodeKind.SYMBOL: KindFacts(Rank.STRUCTURE, text_in_holder=True),
    NodeKind.PROPERTY: KindFacts(
        Rank.STRUCTURE, opens_scope=True, claim=True, runnable=True,
        segment="property", numbered=True, sigil="~property"),
    NodeKind.EXAMPLE: KindFacts(
        Rank.STRUCTURE, claim=True, runnable=True, segment="example",
        numbered=True, sigil="~example"),
    NodeKind.RUN: KindFacts(
        Rank.STRUCTURE, claim=True, runnable=True, segment="run",
        numbered=True, sigil="~run"),
    NodeKind.TEST: KindFacts(Rank.STRUCTURE, runnable=True, sigil="~test"),
    NodeKind.TEST_LINES: KindFacts(
        Rank.BLOCK, runnable=True, segment="test", numbered=True),
    NodeKind.EXTERNAL: KindFacts(Rank.REFERENCES),
    NodeKind.PROSE: KindFacts(Rank.BLOCK, segment="prose", numbered=True),
    NodeKind.CODE: KindFacts(Rank.BLOCK, segment="code", numbered=True),
    NodeKind.BULLETS: KindFacts(
        Rank.BLOCK, segment="bullets", numbered=True),
    NodeKind.APPENDIX: KindFacts(
        Rank.STRUCTURE, section=True, heading="Appendix"),
    NodeKind.TESTS: KindFacts(Rank.STRUCTURE, opens_scope=True),
    NodeKind.POST_TEXT: KindFacts(
        Rank.BLOCK, region=True, segment="post-text"),
    NodeKind.TEST_GROUP: KindFacts(Rank.STRUCTURE, opens_scope=True),
    NodeKind.REFERENCES: KindFacts(Rank.STRUCTURE),
    NodeKind.BINDING: KindFacts(Rank.STRUCTURE),
    NodeKind.LISTING: KindFacts(
        Rank.BLOCK, segment="listing", numbered=True),
    NodeKind.IMPORT: KindFacts(Rank.BLOCK, segment="import", numbered=True),
    NodeKind.DECLARATION: KindFacts(
        Rank.REFERENCES, segment="declaration", numbered=True),
}

#: The named levels, each a rank: a view made from one carries its name,
#: and nothing else reads it. Each shows the whole tree.
PRESETS: dict[str, int] = {
    "outline": Rank.STRUCTURE,
    "index":   Rank.REFERENCES,
    "block":   Rank.BLOCK,
    "full":    Rank.BODY,
}


@dataclass(frozen=True)
class Node:
    """A node in the name-graph: one element of a ``.lob`` file.

    address     globally unique machine identifier (tooling-derived)
    kind        what type of element this node is
    start_line  first line of the element in the ``.lob`` file (1-based)
    end_line    last non-blank line of the element
    file        the ``.lob`` file, relative to the project root, with ``/``
                separators; ``None`` for a module built on its own
    text        a leaf's text, held once: a paragraph with its references
                written with their sigils, a dedented code block, a bullet
                list's items one to a line, a claim's dedented lines, a
                run of bare assertions or a named test as written. A symbol
                holds none, as its lines are in the text of the node that
                holds it: see :meth:`NameGraph.text`.
    refs        the references written in a ``PROSE`` leaf, as parsed
    mode        when a ``RUN`` runs: ``"on-load"`` or ``"on-invocation"``
                (what a bare ``~run`` means); ``None`` on every other node
    declares    what a ``DECLARATION`` declares (``"language"``,
                ``"external"``, ``"on-build"`` or ``"keep-generated-src"``);
                ``None`` on every other node
    value       the value a ``DECLARATION`` gives it, when it has one
    name        the name the node's address is built from: a module's
                title, a heading, a symbol, an ``EXTERNAL``'s file, an
                appendix's title (``Appendix`` if bare), a ``##group``, a
                ``~property <name>`` or a ``~test <name>``; ``None`` for a
                node with a positional address (a paragraph, an unnamed
                ``~property``, a run of test lines) and for ``#Tests``,
                ``#References`` and ``#Binding``, which are keywords

    A node's own lines, its body, are not a field: which lines a node's
    body holds depends on which nodes a view shows (see :func:`bodies`).

    The fields after ``kind`` are excluded from equality and hash, so two
    nodes with the same address and kind are the same node.
    """
    address: str
    kind:    NodeKind
    start_line: int | None = field(
        default=None, hash=False, compare=False,
    )
    end_line: int | None = field(
        default=None, hash=False, compare=False,
    )
    file: str | None = field(
        default=None, hash=False, compare=False,
    )
    text: str | None = field(
        default=None, hash=False, compare=False,
    )
    refs: tuple[Ref, ...] = field(
        default=(), hash=False, compare=False,
    )
    mode: str | None = field(
        default=None, hash=False, compare=False,
    )
    name: str | None = field(
        default=None, hash=False, compare=False,
    )
    declares: str | None = field(
        default=None, hash=False, compare=False,
    )
    value: str | None = field(
        default=None, hash=False, compare=False,
    )

    def __repr__(self) -> str:
        return f"<{self.kind.name} {self.address!r}>"


# ── Edge ─────────────────────────────────────────────────────

class EdgeKind(Enum):
    """How two nodes relate. Only ``CONTAINS`` makes the tree; a graph
    holds no ``CONTAINS_INDIRECTLY``, which only a view writes."""
    CONTAINS      = auto()   # parent to child: where a node is written
    CONTAINS_INDIRECTLY = auto()   # a node to what it holds, through nodes
                                   # a view does not show
    IMPORTS      = auto()   # module to module, from a #References line
    USES_EXTERNAL = auto()   # binding module to a file it declares
    USES          = auto()   # code to a symbol it refers to by name
    CITES         = auto()   # a paragraph to the node a #Label in it names


#: The rank of each edge kind: one for every :class:`EdgeKind`.
EDGE_RANKS: dict[EdgeKind, int] = {
    EdgeKind.CONTAINS:            Rank.STRUCTURE,
    EdgeKind.CONTAINS_INDIRECTLY: Rank.STRUCTURE,
    EdgeKind.IMPORTS:             Rank.REFERENCES,
    EdgeKind.USES_EXTERNAL:       Rank.REFERENCES,
    EdgeKind.USES:                Rank.REFERENCES,
    EdgeKind.CITES:               Rank.REFERENCES,
}


@dataclass(frozen=True)
class Edge:
    """An edge from *source* to *target*. *lines* are every line of the
    ``.lob`` file a reference is written on, each once and in order; empty
    when none is known, and for a ``CONTAINS`` edge. There is one edge for
    each source, target and kind."""
    source:     str             # address of the source node
    target:     str             # address of the target node
    kind:       EdgeKind
    lines:      tuple[int, ...] = field(
        default=(), hash=False, compare=False)

    @property
    def first_line(self) -> int | None:
        """The first of the *lines*, or ``None`` where there are none: the
        one line the old documents give a reference."""
        return self.lines[0] if self.lines else None


# ── Graph ────────────────────────────────────────────────────

class AddressCollisionError(ValueError):
    """Two nodes claim the same address: two differently-kinded ones, or
    two of a name written in the document (a heading, an appendix's
    title, a ``~property`` or a ``~test`` name) in one scope.

    Raised by :meth:`NameGraph.add_node` for kinds, and by :func:`build`
    for a restated document name -- e.g. a ``##Layout`` subheading and a
    ``class Layout`` symbol in the same module both resolve to
    ``mod#Layout``, as do two ``##Layout`` subheadings, and a
    ``##Glossary`` and an ``#Appendix Glossary``. A symbol written
    twice is not an error: the last definition wins. All named things
    share one namespace per module, so this is a real document error,
    not a crash: a
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

        if existing_kind == new_kind:
            names = (f"names two {existing_kind.name.lower()}s "
                     f"(line {existing_line} and line {new_line})"
                     if existing_line is not None and new_line is not None
                     else f"names two {existing_kind.name.lower()}s")
        else:
            names = (f"names both a {_at(existing_kind, existing_line)} "
                     f"and a {_at(new_kind, new_line)}")
        super().__init__(
            f"Address collision: {address!r} {names} -- all named "
            f"things share one namespace per module."
        )


class NameGraph:
    """The parse tree of a package, with cross-references.

    Every element of a ``.lob`` file is a node, in one tree per file
    joined by ``CONTAINS`` edges (an element's parent is where it is
    written); ``USES``, ``CITES``, ``IMPORTS`` and ``USES_EXTERNAL``
    edges cross the trees.  Nodes are keyed by address; edges are stored
    as a list and also indexed by source for efficient child lookup, and a
    parent index finds a node's parent without a scan.
    """

    def __init__(self) -> None:
        self._nodes:  dict[str, Node]        = {}
        self._edges:  list[Edge]             = []
        self._out:    dict[str, list[Edge]]  = {}
        self._parent: dict[str, str]         = {}
        self._sources: dict[str, list[str]]  = {}
        self._collisions: list | None        = None

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
        if edge.kind == EdgeKind.CONTAINS:
            self._parent[edge.target] = edge.source

    def release(self, address: str) -> None:
        """Take the node at *address* out of the node that contains it,
        by removing the ``CONTAINS`` edge into it; the node stays."""
        parent = self._parent.pop(address, None)
        if parent is None:
            return
        held = [e for e in self._out.get(parent, [])
                if e.kind == EdgeKind.CONTAINS and e.target == address]
        for edge in held:
            self._out[parent].remove(edge)
            self._edges.remove(edge)

    def merge(self, other: NameGraph) -> None:
        """Absorb all nodes and edges from another graph."""
        for node in other._nodes.values():
            self.add_node(node)
        for edge in other._edges:
            self.add_edge(edge)
        self._sources.update(other._sources)

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

    def parent_of(self, address: str) -> Node | None:
        """The node that contains the node at *address*, or ``None`` for a
        module, an ``EXTERNAL`` node and an unknown address."""
        parent = self._parent.get(address)
        return self._nodes.get(parent) if parent is not None else None

    def module_of(self, address: str) -> str | None:
        """The address of the module the node at *address* belongs to.

        ``None`` for an unknown address and for an ``EXTERNAL`` node,
        which belongs to no module."""
        node = self._nodes.get(address)
        seen: set[str] = set()
        while node is not None and node.kind != NodeKind.MODULE:
            if node.kind == NodeKind.EXTERNAL or node.address in seen:
                return None
            seen.add(node.address)
            node = self.parent_of(node.address)
        return node.address if node is not None else None

    def scope_of(self, address: str) -> str | None:
        """The address of the scope a name written in the node at
        *address* belongs to: the node itself if its kind opens a scope,
        or else the scope of the node that contains it.

        ``None`` for an unknown address and for an ``EXTERNAL`` node,
        which is written in no scope."""
        node = self._nodes.get(address)
        while node is not None and not KINDS[node.kind].opens_scope:
            node = self.parent_of(node.address)
        return node.address if node is not None else None

    def post_section(self, module: str, kind: NodeKind) -> Node | None:
        """The node of *kind* among the sections after the ``---`` of the
        module at *module* (``REFERENCES``, ``BINDING`` or ``TESTS``), or
        ``None`` if it has none."""
        for region in self.children(module):
            if KINDS[region.kind].region:
                for node in self.children(region.address):
                    if node.kind == kind:
                        return node
        return None

    def import_edges(self, module: str) -> list[Edge]:
        """The ``IMPORTS`` edges from the listings written in the tree of
        the module at *module*, one to each module it lists (the first),
        in document order. An edge starts at the line that makes it, so it
        is a listing, not the module, that is its source."""
        found: dict[str, Edge] = {}
        for edge in self._edges:
            if (edge.kind == EdgeKind.IMPORTS
                    and edge.target in self._nodes
                    and self.module_of(edge.source) == module):
                found.setdefault(edge.target, edge)
        return list(found.values())

    def importer_edges(self, module: str) -> list[Edge]:
        """The ``IMPORTS`` edges into the module at *module*, one from
        each module that lists it (the first), in the order their listings
        were added."""
        found: dict[str, Edge] = {}
        for edge in self._edges:
            if edge.kind == EdgeKind.IMPORTS and edge.target == module:
                address = self.module_of(edge.source)
                if address in self._nodes:
                    found.setdefault(address, edge)
        return list(found.values())

    def imports_of(self, module: str) -> list[Node]:
        """The modules the module at *module* lists, in document order,
        each once (see :meth:`import_edges`)."""
        return [self._nodes[e.target] for e in self.import_edges(module)]

    def imported_by(self, module: str) -> list[Node]:
        """The modules that list the module at *module*, each once, in
        the order their listings were added (see :meth:`importer_edges`)."""
        return [self._nodes[self.module_of(e.source)]
                for e in self.importer_edges(module)]

    def edges(self, kind: EdgeKind | None = None) -> Iterator[Edge]:
        """Iterate over every edge, or every edge of *kind*, in the order
        they were added."""
        for edge in self._edges:
            if kind is None or edge.kind == kind:
                yield edge

    def sections(self, module_address_: str) -> list[Node]:
        """The sections of the module at *module_address_*, in document
        order: its subheadings and appendices (which hang from the
        post-text), and an appendix's subheadings."""
        found: list[Node] = []

        def walk(address: str) -> None:
            for child in self.children(address):
                facts = KINDS[child.kind]
                if facts.section:
                    found.append(child)
                if facts.section or facts.region:
                    walk(child.address)

        walk(module_address_)
        return found

    def prose(self, address: str) -> str:
        """The prose written directly in the module or section at
        *address*: its paragraphs and bullet items, a blank line apart,
        references with their sigils; not its sections'. ``""`` if there
        is none."""
        blocks = (
            (child.text or "").strip() for child in self.children(address)
            if child.kind in (NodeKind.PROSE, NodeKind.BULLETS)
        )
        return "\n\n".join(block for block in blocks if block)

    def bullet_list_count(self, address: str) -> int:
        """The number of bullet lists written directly in the module or
        section at *address*."""
        return sum(1 for child in self.children(address)
                   if child.kind == NodeKind.BULLETS)

    def claims(self, address: str) -> list[Node]:
        """The claims (examples, properties and ``~run`` blocks) written
        directly in the module or section at *address*, in document
        order."""
        return [
            child for child in self.children(address)
            if KINDS[child.kind].claim
        ]

    def text(self, address: str) -> str | None:
        """The text of the node at *address*.

        A leaf's text is its own. A symbol's is the lines it occupies of
        the node that holds it (a code block, or a ``~property``), read
        by its lines, so the graph holds the text once. A symbol made by a
        binding that gave no lines carries its own text. ``None`` for a
        node with no text of its own and for an unknown address.
        """
        node = self._nodes.get(address)
        if node is None or not KINDS[node.kind].text_in_holder:
            return None if node is None else node.text
        if node.text is not None:
            return node.text
        holder = self.parent_of(address)
        if (holder is None or holder.text is None
                or holder.start_line is None
                or node.start_line is None or node.end_line is None):
            return None
        # A code block's text starts on its first line; a claim's, on the
        # line after its sigil.
        first = holder.start_line + (0 if holder.kind == NodeKind.CODE else 1)
        lines = holder.text.split("\n")
        return "\n".join(
            lines[node.start_line - first:node.end_line - first + 1])

    def resolve(
        self,
        name:    str,
        context: str | None = None,
    ) -> Node | None:
        """Resolve the name a reference gives to a node.

        Implements the three-step resolution order from DESIGN.md:
          1. Symbol defined in the current module.
          2. Subheading of the current module.
          3. A module the current module lists (see :meth:`imports_of`).

        *context* is a module address (e.g. ``"roman/numerals"``).
        When context is given, step 3 is restricted to the modules it
        lists — unlisted modules are invisible even if they exist in the
        same package graph.

        Without context, only a full MODULE scan is attempted
        (useful for tooling / package-level lookup; never for
        validating in-source cross-references).

        Symbols and subheadings share the ``#`` address space; a
        collision is an error at add_node time, so steps 1 and 2
        reduce to a single address lookup distinguished by NodeKind.
        """
        if context is not None:
            # Steps 1 & 2: symbol or subheading in the current module
            node = self._nodes.get(named_address(context, name))
            if node is not None:
                if node.kind in (NodeKind.SYMBOL, NodeKind.SUBHEADING):
                    return node
            # Step 3: a module the current module lists
            for target in self.imports_of(context):
                if target.name == name:
                    return target
        else:
            # No context: scan all MODULE nodes (tooling use only)
            for node in self._nodes.values():
                if node.name == name and node.kind == NodeKind.MODULE:
                    return node
        return None

    def search(
        self,
        pattern: str,
        kind: NodeKind | None = None,
    ) -> Iterator[Node]:
        """Yield nodes whose name matches *pattern* (fnmatch-style).

        ``*discount*`` matches any name containing "discount".
        ``apply_*`` matches any name starting with "apply_".
        Matching is case-sensitive.  Pass *kind* to restrict results.
        A node without a name (see :attr:`Node.name`) is found by no
        pattern, whatever *kind* is.
        """
        for node in self._nodes.values():
            if kind is not None and node.kind != kind:
                continue
            if node.name is not None and fnmatch.fnmatch(node.name, pattern):
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

    def __len__(self) -> int:
        return len(self._nodes)

    def __repr__(self) -> str:
        return (
            f"<NameGraph {len(self._nodes)} nodes,"
            f" {len(self._edges)} edges>"
        )


# ── Content helpers ──────────────────────────────────────────

def _prose_leaf_text(block: ProseBlock) -> str:
    """A paragraph's text: its spans joined, each reference written with
    its sigil (``#Label`` or ``##Label``)."""
    return "".join(
        span if isinstance(span, str)
        else ("##" if span.sub else "#") + span.label
        for span in block.spans
    )


# ── Structure ────────────────────────────────────────────────

class _Ordinals:
    """Counts the nodes of one parent that have positional addresses, per
    kind, from 1."""

    def __init__(self) -> None:
        self._n: dict[NodeKind, int] = {}

    def next(self, kind: NodeKind) -> int:
        self._n[kind] = self._n.get(kind, 0) + 1
        return self._n[kind]


def _positional_identity(parent: str, kind: NodeKind, n: int) -> str:
    """The address of the *n*th node of *kind* written in the node at
    *parent* that the document does not name."""
    return positional_address(parent, kind, n)


def _claim_identity(
    graph: NameGraph, claim: Claim, parent: str, ordinals: _Ordinals,
) -> tuple[str, NodeKind, str | None]:
    """``(address, kind, name)`` of *claim* written in the node at
    *parent*. The kind follows the sigil: every ``~run`` (bare, ``on-load``
    or ``on-invocation``) is a ``RUN``, ``~example`` an ``EXAMPLE`` and
    anything else a ``PROPERTY``. A named property is named in the scope
    of *parent* but still counts among its properties; any other claim,
    and an unnamed property, has no name."""
    parts = claim.sigil.split(None, 1)
    if parts[0] == "~example":
        kind = NodeKind.EXAMPLE
    elif parts[0] == "~run":
        kind = NodeKind.RUN
    else:
        kind = NodeKind.PROPERTY
    n = ordinals.next(kind)
    if kind == NodeKind.PROPERTY and len(parts) > 1:
        name = parts[1].strip()
        return named_address(graph.scope_of(parent), name), kind, name
    return _positional_identity(parent, kind, n), kind, None


def _run_mode(claim: Claim) -> str:
    """When a ``~run`` runs: the mode written after the sigil
    (``on-load`` or ``on-invocation``), and ``on-invocation`` for a bare
    ``~run``, which is what the grammar means by it."""
    parts = claim.sigil.split()
    return parts[1] if len(parts) > 1 else "on-invocation"


def _add_child(
    graph: NameGraph, parent: str, node: Node, document_name: bool = False,
) -> None:
    """Add *node* to the graph, contained by the node at *parent*.

    A node already at its address is replaced, and is contained only by
    *parent*: a symbol defined twice in a scope keeps its last definition.
    A *document_name* (a heading, an appendix's title, a ``~property`` or
    ``~test`` name) is written once in its scope, so a second is a
    collision: raised, or collected when :func:`build` was given a list
    to collect them in, in which case it replaces the first."""
    existing = graph.node(node.address)
    if document_name and existing is not None:
        error = AddressCollisionError(
            node.address, existing.kind, node.kind,
            existing.start_line, node.start_line)
        if graph._collisions is None:
            raise error
        graph._collisions.append(error)
    graph.add_node(node)
    graph.release(node.address)
    graph.add_edge(Edge(
        source=parent, target=node.address, kind=EdgeKind.CONTAINS))


def _add_prose(
    graph: NameGraph, parent: str, block: ProseBlock, n: int,
    file: str | None,
) -> None:
    address = _positional_identity(parent, NodeKind.PROSE, n)
    _add_child(graph, parent, Node(
        address=address,
        kind=NodeKind.PROSE, text=_prose_leaf_text(block),
        refs=tuple(s for s in block.spans if isinstance(s, Ref)),
        start_line=block.start_line, end_line=block.end_line, file=file,
    ))


def build(
    module: Module, file: str | None = None,
    collisions: list[AddressCollisionError] | None = None,
) -> NameGraph:
    """Build the tree of a Module as a NameGraph.

    Every element of the module is a node, contained by the node it is
    written in, in document order: the module holds its paragraphs, code
    blocks, bullet lists, claims and subheadings, and its post-text (what
    follows the ``---`` separator, if there is one); a subheading or
    appendix holds the same as the module's body; the post-text holds the
    ``#Tests`` section and the appendices; ``#Tests`` holds its groups,
    runs of bare assertions, named tests and commentary. The post-text is
    a region of the tree and no part of an address: what hangs from it
    is addressed as if it hung from the module. A leaf holds its text, a
    node its first and last line. Claims are made here, as they need no
    language binding; :func:`enrich` adds the symbols code defines.

    *file* is the module's path relative to the project root, with ``/``
    separators; ``None`` for a module built on its own.

    A name written in the document twice in one scope (two headings, two
    appendix titles, two ``~property`` or two ``~test`` names) raises
    :class:`AddressCollisionError`.  Given a list as *collisions*, each is
    appended to it instead, and the later node replaces the earlier, so
    the structure is built whole.
    """
    graph = NameGraph()
    graph._collisions = collisions
    try:
        _build_tree(graph, module, file)
    finally:
        graph._collisions = None      # the graph does not keep the list
    return graph


def _build_tree(graph: NameGraph, module: Module, file: str | None) -> None:
    """Add the tree of *module* to *graph*, which is empty."""
    addr = module_address(module.title)

    graph.add_node(Node(
        address=addr, kind=NodeKind.MODULE,
        start_line=module.start_line, end_line=module.end_line, file=file,
        name=module.title,
    ))
    _add_items(graph, module.body, addr, file)

    post_text = module.post_text
    if post_text is None:
        return
    post_addr = positional_address(addr, NodeKind.POST_TEXT, 1)
    _add_child(graph, addr, Node(
        address=post_addr, kind=NodeKind.POST_TEXT,
        start_line=post_text.start_line, end_line=post_text.end_line,
        file=file,
    ))
    for section in post_text.sections:
        if isinstance(section, AppendixSection):
            name = section.name or "Appendix"
            app_addr = named_address(graph.scope_of(post_addr), name)
            _add_child(graph, post_addr, Node(
                address=app_addr,
                kind=NodeKind.APPENDIX,
                start_line=section.start_line, end_line=section.end_line,
                file=file, name=name,
            ), document_name=True)
            _add_items(graph, section.body, app_addr, file)
        elif isinstance(section, TestsSection):
            _add_tests(graph, section, post_addr, file)
        elif isinstance(section, ReferencesSection):
            _add_references(graph, section, post_addr, file)
        elif isinstance(section, BindingSection):
            _add_binding(graph, section, post_addr, file)


def _add_references(
    graph:   NameGraph,
    section: ReferencesSection,
    parent:  str,
    file:    str | None,
) -> None:
    """Add the ``#References`` section, named in the scope of the node at
    *parent*, to it, and a ``LISTING`` for each module it lists. The
    import statements of the bound language are added by :func:`enrich`,
    which has the binding that knows where one ends."""
    address = named_address(graph.scope_of(parent), "References")
    _add_child(graph, parent, Node(
        address=address, kind=NodeKind.REFERENCES,
        start_line=section.start_line, end_line=section.end_line,
        file=file,
    ))
    ordinals = _Ordinals()
    for listing in section.listings:
        listing_address = _positional_identity(
            address, NodeKind.LISTING, ordinals.next(NodeKind.LISTING))
        _add_child(graph, address, Node(
            address=listing_address, kind=NodeKind.LISTING,
            text=f"#{listing.title}",
            start_line=listing.line, end_line=listing.line, file=file,
        ))


def _add_binding(
    graph:   NameGraph,
    section: BindingSection,
    parent:  str,
    file:    str | None,
) -> None:
    """Add the ``#Binding`` section, named in the scope of the node at
    *parent*, to it, and a ``DECLARATION`` for each line it declares
    something on."""
    address = named_address(graph.scope_of(parent), "Binding")
    _add_child(graph, parent, Node(
        address=address, kind=NodeKind.BINDING,
        start_line=section.start_line, end_line=section.end_line,
        file=file,
    ))
    ordinals = _Ordinals()
    for declaration in section.declarations:
        decl_address = _positional_identity(
            address, NodeKind.DECLARATION,
            ordinals.next(NodeKind.DECLARATION))
        _add_child(graph, address, Node(
            address=decl_address, kind=NodeKind.DECLARATION,
            text=declaration.text,
            start_line=declaration.line, end_line=declaration.line,
            file=file, declares=declaration.keyword,
            value=declaration.value,
        ))


def _add_items(
    graph:  NameGraph,
    items:  list,
    parent: str,
    file:   str | None,
) -> None:
    """Add the elements of a body (a module's, a subheading's or an
    appendix's) as children of the node at *parent*."""
    ordinals = _Ordinals()
    for item in items:
        if isinstance(item, Subheading):
            sub_addr = named_address(graph.scope_of(parent), item.title)
            _add_child(graph, parent, Node(
                address=sub_addr,
                kind=NodeKind.SUBHEADING,
                start_line=item.start_line, end_line=item.end_line,
                file=file, name=item.title,
            ), document_name=True)
            _add_items(graph, item.body, sub_addr, file)
        elif isinstance(item, ProseBlock):
            _add_prose(
                graph, parent, item, ordinals.next(NodeKind.PROSE), file)
        elif isinstance(item, CodeBlock):
            address = _positional_identity(
                parent, NodeKind.CODE, ordinals.next(NodeKind.CODE))
            _add_child(graph, parent, Node(
                address=address,
                kind=NodeKind.CODE,
                text=textwrap.dedent("\n".join(item.lines)),
                start_line=item.start_line, end_line=item.end_line,
                file=file,
            ))
        elif isinstance(item, BulletBlock):
            address = _positional_identity(
                parent, NodeKind.BULLETS, ordinals.next(NodeKind.BULLETS))
            _add_child(graph, parent, Node(
                address=address,
                kind=NodeKind.BULLETS, text="\n".join(item.items),
                start_line=item.start_line, end_line=item.end_line,
                file=file,
            ))
        elif isinstance(item, Claim):
            address, kind, name = _claim_identity(
                graph, item, parent, ordinals)
            _add_child(graph, parent, Node(
                address=address, kind=kind,
                text=textwrap.dedent("\n".join(item.lines)),
                start_line=item.start_line, end_line=item.end_line,
                file=file, mode=_run_mode(item) if kind == NodeKind.RUN
                else None, name=name,
            ), document_name=name is not None)


def _add_tests(
    graph:   NameGraph,
    section: TestsSection,
    parent:  str,
    file:    str | None,
) -> None:
    """Add the ``#Tests`` section, named in the scope of the node at
    *parent*, to it, and what it holds."""
    tests_addr = named_address(graph.scope_of(parent), "Tests")
    _add_child(graph, parent, Node(
        address=tests_addr, kind=NodeKind.TESTS,
        start_line=section.start_line, end_line=section.end_line,
        file=file,
    ))
    _add_assertions(
        graph, section.items, section.line_offsets or {}, tests_addr, file)


def _add_assertions(
    graph:   NameGraph,
    items:   list,
    offsets: dict,
    parent:  str,
    file:    str | None,
) -> None:
    """Add the items of ``#Tests`` or of a group as children of *parent*.

    A run of bare assertion lines is consecutive bare lines (blank ones
    included). It is one ``TEST_LINES`` node, from its first to its
    last non-blank line and holding those lines as written; a run of only
    blank lines is nothing. A ``##group`` is a ``TEST_GROUP`` and a
    ``~test`` a ``TEST``, which has its name. *offsets* maps an item's
    index to its line.
    """
    ordinals = _Ordinals()
    i = 0
    while i < len(items):
        item = items[i]
        if isinstance(item, str):
            j = i
            while j < len(items) and isinstance(items[j], str):
                j += 1
            lit = [k for k in range(i, j) if items[k].strip()]
            if lit:
                first, last = lit[0], lit[-1]
                address = _positional_identity(
                    parent, NodeKind.TEST_LINES,
                    ordinals.next(NodeKind.TEST_LINES))
                _add_child(graph, parent, Node(
                    address=address,
                    kind=NodeKind.TEST_LINES,
                    text="\n".join(items[first:last + 1]),
                    start_line=offsets.get(first),
                    end_line=offsets.get(last), file=file,
                ))
            i = j
            continue
        if isinstance(item, ProseBlock):
            _add_prose(
                graph, parent, item, ordinals.next(NodeKind.PROSE), file)
        elif isinstance(item, TestGroup):
            group_addr = named_address(graph.scope_of(parent), item.title)
            _add_child(graph, parent, Node(
                address=group_addr,
                kind=NodeKind.TEST_GROUP,
                start_line=item.start_line, end_line=item.end_line,
                file=file, name=item.title,
            ), document_name=True)
            _add_assertions(
                graph, item.items, item.line_offsets or {}, group_addr,
                file)
        elif isinstance(item, NamedTest):
            # One address per ~test block (`group#name`), as ~example's:
            # every assertion line in it shares that address.
            _add_child(graph, parent, Node(
                address=named_address(graph.scope_of(parent), item.name),
                kind=NodeKind.TEST,
                text="\n".join(item.lines).rstrip(),
                start_line=item.start_line, end_line=item.end_line,
                file=file, name=item.name,
            ), document_name=True)
        i += 1


# ── Symbol enrichment ────────────────────────────────────────

def enrich(
    graph:         NameGraph,
    module:        Module,
    extractor:     Extractor,
    split_imports: ImportSplitter | None = None,
) -> None:
    """Enrich a graph made by :func:`build` with symbol nodes, and the
    import statements of the bound language.

    Reads the graph: every ``CODE`` leaf and every ``PROPERTY`` node in
    the module's tree, wherever it is written (a subheading, an
    ``#Appendix`` or one of its subheadings too), and extracts symbols
    from its text with the provided language-specific extractor.  A
    symbol is contained by the ``CODE`` leaf it is written in, and the
    functions a ``~property`` defines by its ``PROPERTY`` node.  The
    lines of ``#References`` that list no module are split into
    statements by *split_imports* (the binding's rule for where a
    statement ends; one statement for each non-blank line when there is
    none), and each is an ``IMPORT`` node in the section.  *module* is
    used for its address and its ``#References``.

    The symbol's address is that of its scope and its name: a code
    block's is module-scoped,
        roman/numerals#from_roman
    even when defined inside ##Decoding, and a ``~property``'s is the
    property's own.

    Raises AddressCollisionError if a symbol name collides with an
    existing node of another kind in the same module (a subheading, say).
    """
    mod_addr = module_address(module.title)
    for holder in _descendants(graph, mod_addr):
        if holder.kind == NodeKind.CODE:
            first = holder.start_line
        elif holder.kind == NodeKind.PROPERTY:
            first = (None if holder.start_line is None
                     else holder.start_line + 1)
        else:
            continue
        scope = graph.scope_of(holder.address)
        for info in extractor((holder.text or "").split("\n")):
            if holder.kind == NodeKind.PROPERTY and info.name == "_":
                continue
            _add_child(graph, holder.address, _symbol_node(
                named_address(scope, info.name), info, holder, first,
                holder.file))
    _add_imports(graph, module, split_imports or default_split_imports)


def _add_imports(
    graph: NameGraph, module: Module, split_imports: ImportSplitter,
) -> None:
    """Add an ``IMPORT`` node to the ``#References`` node of *module* for
    each statement *split_imports* finds in its import lines, and put the
    section's children in the order they are written."""
    if module.post_text is None:
        return
    section = next((s for s in module.post_text.sections
                    if isinstance(s, ReferencesSection)), None)
    node = graph.post_section(
        module_address(module.title), NodeKind.REFERENCES)
    if section is None or node is None:
        return
    ordinals = _Ordinals()
    for text, first_line in split_imports(section.imports):
        address = _positional_identity(
            node.address, NodeKind.IMPORT, ordinals.next(NodeKind.IMPORT))
        _add_child(graph, node.address, Node(
            address=address, kind=NodeKind.IMPORT, text=text,
            start_line=first_line,
            end_line=(None if first_line is None
                      else first_line + text.count("\n")),
            file=node.file,
        ))
    in_order = sorted(graph.children(node.address),
                      key=lambda child: child.start_line or 0)
    for child in in_order:
        graph.release(child.address)
        graph.add_edge(Edge(
            source=node.address, target=child.address,
            kind=EdgeKind.CONTAINS))


def _symbol_node(
    address: str, info: SymbolInfo, holder, first: int | None,
    file: str | None,
) -> Node:
    """The node of the symbol *info*, written in the code block or claim
    *holder*, whose first line of code is line *first* of the file.

    The node takes the symbol's own lines and holds no text: it is read
    from what holds it (see :meth:`NameGraph.text`). A symbol the binding
    gave no lines for keeps its source and the first line of *holder*.
    """
    if info.first_line is None or first is None:
        return Node(
            address=address, kind=NodeKind.SYMBOL,
            text=info.source,
            start_line=holder.start_line, end_line=holder.end_line,
            file=file, name=info.name)
    last = info.first_line if info.last_line is None else info.last_line
    return Node(
        address=address, kind=NodeKind.SYMBOL,
        start_line=first + info.first_line - 1, end_line=first + last - 1,
        file=file, name=info.name)


def _descendants(graph: NameGraph, address: str) -> list[Node]:
    """The nodes below the node at *address*, parents before children,
    in document order. A list, so the graph can be added to as it is
    read."""
    found: list[Node] = []
    for child in graph.children(address):
        found.append(child)
        found.extend(_descendants(graph, child.address))
    return found


def add_source(graph: NameGraph, module: Module) -> None:
    """Keep the text *module* was parsed from (its ``source``), the file
    the bodies of its nodes are lines of (see :func:`bodies`). A module
    with no ``source`` has no bodies."""
    address = module_address(module.title)
    if module.source is not None and graph.node(address) is not None:
        graph._sources[address] = module.source.split("\n")


def bodies(graph: NameGraph, shown: set[str]) -> dict[str, str]:
    """The body of each node of *shown* that has one, by the line rule: a
    line is in the body of the written node that holds it, and where
    *shown* does not have that node, in the body of the deepest node it has
    that covers the line (a node covers the lines from its ``start_line``
    to its ``end_line``). A body is the lines as they are in the file,
    indent and all, less blank lines at either end; a blank line inside it
    stays in it, and one between two nodes is in neither. So a heading's
    body is its line, and a claim's its sigil line and the lines under it.

    A node whose text is lines of the node that holds it (a ``SYMBOL``) is
    derived: it has the lines its holder, when *shown* has it, has not. An
    ``EXTERNAL`` has no lines, so no body. Nothing is given for a module
    whose source was not kept (see :func:`add_source`)."""
    by_module: dict[str, list[Node]] = {}
    for address in shown:
        node = graph.node(address)
        module = graph.module_of(address)
        if (node is None or module is None or node.start_line is None
                or node.end_line is None):
            continue
        by_module.setdefault(module, []).append(node)
    found: dict[str, str] = {}
    for module, nodes in by_module.items():
        source = graph._sources.get(module)
        if source is not None:
            found.update(_bodies_of(graph, nodes, source))
    return found


def _bodies_of(
    graph: NameGraph, nodes: list[Node], source: list[str],
) -> dict[str, str]:
    """The bodies of *nodes*, all of one module, whose file is the lines
    *source* (see :func:`bodies`)."""
    def depth(node: Node) -> int:
        steps, above = 0, graph.parent_of(node.address)
        while above is not None:
            steps, above = steps + 1, graph.parent_of(above.address)
        return steps

    holder: dict[int, str] = {}
    written = [n for n in nodes if not KINDS[n.kind].text_in_holder]
    derived = [n for n in nodes if KINDS[n.kind].text_in_holder]
    ordered = [*sorted(written, key=lambda n: -depth(n)),
               *sorted(derived, key=lambda n: n.end_line - n.start_line)]
    for node in ordered:
        for number in range(node.start_line, node.end_line + 1):
            if number <= len(source):
                holder.setdefault(number, node.address)
    held: dict[str, list[int]] = {}
    for number in sorted(holder):
        held.setdefault(holder[number], []).append(number)
    found: dict[str, str] = {}
    for address, numbers in held.items():
        while numbers and not source[numbers[0] - 1].strip():
            numbers.pop(0)
        while numbers and not source[numbers[-1] - 1].strip():
            numbers.pop()
        if numbers:
            found[address] = "\n".join(source[n - 1] for n in numbers)
    return found


def claims_to_run(graph: NameGraph, module_address_: str) -> list[ClaimToRun]:
    """The claims and tests of the module at *module_address_*, for a
    binding to run, in document order.

    This is the one place they are collected. It reads the module's tree
    wherever a claim is written: the body, subheadings, each ``#Appendix``
    and its subheadings, and ``#Tests`` and its groups. An ``~example``,
    a ``~property``, a ``~run``, a ``~test`` and a run of bare assertions
    (``TEST_LINES``) are reported at their own address, and commentary
    ends a run. Lines are
    the node's text, one for each file line, and ``first_line`` is the line
    of the first (the one after the ``~sigil``, or a run's own first line,
    which has no sigil).
    """
    found: list[ClaimToRun] = []
    for node in _descendants(graph, module_address_):
        if not KINDS[node.kind].runnable:
            continue
        address, sigil_line = node.address, node.start_line
        first_line = (None if node.start_line is None
                      else node.start_line + 1)
        if node.kind == NodeKind.TEST_LINES:
            sigil_line, first_line = None, node.start_line
        text = graph.text(node.address) or ""
        lines = text.split("\n")
        while lines and not lines[-1].strip():
            lines.pop()                 # the blank lines after it
        found.append(ClaimToRun(
            address=address, kind=node.kind.name, lines=lines,
            first_line=first_line, sigil_line=sigil_line,
            name=node.name, mode=node.mode,
        ))
    return found


def add_cites_edges(graph: NameGraph) -> None:
    """Populate CITES edges from prose ``#Label`` cross-references.

    Reads the references each ``PROSE`` leaf holds (``Node.refs``) and
    resolves each against the graph in the module the leaf is written
    in.  A resolved reference becomes an ``EdgeKind.CITES`` edge
    from the leaf that holds it to the node it names: one edge for each
    leaf and target, carrying every line a reference to it is written on.

    Must be called after all ``enrich()`` and IMPORTS passes so that
    ``graph.resolve()`` has the full import context available.
    """
    cited: dict[tuple[str, str], set[int]] = {}
    for leaf in list(graph.nodes(kind=NodeKind.PROSE)):
        context = graph.module_of(leaf.address)
        if context is None:
            continue
        for ref in leaf.refs:
            target = graph.resolve(ref.label, context=context)
            if target is None:
                continue
            lines = cited.setdefault((leaf.address, target.address), set())
            if ref.start_line is not None:
                lines.add(ref.start_line)
    for (source, target), lines in cited.items():
        graph.add_edge(Edge(
            source=source, target=target, kind=EdgeKind.CITES,
            lines=tuple(sorted(lines))))


def _scanned_text(
    graph: NameGraph, node: Node,
) -> tuple[str | None, int | None]:
    """The text a call extractor reads for *node*, dedented, and the file
    line its first line is on.

    A symbol's text, from the line the symbol starts on. A claim's or a
    named test's lines, without the blank ones before the first, from the
    first that has text: they begin on the line after the sigil. A run of
    bare assertions (``TEST_LINES``), from its own first line. A group
    and ``#Tests`` hold tests, which are read on their own.
    """
    if node.kind == NodeKind.SYMBOL:
        return graph.text(node.address), node.start_line
    if node.kind == NodeKind.TEST_LINES:
        return textwrap.dedent(node.text or ""), node.start_line
    if KINDS[node.kind].runnable:
        lines = (node.text or "").split("\n")
        blank = next((i for i, text in enumerate(lines) if text.strip()),
                     len(lines))
        first = None if node.start_line is None else node.start_line + 1
        return (textwrap.dedent("\n".join(lines[blank:])),
                None if first is None else first + blank)
    return None, None


def add_uses_edges(
    graph:          NameGraph,
    call_extractor: Callable[[str], list[tuple[str, int]]],
) -> None:
    """Populate USES edges from statically visible symbol references.

    Builds a name → address index from all SYMBOL nodes, then for each
    node that holds code (a symbol, a claim, a named test, or one of the
    runs of bare assertions in ``#Tests``, each on its own), calls
    *call_extractor* on its text and adds a ``EdgeKind.USES`` edge for
    every returned name that resolves to a known symbol address.

    Each edge carries ``lines``, every line a name is used on in the .lob
    file, each once and in order: the line the scanned text starts on,
    plus the line in that text, less one.  When no line is known there are
    none.

    Both intra-module and cross-module references are handled identically:
    the lookup is name-based across the whole graph.  Unresolved names
    (builtins, parameters, dynamic calls) produce no edge and no error.

    Must be called after all ``enrich()`` passes so the full symbol index
    is available.
    """
    # Build name → [address] index over all known symbols.
    name_index: dict[str, list[str]] = {}
    for node in graph.nodes(kind=NodeKind.SYMBOL):
        name_index.setdefault(node.name, []).append(node.address)

    # used: (source_addr, target_addr) → the lines it is used on, none when
    # they are not known
    used: dict[tuple[str, str], set[int]] = {}
    for node in (
        *graph.nodes(kind=NodeKind.SYMBOL),
        *(n for n in graph.nodes() if KINDS[n.kind].runnable),
    ):
        source, base = _scanned_text(graph, node)
        if not source:
            continue
        for ref_name, src_line in call_extractor(source):
            for target_addr in name_index.get(ref_name, []):
                lines = used.setdefault((node.address, target_addr), set())
                if base is not None:
                    lines.add(base + (src_line - 1))

    for (src_addr, tgt_addr), lines in used.items():
        graph.add_edge(Edge(
            source=src_addr,
            target=tgt_addr,
            kind=EdgeKind.USES,
            lines=tuple(sorted(lines)),
        ))


def sigil_of(node: Node) -> str:
    """The sigil that begins the node in its file (``~example``,
    ``~property``, ``~run`` or ``~test``), or ``""`` for a node with
    none."""
    return KINDS[node.kind].sigil or ""


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

    Reads the graph: every ``PROSE`` leaf in the module's tree (the
    body, its subheadings, each ``#Appendix`` and its subheadings, and
    the commentary in ``#Tests`` and its groups), and calls
    :meth:`NameGraph.resolve` on each :class:`~notlob.model.Ref` it
    holds.  *module* is used only for its address.  An error is located
    at the subheading the paragraph is written in, and at the module for
    a paragraph written anywhere else.

    ``#Label`` references are validated via the full three-step
    resolution order.  ``##Label`` references are validated against
    subheadings of the current module only.

    An unresolved reference is a first-class error; the returned list
    is empty when all references resolve.
    """
    mod_addr = module_address(module.title)
    errors: list[RefError] = []
    for leaf in _descendants(graph, mod_addr):
        if leaf.kind != NodeKind.PROSE:
            continue
        holder = graph.parent_of(leaf.address)
        location = (holder.address
                    if holder is not None and holder.kind == NodeKind.SUBHEADING
                    else mod_addr)
        errors.extend(
            RefError(location=location, ref=ref) for ref in leaf.refs
            if not _resolves(graph, ref, mod_addr))
    return errors


def _resolves(graph: NameGraph, ref: Ref, mod_addr: str) -> bool:
    """Return True if *ref* resolves against *graph* in *mod_addr*."""
    if ref.sub:
        # ##Label: only a subheading of the current module
        node = graph.node(named_address(mod_addr, ref.label))
        return node is not None and node.kind == NodeKind.SUBHEADING
    return graph.resolve(ref.label, context=mod_addr) is not None
