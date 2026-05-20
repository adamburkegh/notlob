"""notlob.parser - Parse .lob source files into a Lark Tree.

Two-phase approach:
  1. The line lexer classifies each source line into a typed Token.
     This is deterministic — one line, one token, no ambiguity.
  2. Lark parses the token stream against grammar.lark.

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


def _classify(line: str) -> Token:
    """Classify one source line (with trailing newline) as a Token."""
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
    return Token("PROSE", stripped)


class _LobLexer(Lexer):
    """Line-level lexer: feeds pre-classified tokens to Lark."""

    def __init__(self, lexer_conf):
        pass    # Lark passes its lexer config; we ignore it

    def lex(self, data: str):
        for line in data.splitlines(keepends=True):
            if line:
                yield _classify(line)

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
