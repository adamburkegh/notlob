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
``##group`` in it, are scopes) and its name, and an anonymous one by its
kind and position among its siblings of that kind
(:func:`anonymous_address`).  What each kind is, such as whether it opens
a scope, is stated once in :data:`KINDS`:

  Module:     title → lowercase, spaces → slashes
              "Pricing Discounts" → "pricing/discounts"

  Subheading: module_address + "#" + label  (label preserved as-is)
              "pricing/discounts#Stacking Discounts"

  Symbol:     module_address + "#" + name, wherever in the module it is
              written: "pricing/discounts#apply_discount"

  Anonymous:  parent_address + "#" + kind + "#" + n, counted from 1
              "pricing/discounts#prose#2", "pricing/discounts#example#1"

Addresses are machine identifiers; labels are the human-readable names as
written in source.  A name collision between nodes of different kinds
(a symbol and a subheading in one module) is an error: all named things
share one namespace per module.  The post-text (what follows ``---``) is
a node in the tree but no part of an address: ``#Tests`` and the
appendices are addressed as if they hung from the module.

This scheme is isomorphic to URI fragment addressing.

Edge vocabulary
---------------
  CONTAINS      — parent → child, where a node is written; the tree
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
import json
import re
import textwrap
from dataclasses import dataclass, field, replace
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


def anonymous_address(parent: str, kind: NodeKind, n: int) -> str:
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
        raise ValueError(f"{kind.name} nodes are named, not anonymous")
    address = f"{parent}#{facts.segment}"
    return f"{address}#{n}" if facts.numbered else address


# ── Node ─────────────────────────────────────────────────────

class NodeKind(Enum):
    """What a node is. A kind says what the node is, not whether it is
    named: ``PROPERTY`` and ``TEST`` cover the named and the anonymous."""
    MODULE     = auto()    # a .lob file: the root of its tree
    SUBHEADING = auto()    # a ##Subheading
    SYMBOL     = auto()    # a name defined in code: function, class, constant
    PROPERTY   = auto()    # a ~property claim, named or not
    EXAMPLE    = auto()    # an ~example claim
    RUN        = auto()    # a ~run claim, of any mode
    TEST       = auto()    # a test: a ~test, or a run of bare assertions
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


@dataclass(frozen=True)
class KindFacts:
    """What is true of every node of a kind. A kind is an adjective, and
    each of these is one the code asks in more than one place.

    opens_scope      a name written in a node of this kind belongs to it
    claim            an ``~example``, ``~property`` or ``~run``
    runnable         a binding runs it: a claim, or a test
    hidden_at_outline
                     the ``outline`` leaves it out, and moves its edges to
                     the section that holds it: a paragraph, code block,
                     bullet list, listing, import statement or declaration,
                     and the region after the ``---``
    section          a section of the document
    region           a region of the tree, no part of an address
    text_in_holder   its text is lines of the node that holds it
    segment          its part of an address when it is anonymous; ``None``
                     for a kind that is always named
    numbered         an anonymous address has an ordinal after the segment
    sigil            the sigil that begins it in its file, ``None`` for a kind
                     with none
    sigil_needs_name it has its sigil only if the document names it: a
                     test is written ``~test name``, but a run of bare
                     assertions has no sigil
    """
    opens_scope:    bool = False
    claim:          bool = False
    runnable:       bool = False
    hidden_at_outline: bool = False
    section:        bool = False
    region:         bool = False
    text_in_holder: bool = False
    segment:        str | None = None
    numbered:       bool = False
    sigil:          str | None = None
    sigil_needs_name: bool = False


#: The facts of each kind, one row for every :class:`NodeKind`.
KINDS: dict[NodeKind, KindFacts] = {
    NodeKind.MODULE: KindFacts(opens_scope=True),
    NodeKind.SUBHEADING: KindFacts(section=True),
    NodeKind.SYMBOL: KindFacts(text_in_holder=True),
    NodeKind.PROPERTY: KindFacts(
        opens_scope=True, claim=True, runnable=True,
        segment="property", numbered=True, sigil="~property"),
    NodeKind.EXAMPLE: KindFacts(
        claim=True, runnable=True, segment="example", numbered=True,
        sigil="~example"),
    NodeKind.RUN: KindFacts(
        claim=True, runnable=True, segment="run", numbered=True,
        sigil="~run"),
    NodeKind.TEST: KindFacts(
        runnable=True, segment="test", numbered=True,
        sigil="~test", sigil_needs_name=True),
    NodeKind.EXTERNAL: KindFacts(),
    NodeKind.PROSE: KindFacts(
        hidden_at_outline=True, segment="prose", numbered=True),
    NodeKind.CODE: KindFacts(
        hidden_at_outline=True, segment="code", numbered=True),
    NodeKind.BULLETS: KindFacts(
        hidden_at_outline=True, segment="bullets", numbered=True),
    NodeKind.APPENDIX: KindFacts(
        section=True, segment="appendix", numbered=True),
    NodeKind.TESTS: KindFacts(opens_scope=True),
    NodeKind.POST_TEXT: KindFacts(
        hidden_at_outline=True, region=True, segment="post-text"),
    NodeKind.TEST_GROUP: KindFacts(opens_scope=True),
    NodeKind.REFERENCES: KindFacts(),
    NodeKind.BINDING: KindFacts(),
    NodeKind.LISTING: KindFacts(
        hidden_at_outline=True, segment="listing", numbered=True),
    NodeKind.IMPORT: KindFacts(
        hidden_at_outline=True, segment="import", numbered=True),
    NodeKind.DECLARATION: KindFacts(
        hidden_at_outline=True, segment="declaration", numbered=True),
}


@dataclass(frozen=True)
class Node:
    """A node in the name-graph: one element of a ``.lob`` file.

    address     globally unique machine identifier (tooling-derived)
    label       human-readable name as written in source
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
    name        the name written in the document for a heading, a
                ``##group``, a ``~property`` or a ``~test``; ``None`` for
                an anonymous node (an unnamed ``~property``, a run of
                bare assertions) and for what a document does not name

    The fields after ``kind`` are excluded from equality and hash, so two
    nodes with the same address, label and kind are the same node.
    """
    address: str
    label:   str
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
    """How two nodes relate. Only ``CONTAINS`` makes the tree."""
    CONTAINS      = auto()   # parent to child: where a node is written
    IMPORTS      = auto()   # module to module, from a #References line
    USES_EXTERNAL = auto()   # binding module to a file it declares
    USES          = auto()   # code to a symbol it refers to by name
    CITES         = auto()   # a paragraph to the node a #Label in it names


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


#: The namespace of the vocabulary, declared in ``schema/notlob.ttl``.
_TURTLE_NAMESPACE = "urn:notlob:ns:"


def turtle_class_name(kind: NodeKind) -> str:
    """The name of the ontology class of the nodes of *kind*, in
    UpperCamelCase as RDF classes are named: ``Module``, ``PostText``,
    ``TestGroup``. The emitter, the ontology and the guard on them all
    take the name from here."""
    return "".join(word.capitalize() for word in kind.name.split("_"))


def _turtle_node(node: dict) -> list[str]:
    """The lines that write *node*, an entry of the document, as one
    Turtle subject."""
    parts = [f"notlob:address {_turtle_lit(node['address'])}"]
    if "label" in node:
        parts.insert(0, f"rdfs:label {_turtle_lit(node['label'])}")
    if node.get("named"):
        parts.append("notlob:named true")
    for key in ("mode", "declares", "value"):
        if key in node:
            parts.append(f"notlob:{key} {_turtle_lit(node[key])}")
    if "file" in node:
        parts.append(f"notlob:file {_turtle_lit(node['file'])}")
    for key, prop in (("start_line", "startLine"), ("size", "size")):
        if key in node:
            parts.append(f"notlob:{prop} {node[key]}")
    for ref in node.get("refs", []):
        inner = [f"rdfs:label {_turtle_lit(ref['label'])}",
                 f"notlob:sub {'true' if ref['sub'] else 'false'}"]
        if ref["start_line"] is not None:
            inner.append(f"notlob:startLine {ref['start_line']}")
        parts.append(f"notlob:ref [ {' ; '.join(inner)} ]")
    if "text" in node:
        parts.append(f"notlob:text {_turtle_long_lit(node['text'])}")
    kind = turtle_class_name(NodeKind[node["kind"]])
    lines = [f"{_turtle_iri(node['address'])} a notlob:{kind} ;"]
    lines += [f"    {part} ;" for part in parts]
    lines[-1] = lines[-1][:-2] + " ."
    return lines


# ── Graph ────────────────────────────────────────────────────

class AddressCollisionError(ValueError):
    """Two nodes claim the same address: two differently-kinded ones, or
    two of a name written in the document (a heading, a ``~property`` or
    a ``~test`` name) in one scope.

    Raised by :meth:`NameGraph.add_node` for kinds, and by :func:`build`
    for a restated document name -- e.g. a ``##Layout`` subheading and a
    ``class Layout`` symbol in the same module both resolve to
    ``mod#Layout``, as do two ``##Layout`` subheadings. A symbol written
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
        label:   str,
        context: str | None = None,
    ) -> Node | None:
        """Resolve a #label reference to a node.

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
            node = self._nodes.get(named_address(context, label))
            if node is not None:
                if node.kind in (NodeKind.SYMBOL, NodeKind.SUBHEADING):
                    return node
            # Step 3: a module the current module lists
            for target in self.imports_of(context):
                if target.label == label:
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

    def to_dict(self, level: str | int = "outline") -> dict:
        """The graph as a document: a plain dict of the shape described by
        ``notlob/schema/name_graph.json``.

        *level* is how much it shows, by name or by number (see
        :data:`LEVELS`):

        * ``outline`` (1): every node but the anonymous leaves
          (paragraphs, code blocks, bullet lists) and the region after
          the ``---``, with an edge to or from one of those moved to the
          section that holds it.
        * ``index`` (2): every node, the references a paragraph holds, and
          a ``size`` for each node.
        * ``full`` (3): and the ``text`` of each node that holds text,
          once.

        ``nodes`` is in the order the files are written, and the
        ``CONTAINS`` edges, one into each node but a module and an
        ``EXTERNAL``, in that order too. Only a module has a ``label`` and
        a ``file``.

        Raises ``ValueError`` for a level that is none of these.
        """
        level = parse_level(level)
        return {
            "version": DOCUMENT_VERSION,
            "level":   level,
            "nodes":   _document_nodes(self, level),
            "edges":   _document_edges(self, level),
        }

    def to_json(
        self,
        indent: int | None = 2,
        level: str | int = "outline",
    ) -> str:
        """Serialise the graph to a JSON string.

        *indent* controls pretty-printing; pass ``None`` for compact
        single-line output.  *level* is forwarded to :meth:`to_dict`.
        """
        return json.dumps(
            self.to_dict(level=level), indent=indent, ensure_ascii=False)

    def to_turtle(
        self,
        base: str | None = None,
        level: str | int = "outline",
    ) -> str:
        """Serialise the graph as RDF in Turtle syntax.

        It writes the nodes and edges that :meth:`to_dict` does at the
        same *level* (see there for what each level shows), with the
        edges lifted the same way, the tree among them as
        ``notlob:contains`` triples. Only a module has an
        ``rdfs:label`` and a ``notlob:file``. A node's ``named``, ``mode`` and
        ``size``, a paragraph's references (``notlob:ref``) and a node's
        ``text`` are written as the level gives them; an edge is a triple
        without its line, which RDF has no place for (the JSON carries
        it).

        The vocabulary (``notlob:``) is declared in
        ``notlob/schema/notlob.ttl`` under the informal ``urn:notlob:ns:``
        namespace. Node addresses become relative IRI references (see
        :func:`_turtle_iri`), so they resolve against wherever the
        document is loaded; pass *base* to emit an ``@base`` and put the
        project's nodes under an IRI of your own. There is no default
        base: project data does not belong in notlob's namespace.

        No external dependency — Turtle is emitted as plain strings.
        """
        level = parse_level(level)
        lines = [f"@base <{base}> ."] if base else []
        lines += [
            f"@prefix notlob: <{_TURTLE_NAMESPACE}> .",
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
            "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
            "",
        ]
        nodes = _document_nodes(self, level)
        for node in nodes:
            lines += _turtle_node(node)
            lines.append("")
        for edge in _document_edges(self, level):
            lines.append(
                f"{_turtle_iri(edge['source'])} "
                f"notlob:{edge['kind'].lower()} "
                f"{_turtle_iri(edge['target'])} ."
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
    """Counts the anonymous nodes of one parent, per kind, from 1."""

    def __init__(self) -> None:
        self._n: dict[NodeKind, int] = {}

    def next(self, kind: NodeKind) -> int:
        self._n[kind] = self._n.get(kind, 0) + 1
        return self._n[kind]


def _anonymous_identity(
    parent: str, kind: NodeKind, n: int,
) -> tuple[str, str]:
    """``(address, label)`` of the *n*th anonymous node of *kind* written
    in the node at *parent*."""
    return anonymous_address(parent, kind, n), f"{KINDS[kind].segment}#{n}"


def _container(graph: NameGraph, address: str) -> str:
    """The address of the nearest node at or above *address* that is not a
    region of the tree: the one an anonymous node written in a region is
    addressed from."""
    node = graph.node(address)
    while KINDS[node.kind].region:
        node = graph.parent_of(node.address)
    return node.address


def _claim_identity(
    graph: NameGraph, claim: Claim, parent: str, ordinals: _Ordinals,
) -> tuple[str, str, NodeKind]:
    """``(address, label, kind)`` of *claim* written in the node at
    *parent*. The kind follows the sigil: every ``~run`` (bare, ``on-load``
    or ``on-invocation``) is a ``RUN``, ``~example`` an ``EXAMPLE`` and
    anything else a ``PROPERTY``. A named property is named in the scope
    of *parent* but still counts among its properties."""
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
        return named_address(graph.scope_of(parent), name), name, kind
    return (*_anonymous_identity(parent, kind, n), kind)


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
    A *document_name* (a heading, a ``~property`` or ``~test`` name) is
    written once in its scope, so a second is a collision: raised, or
    collected when :func:`build` was given a list to collect them in, in
    which case it replaces the first."""
    if document_name:
        node = replace(node, name=node.label)
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
    address, label = _anonymous_identity(parent, NodeKind.PROSE, n)
    _add_child(graph, parent, Node(
        address=address, label=label,
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
    ``~property`` or two ``~test`` names) raises
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
        address=addr, label=module.title, kind=NodeKind.MODULE,
        start_line=module.start_line, end_line=module.end_line, file=file,
    ))
    _add_items(graph, module.body, addr, file)

    post_text = module.post_text
    if post_text is None:
        return
    post_addr = anonymous_address(addr, NodeKind.POST_TEXT, 1)
    _add_child(graph, addr, Node(
        address=post_addr, label="post-text", kind=NodeKind.POST_TEXT,
        start_line=post_text.start_line, end_line=post_text.end_line,
        file=file,
    ))
    ordinals = _Ordinals()
    for section in post_text.sections:
        if isinstance(section, AppendixSection):
            app_addr = anonymous_address(
                _container(graph, post_addr), NodeKind.APPENDIX,
                ordinals.next(NodeKind.APPENDIX))
            _add_child(graph, post_addr, Node(
                address=app_addr,
                label=section.title.lstrip("#").strip(),
                kind=NodeKind.APPENDIX,
                start_line=section.start_line, end_line=section.end_line,
                file=file,
            ))
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
        address=address, label="References", kind=NodeKind.REFERENCES,
        start_line=section.start_line, end_line=section.end_line,
        file=file,
    ))
    ordinals = _Ordinals()
    for listing in section.listings:
        listing_address, label = _anonymous_identity(
            address, NodeKind.LISTING, ordinals.next(NodeKind.LISTING))
        _add_child(graph, address, Node(
            address=listing_address, label=label, kind=NodeKind.LISTING,
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
        address=address, label="Binding", kind=NodeKind.BINDING,
        start_line=section.start_line, end_line=section.end_line,
        file=file,
    ))
    ordinals = _Ordinals()
    for declaration in section.declarations:
        decl_address, label = _anonymous_identity(
            address, NodeKind.DECLARATION,
            ordinals.next(NodeKind.DECLARATION))
        _add_child(graph, address, Node(
            address=decl_address, label=label, kind=NodeKind.DECLARATION,
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
                address=sub_addr, label=item.title,
                kind=NodeKind.SUBHEADING,
                start_line=item.start_line, end_line=item.end_line,
                file=file,
            ), document_name=True)
            _add_items(graph, item.body, sub_addr, file)
        elif isinstance(item, ProseBlock):
            _add_prose(
                graph, parent, item, ordinals.next(NodeKind.PROSE), file)
        elif isinstance(item, CodeBlock):
            address, label = _anonymous_identity(
                parent, NodeKind.CODE, ordinals.next(NodeKind.CODE))
            _add_child(graph, parent, Node(
                address=address, label=label,
                kind=NodeKind.CODE,
                text=textwrap.dedent("\n".join(item.lines)),
                start_line=item.start_line, end_line=item.end_line,
                file=file,
            ))
        elif isinstance(item, BulletBlock):
            address, label = _anonymous_identity(
                parent, NodeKind.BULLETS, ordinals.next(NodeKind.BULLETS))
            _add_child(graph, parent, Node(
                address=address, label=label,
                kind=NodeKind.BULLETS, text="\n".join(item.items),
                start_line=item.start_line, end_line=item.end_line,
                file=file,
            ))
        elif isinstance(item, Claim):
            address, label, kind = _claim_identity(
                graph, item, parent, ordinals)
            _add_child(graph, parent, Node(
                address=address, label=label, kind=kind,
                text=textwrap.dedent("\n".join(item.lines)),
                start_line=item.start_line, end_line=item.end_line,
                file=file, mode=_run_mode(item) if kind == NodeKind.RUN
                else None,
            ), document_name=(kind == NodeKind.PROPERTY
                              and len(item.sigil.split()) > 1))


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
        address=tests_addr, label="Tests", kind=NodeKind.TESTS,
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
    included). It is one anonymous ``TEST`` node, from its first to its
    last non-blank line and holding those lines as written; a run of only
    blank lines is nothing. A ``##group`` is a ``TEST_GROUP`` and a
    ``~test`` a named ``TEST``. *offsets* maps an item's index to its
    line.
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
                address, label = _anonymous_identity(
                    parent, NodeKind.TEST, ordinals.next(NodeKind.TEST))
                _add_child(graph, parent, Node(
                    address=address, label=label,
                    kind=NodeKind.TEST,
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
                address=group_addr, label=item.title,
                kind=NodeKind.TEST_GROUP,
                start_line=item.start_line, end_line=item.end_line,
                file=file,
            ), document_name=True)
            _add_assertions(
                graph, item.items, item.line_offsets or {}, group_addr,
                file)
        elif isinstance(item, NamedTest):
            # One address per ~test block (`group#name`), as ~example's:
            # every assertion line in it shares that address.
            _add_child(graph, parent, Node(
                address=named_address(graph.scope_of(parent), item.name),
                label=item.name, kind=NodeKind.TEST,
                text="\n".join(item.lines).rstrip(),
                start_line=item.start_line, end_line=item.end_line,
                file=file,
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
        address, label = _anonymous_identity(
            node.address, NodeKind.IMPORT, ordinals.next(NodeKind.IMPORT))
        _add_child(graph, node.address, Node(
            address=address, label=label, kind=NodeKind.IMPORT, text=text,
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
            address=address, label=info.name, kind=NodeKind.SYMBOL,
            text=info.source,
            start_line=holder.start_line, end_line=holder.end_line,
            file=file)
    last = info.first_line if info.last_line is None else info.last_line
    return Node(
        address=address, label=info.name, kind=NodeKind.SYMBOL,
        start_line=first + info.first_line - 1, end_line=first + last - 1,
        file=file)


def _descendants(graph: NameGraph, address: str) -> list[Node]:
    """The nodes below the node at *address*, parents before children,
    in document order. A list, so the graph can be added to as it is
    read."""
    found: list[Node] = []
    for child in graph.children(address):
        found.append(child)
        found.extend(_descendants(graph, child.address))
    return found


def claims_to_run(graph: NameGraph, module_address_: str) -> list[ClaimToRun]:
    """The claims and tests of the module at *module_address_*, for a
    binding to run, in document order.

    This is the one place they are collected. It reads the module's tree
    wherever a claim is written: the body, subheadings, each ``#Appendix``
    and its subheadings, and ``#Tests`` and its groups. An ``~example``,
    a ``~property``, a ``~run``, a ``~test`` and a run of bare assertions
    are reported at their own address, and commentary ends a run. Lines are
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
        if _is_anonymous_test(node):
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
    leaf and target, carrying the line of the first reference to it.

    Must be called after all ``enrich()`` and IMPORTS passes so that
    ``graph.resolve()`` has the full import context available.
    """
    seen: set[tuple[str, str]] = set()
    for leaf in list(graph.nodes(kind=NodeKind.PROSE)):
        context = graph.module_of(leaf.address)
        if context is None:
            continue
        for ref in leaf.refs:
            target = graph.resolve(ref.label, context=context)
            if target is None:
                continue
            key = (leaf.address, target.address)
            if key not in seen:
                graph.add_edge(Edge(
                    source=leaf.address,
                    target=target.address,
                    kind=EdgeKind.CITES,
                    start_line=ref.start_line,
                ))
                seen.add(key)


def _is_anonymous_test(node: Node) -> bool:
    """Whether *node* is an anonymous test, a run of bare assertion lines,
    and not a named one (``~test <name>``).

    Told apart by whether the document names it: a named test records
    its name (``Node.name``). What the node is called cannot tell them
    apart, as a name is free text (``~test test#1``), and neither can its
    lines, which a module built by hand may lack.
    """
    return node.kind == NodeKind.TEST and node.name is None


def _scanned_text(
    graph: NameGraph, node: Node,
) -> tuple[str | None, int | None]:
    """The text a call extractor reads for *node*, dedented, and the file
    line its first line is on.

    A symbol's text, from the line the symbol starts on. A claim's or a
    named test's lines, without the blank ones before the first, from the
    first that has text: they begin on the line after the sigil. A run of
    bare assertions (an anonymous test), from its own first line. A group
    and ``#Tests`` hold tests, which are read on their own.
    """
    if node.kind == NodeKind.SYMBOL:
        return graph.text(node.address), node.start_line
    if node.kind == NodeKind.TEST and _is_anonymous_test(node):
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

    Each edge carries ``start_line`` — the line of the first call site in
    the .lob file: the line the scanned text starts on, plus the line in
    that text, less one.  When that line is not known the field is
    omitted.

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

    # first_call: (source_addr, target_addr) → the earliest line it is
    # called on, or None when the line is not known
    first_call: dict[tuple[str, str], int | None] = {}
    for node in (
        *graph.nodes(kind=NodeKind.SYMBOL),
        *(n for n in graph.nodes() if KINDS[n.kind].runnable),
    ):
        source, base = _scanned_text(graph, node)
        if not source:
            continue
        for ref_name, src_line in call_extractor(source):
            line = None if base is None else base + (src_line - 1)
            for target_addr in name_index.get(ref_name, []):
                key = (node.address, target_addr)
                if key not in first_call or (
                        line is not None and (
                            first_call[key] is None
                            or line < first_call[key])):
                    first_call[key] = line

    for (src_addr, tgt_addr), line in first_call.items():
        graph.add_edge(Edge(
            source=src_addr,
            target=tgt_addr,
            kind=EdgeKind.USES,
            start_line=line,
        ))


# ── The graph as a document ───────────────────────────────────

#: The version of the document :meth:`NameGraph.to_dict` writes.
DOCUMENT_VERSION = 2

#: The levels of detail, in the order of how much each shows: the number
#: of a level is its place here, counting from 1.
LEVELS = ("outline", "index", "full")

def parse_level(level: str | int | None) -> str:
    """The name of *level*, given as a name or as a number (``1`` to
    ``3``, or the digit as a string).

    Raises ``ValueError``, naming the choices, for anything else.
    """
    if isinstance(level, str) and level in LEVELS:
        return level
    number = level
    if isinstance(level, str) and level.isdigit():
        number = int(level)
    if (isinstance(number, int) and not isinstance(number, bool)
            and 1 <= number <= len(LEVELS)):
        return LEVELS[number - 1]
    raise ValueError(
        f"unknown level {level!r}: choose outline, index or full "
        f"(or 1, 2, 3)")


def _sizes(graph: NameGraph) -> dict[str, int]:
    """The characters of text held at or under each node, each leaf's
    text counted once. A symbol holds none of its own (its lines are in
    the text that holds it), so it adds nothing to what contains it and its
    own size is that of its lines."""
    sizes: dict[str, int] = {}

    def size(node: Node) -> int:
        if node.address in sizes:
            return sizes[node.address]
        if KINDS[node.kind].text_in_holder:
            total = len(graph.text(node.address) or "")
        else:
            total = len(node.text or "") + sum(
                size(child) for child in graph.children(node.address)
                if not KINDS[child.kind].text_in_holder)
        sizes[node.address] = total
        return total

    for node in graph.nodes():
        size(node)
    return sizes


def _what_it_is(node: Node) -> dict:
    """What a node is, apart from where it is: the facts both a query's
    answer and the document write for it."""
    d: dict = {}
    if node.name is not None:
        d["named"] = True
    for field_name in ("mode", "declares", "value"):
        value = getattr(node, field_name)
        if value is not None:
            d[field_name] = value
    return d


def _where_it_is(node: Node) -> dict:
    """The line a node is written on. Nothing printed gives where it
    ends: a reader takes that from the file, and the model keeps it for
    ``query content``."""
    return {} if node.start_line is None else {"start_line": node.start_line}


def _what_the_level_adds(
    node: Node, level: str, sizes: dict[str, int],
) -> dict:
    """What the document adds for a node from ``index`` on: its size, the
    references a paragraph holds and, at ``full``, its text. *sizes* is
    :func:`_sizes` of its graph."""
    d: dict = {}
    if level != "outline":
        d["size"] = sizes[node.address]
        if node.kind == NodeKind.PROSE:
            d["refs"] = [
                {"label": ref.label, "sub": ref.sub,
                 "start_line": ref.start_line}
                for ref in node.refs]
    if (level == "full" and node.text is not None
            and not KINDS[node.kind].text_in_holder):
        d["text"] = node.text
    return d


def _node_entry(node: Node, level: str, sizes: dict[str, int]) -> dict:
    """The node as the document writes it at *level*. Only a module has a
    ``label``, its title, and a ``file``: any other node's follow from its
    address."""
    d: dict = {"address": node.address}
    if node.kind == NodeKind.MODULE:
        d["label"] = node.label
    d["kind"] = node.kind.name
    d.update(_what_it_is(node))
    if node.kind == NodeKind.MODULE and node.file is not None:
        d["file"] = node.file
    d.update(_where_it_is(node))
    d.update(_what_the_level_adds(node, level, sizes))
    return d


def _is_left_out(node: Node, level: str) -> bool:
    return level == "outline" and KINDS[node.kind].hidden_at_outline


def _in_writing_order(
    graph: NameGraph, level: str,
) -> list[tuple[Node, str | None]]:
    """The nodes the document shows at *level*, each with the address of
    the node above it that is shown, in the order they are written: each
    module, then what is written in it depth first, siblings by
    ``start_line``; then any other node but an ``EXTERNAL``, then the
    ``EXTERNAL`` nodes, in the order they were added. What a level leaves
    out is passed through: its children belong to the node above."""
    def held(address: str) -> list[Node]:
        found: list[Node] = []
        for child in graph.children(address):
            if _is_left_out(child, level):
                found += held(child.address)
            else:
                found.append(child)
        return found

    order: list[tuple[Node, str | None]] = []
    seen: set[str] = set()

    def walk(node: Node, parent: str | None) -> None:
        seen.add(node.address)
        order.append((node, parent))
        below = sorted(held(node.address),
                       key=lambda n: n.start_line or 0)
        for child in below:
            walk(child, node.address)

    for module in graph.nodes(NodeKind.MODULE):
        walk(module, None)
    others = [n for n in graph.nodes()
              if n.address not in seen and not _is_left_out(n, level)]
    for node in others:
        if node.kind != NodeKind.EXTERNAL:
            order.append((node, None))
    for node in others:
        if node.kind == NodeKind.EXTERNAL:
            order.append((node, None))
    return order


def _document_nodes(graph: NameGraph, level: str) -> list[dict]:
    """The nodes of the document at *level*, in writing order (see
    :func:`_in_writing_order`)."""
    sizes = _sizes(graph) if level != "outline" else {}
    return [
        _node_entry(node, level, sizes)
        for node, _ in _in_writing_order(graph, level)
    ]


def _document_edges(graph: NameGraph, level: str) -> list[dict]:
    """The edges of the document at *level*: the ``CONTAINS`` edges, one
    into each node but a module and an ``EXTERNAL``, in writing order (see
    :func:`_in_writing_order`) so a node's children come in the order they
    are written; and from ``index`` on the others, the cross-references,
    in the order they were added. ``outline`` is the tree alone: a level
    is the same content in text and in JSON, and the text of ``outline``
    has no references."""
    contains = [
        {"source": parent, "target": node.address, "kind": "CONTAINS"}
        for node, parent in _in_writing_order(graph, level)
        if parent is not None
    ]
    if level == "outline":
        return contains
    return contains + _cross_references(graph, level)


def _cross_references(graph: NameGraph, level: str) -> list[dict]:
    """The edges but ``CONTAINS`` as they stand at *level*, in the order
    they were added: an edge to or from a node that *level* leaves out is
    moved to the nearest node above it that is shown, along ``CONTAINS``;
    edges that are then the same (source, target and kind) are one, at the
    earliest line."""
    def hidden(address: str) -> bool:
        node = graph.node(address)
        return node is not None and _is_left_out(node, level)

    def shown(address: str) -> str | None:
        while hidden(address):
            parent = graph.parent_of(address)
            if parent is None:
                return None
            address = parent.address
        return address

    merged: dict[tuple[str, str, str], dict] = {}
    for edge in graph.edges():
        if edge.kind == EdgeKind.CONTAINS:
            continue
        source, target = shown(edge.source), shown(edge.target)
        if source is None or target is None:
            continue
        key = (source, target, edge.kind.name)
        if key not in merged:
            merged[key] = {"source": source, "target": target,
                           "kind": edge.kind.name}
            if edge.start_line is not None:
                merged[key]["start_line"] = edge.start_line
        elif edge.start_line is not None and (
                merged[key].get("start_line", edge.start_line + 1)
                > edge.start_line):
            merged[key]["start_line"] = edge.start_line
    return list(merged.values())


def _lifted_citations(graph: NameGraph) -> list[dict]:
    """The ``CITES`` edges lifted to the nodes ``outline`` shows: a
    paragraph's citation is its section's. These answer ``query cites``
    and ``cited-by``; the document at ``outline`` no longer holds them."""
    return [e for e in _cross_references(graph, "outline")
            if e["kind"] == "CITES"]


# ── Answers to queries ────────────────────────────────────────

def node_summary(node: Node) -> dict:
    """The node as a query prints it: its ``label`` and ``file`` as well,
    for an answer stands on its own, with no module beside it to look them
    up in."""
    d: dict = {"address": node.address, "label": node.label,
               "kind": node.kind.name}
    d.update(_what_it_is(node))
    if node.file is not None:
        d["file"] = node.file
    d.update(_where_it_is(node))
    return d


def sigil_of(node: Node) -> str:
    """The sigil that begins the node in its file (``~example``,
    ``~property``, ``~run``, or ``~test`` for a test the document names),
    or ``""`` for a node with none."""
    facts = KINDS[node.kind]
    if facts.sigil is None or (facts.sigil_needs_name and node.name is None):
        return ""
    return facts.sigil


def content_tree(
    graph: NameGraph, address: str, depth: int | None = None,
) -> dict | None:
    """The subtree at *address*, nested and narrow, or ``None`` if there
    is no such node.

    Each node has its ``address``, ``kind`` and ``start_line``,
    ``"named": true`` when the document names it, its ``mode``,
    ``declares`` and ``value`` when set, its ``text`` when it holds text,
    and its ``children`` (what it contains, in document order) when it has
    any, down *depth* ``CONTAINS`` steps (``0`` the node alone, ``None``
    all of them). The root also has its ``file``. There
    are no edges, labels, sizes or references: nesting is the containment,
    the address carries the label, and the references are written in the
    text.

    Text is held once, so a symbol has none, its lines being in the code
    block it is written in; but a symbol whose code block is not in the
    answer carries its text, so the answer still shows each line of
    source. That is the symbol asked for itself: a symbol is a child of
    its code block, so *depth* never leaves one without it.
    """
    root = graph.node(address)
    if root is None:
        return None

    def entry(node: Node, remaining: int | None, holder_in: bool) -> dict:
        d: dict = {"address": node.address, "kind": node.kind.name}
        if node.name is not None:
            d["named"] = True
        for field_name in ("mode", "declares", "value"):
            value = getattr(node, field_name)
            if value is not None:
                d[field_name] = value
        if node is root:
            if node.file is not None:
                d["file"] = node.file
        d.update(_where_it_is(node))
        if KINDS[node.kind].text_in_holder:
            text = None if holder_in else graph.text(node.address)
        else:
            text = node.text
        if text is not None:
            d["text"] = text
        if remaining != 0:
            children = [
                entry(child, None if remaining is None else remaining - 1,
                      True)
                for child in graph.children(node.address)]
            if children:
                d["children"] = children
        return d

    return entry(root, depth, False)


def _citations(graph: NameGraph) -> list[Edge]:
    """The ``CITES`` edges lifted to the nodes ``outline`` shows, each
    with the line it is written on (the earliest, where edges were
    merged)."""
    return [
        Edge(source=e["source"], target=e["target"], kind=EdgeKind.CITES,
             start_line=e.get("start_line"))
        for e in _lifted_citations(graph)]


def cites_edges(graph: NameGraph, address: str) -> list[Edge]:
    """The ``CITES`` edges from the node at *address*, in the order first
    found, one to each node it cites (the first): those named in its
    paragraphs (as ``outline`` shows the edges, a section's citations are
    its paragraphs'), or, for a paragraph itself, in it."""
    node = graph.node(address)
    if node is None:
        return []
    if KINDS[node.kind].hidden_at_outline:
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
