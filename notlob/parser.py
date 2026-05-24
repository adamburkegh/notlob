"""notlob.parser - Parse .lob source files into a Lark Tree.

Two-phase approach
------------------
1. The line lexer (``_LobLexer``) classifies each source line into one
   or more typed tokens.  Structural lines produce a single token each
   (MOD_HEAD, SUBHEAD, SIGIL, INDENT, BLANK, SEPARATOR, or a post-text
   head token).  Prose lines are sub-tokenised into PROSE_TEXT, REF,
   and PROSE_NL tokens by ``_tokenize_prose``.

2. Lark parses the flat token stream against ``grammar.lark`` using an
   LALR parser.  Because classification happens in phase 1, the grammar
   is entirely structural — no regex, no lexer ambiguity.

Line-start invariant
--------------------
``#`` and ``##`` at column zero are always structural tokens (MOD_HEAD,
SUBHEAD, or a reserved post-text head like TESTS_HEAD).  ``_classify``
checks for these before falling through to prose.  Consequently, inline
refs (``#Label``, ``##Label``) only ever appear mid-line, as PROSE_TEXT
and REF tokens produced by ``_tokenize_prose``.  The grammar relies on
this invariant to avoid any heading / reference ambiguity.

Usage::

    from notlob.parser import parse_file, to_json
    tree = parse_file("examples/pricing/discounts.lob")
    print(tree.pretty())
    print(to_json(tree))
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from lark import Lark, Token, Tree
from lark.lexer import Lexer, LexerState

_GRAMMAR = (Path(__file__).parent / "grammar.lark").read_text(
    encoding="utf-8"
)

# ── Line lexer ───────────────────────────────────────────────

_RESERVED_HEADS: dict[str, str] = {
    "#Tests":      "TESTS_HEAD",
    "#Binding":    "BINDING_HEAD",
    "#References": "REFERENCES_HEAD",
}

# Matches ##Label or #Label in prose: capital letter start, optional
# Title Case continuation (space + capital letter + word chars).
# Lookbehind prevents matching # inside URLs or identifiers.
_REF_PAT = re.compile(
    r'(?<![/\w])(##?[A-Z][A-Za-z0-9_]*(?:[ ][A-Z][A-Za-z0-9_]*)*)'
)


def _classify(line: str) -> Token | None:
    """Classify one source line as a single Token, or None for prose.

    Returns None when the line is unindented prose; the caller is
    responsible for sub-tokenising it into PROSE_TEXT and REF tokens.
    """
    stripped = line.rstrip("\n")

    if stripped == "---":
        return Token("SEPARATOR", stripped)
    if stripped in _RESERVED_HEADS:
        return Token(_RESERVED_HEADS[stripped], stripped)
    if re.match(r"#Appendix:", stripped):
        return Token("APPENDIX_HEAD", stripped)
    if stripped.startswith("##"):
        return Token("SUBHEAD", stripped[2:].strip())
    if re.match(r"#[^#]", stripped):
        return Token("MOD_HEAD", stripped[1:].strip())
    if re.match(r"~[a-z]", stripped):
        return Token("SIGIL", stripped)
    if stripped == "":
        return Token("BLANK", stripped)
    if stripped != stripped.lstrip():   # line has leading whitespace
        return Token("INDENT", stripped)
    return None                         # prose — sub-tokenise below


def _tokenize_prose(line: str):
    """Yield PROSE_TEXT, REF, and PROSE_NL tokens from one prose line.

    Splits the line on the REF pattern.  Each match becomes a REF
    token; surrounding text becomes PROSE_TEXT.  A PROSE_NL sentinel
    is emitted last, marking the end of the line for the grammar's
    ``prose_line`` rule.
    """
    for part in _REF_PAT.split(line):
        if not part:
            continue
        if _REF_PAT.fullmatch(part):
            yield Token("REF", part)
        else:
            yield Token("PROSE_TEXT", part)
    yield Token("PROSE_NL", "")


class _LobLexer(Lexer):
    """Line-level lexer: feeds pre-classified tokens to Lark."""

    def __init__(self, lexer_conf):
        pass    # Lark passes its lexer config; we ignore it

    def lex(self, data: str):
        for line in data.splitlines(keepends=True):
            if line:
                tok = _classify(line)
                if tok is None:
                    yield from _tokenize_prose(line.rstrip("\n"))
                else:
                    yield tok

    def make_lexer_state(self, text):
        return LexerState(text)


_parser = Lark(
    _GRAMMAR,
    parser="lalr",
    lexer=_LobLexer,
    propagate_positions=False,
)


# ── Public API ───────────────────────────────────────────────

def parse(source: str) -> Tree:
    """Parse a .lob source string and return a Lark Tree."""
    if not source.endswith("\n"):
        source += "\n"
    return _parser.parse(source)


def parse_file(path: str | Path) -> Tree:
    """Parse a .lob file and return a Lark Tree."""
    return parse(Path(path).read_text(encoding="utf-8"))


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
    return json.dumps(to_dict(tree), indent=indent)
