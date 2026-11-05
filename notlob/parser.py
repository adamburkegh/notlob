"""notlob.parser - Parse .lob source files into a Lark Tree.

Native grammar
--------------
``grammar.lark`` is parsed with Lark's own contextual LALR lexer — every
structural line-type (the heading markers, ``SIGIL``, ``INDENT``,
``BLANK``, ``BULLET``, ``SEPARATOR``, the reserved post-text heads) is a
native terminal in the grammar file itself, not a token produced by a
hand-written Python line classifier. See ``grammar.lark``'s header comment
for how heading/sigil/prose disambiguation is resolved via terminal
priority and line-start anchoring, and for what a name is: a ``NAME``
terminal that holds no ``#``, beside a marker, so a ``NAME`` token is
exactly the name.

Two things the grammar can't fully own are handled here, in a thin layer
around the raw parse:

**Token normalisation.** Every line-oriented terminal in the grammar
consumes through its own trailing newline (so the lexer's cursor is
always at true line-start for the next token). Downstream consumers
(``model.py``, ``weave/markdown.py``) expect the *stripped* content.
``_normalize`` rewrites each raw token's value to match, once, right
after parsing, so nothing downstream needs to know the grammar changed.

**The refusal of a ``#`` in a name.** The grammar refuses it, in Lark's
words (``Unexpected token ... Expected one of: _EOL``), which tell an
author little. ``parse`` words that one refusal, as
``sharp.lob:5: a name may not hold '#': 'Calling C# from Python'``, and
holds no rule of its own: it only reads what Lark's error says.

Usage::

    from notlob.parser import parse_file, to_json
    tree = parse_file("examples/pricing/discounts.lob")
    print(tree.pretty())
    print(to_json(tree))
"""

from __future__ import annotations

import json
from pathlib import Path

from lark import Lark, Token, Tree
from lark.exceptions import UnexpectedInput

_GRAMMAR = (Path(__file__).parent / "grammar.lark").read_text(
    encoding="utf-8"
)

_parser = Lark(
    _GRAMMAR,
    parser="lalr",
    propagate_positions=True,
    regex=True,
)

# ── Token normalisation ─────────────────────────────────────
#
# Maps a raw terminal's matched text to the value downstream code
# expects: the trailing "\n" stripped from every line-token.

_LINE_TOKEN_TYPES = {
    "SIGIL", "SEPARATOR", "TESTS_HEAD", "BINDING_HEAD", "REFERENCES_HEAD",
    "INDENTED_LINE", "LISTING_LINE", "BULLET", "BLANK",
}


def _normalize_token(tok: Token) -> Token:
    return tok.update(value=str(tok).rstrip("\n"))


def _normalize(tree: Tree) -> Tree:
    """Rewrite line-token values in place to match pre-refactor shape."""
    for subtree in tree.iter_subtrees():
        children = subtree.children
        for i, child in enumerate(children):
            if isinstance(child, Token) and child.type in _LINE_TOKEN_TYPES:
                children[i] = _normalize_token(child)
    return tree


# The closed vocabulary of recognised claim sigils (body-level; excludes
# ~test, which is _TEST_MARK, a separate terminal only reachable inside
# a #Tests group). Mirrors grammar.lark's SIGIL terminal; kept here for
# cross-checking against notlob.graph's dispatch (see
# tests/test_graph_completeness.py), which fails loudly if the two drift
# apart.
_KNOWN_SIGILS = ("~example", "~run", "~property")


# ── The refusal of a # in a name ─────────────────────────────

class LobSyntaxError(ValueError):
    """A ``#`` in a name, worded for an author: the grammar refused it, and
    this says where and what the name was. ``str`` of it is
    ``file:line: reason`` (``line N: reason`` when the source has no file).
    Any other refusal stays Lark's own."""

    def __init__(self, line: int, reason: str, file: str | None = None):
        self.line, self.reason, self.file = line, reason, file
        super().__init__(
            f"{file}:{line}: {reason}" if file else f"line {line}: {reason}")


def _named_with_hash(
    source: str, exc: UnexpectedInput,
) -> LobSyntaxError | None:
    """Lark's refusal *exc* of *source* as a ``#`` in a name, or ``None``
    if it is some other refusal. The grammar expects only the rest of a
    name (a ``NAME``, or the end of its line) where it stopped, and what
    stands there is a ``#``: the name is what is written from the ``NAME``
    Lark had read (if any) to the end of the line."""
    expected = getattr(exc, "expected", None)
    if not expected or not set(expected) <= {"NAME", "_EOL"}:
        return None
    if source[exc.pos_in_stream:].lstrip(" \t")[:1] != "#":
        return None
    read = (getattr(exc, "token_history", None) or [None])[-1]
    start = read.start_pos if getattr(read, "type", "") == "NAME" else (
        exc.pos_in_stream)
    end = source.find("\n", exc.pos_in_stream)
    name = source[start:end if end >= 0 else None].strip()
    return LobSyntaxError(exc.line, f"a name may not hold '#': {name!r}")


# ── Public API ───────────────────────────────────────────────

def parse(source: str) -> Tree:
    """Parse a .lob source string and return a Lark Tree. Raises
    :class:`LobSyntaxError` for a ``#`` in a name, and Lark's own
    ``UnexpectedInput`` for any other refusal."""
    if not source.endswith("\n"):
        source += "\n"
    try:
        tree = _parser.parse(source)
    except UnexpectedInput as exc:
        worded = _named_with_hash(source, exc)
        if worded is None:
            raise
        raise worded from None
    _normalize(tree)
    return tree


def load_file(path: str | Path) -> tuple[Tree, str]:
    """Parse a .lob file and return its Lark Tree and the text it was read
    as. A ``#`` in a name raises :class:`LobSyntaxError` with the file (as
    given, with ``/``)."""
    source = Path(path).read_text(encoding="utf-8")
    try:
        return parse(source), source
    except LobSyntaxError as exc:
        raise LobSyntaxError(
            exc.line, exc.reason, Path(path).as_posix()) from None


def parse_file(path: str | Path) -> Tree:
    """Parse a .lob file and return a Lark Tree. A ``#`` in a name raises
    :class:`LobSyntaxError` with the file (as given, with ``/``)."""
    return load_file(path)[0]


# ── Serialisation ────────────────────────────────────────────

def to_dict(node: Tree | Token) -> dict:
    """Recursively convert a Tree or Token to a plain dict."""
    if isinstance(node, Token):
        return {"token": node.type, "value": str(node)}
    return {
        "rule": node.data,
        "children": [to_dict(c) for c in node.children],
    }


def to_json(tree: Tree, *, indent: int = 2) -> str:
    """Serialise a parse Tree to a JSON string."""
    return json.dumps(to_dict(tree), indent=indent, ensure_ascii=False)
