r"""Generate a backnaur-flavoured LaTeX fragment describing notlob's grammar.

Usage::

    notlobenv/Scripts/python notlob/util/gen_grammar_latex.py > var/notlob_grammar.tex

Why this exists
----------------
The grammar section of the paper needs to match ``notlob/grammar.lark``
exactly, and needs to be typeset with a package that actually works with
the ``acmart`` document class -- ``backnaur`` was settled on after
``syntax`` (mdwtools) turned out to clash with it. Hand-transcribing the
grammar into ``backnaur``'s macros directly, by hand, in an editor, is
where the real risk lives: every literal terminal string needs specific
LaTeX escaping (``#`` -> ``\#``, ``~`` -> ``\textasciitilde{}`` -- NOT the
bare ``\~`` accent shortcut, which silently produces an accented letter
instead of a tilde), and every time the grammar changes there's a fresh
chance to get an escape wrong or drift out of sync with the real source.

How the model is derived
-------------------------
This script parses ``grammar.lark`` for real, rather than maintaining a
hand-typed shadow copy of it. It does this by loading Lark's own
``grammars/lark.lark`` -- the grammar Lark ships that describes ``.lark``
file syntax itself -- as an ordinary ``Lark`` instance, and using *that*
to parse ``notlob/grammar.lark``'s source text. (This isn't how Lark
bootstraps its own parser -- see that file's own comment, "Lark is not
bootstrapped, its parser is implemented in load_grammar.py" -- but
nothing stops it being used this way as an independent tool.) The
resulting parse tree mirrors the file's EBNF structure directly (``|``,
``*``, ``+``, ``?``, ``(...)``, string/regex literals, ``.N``
priorities), so every *rule* (nonterminal production) and every
string-literal-only *terminal* translates into this script's small BNF
AST (``NT``/``T``/``D``/``Seq``/``Or``/``Opt``/``Rep``/``RepPlus``/
``Except``) completely mechanically -- there is no hand-maintained
production list to let drift out of sync.

What's still hand-maintained, and why
--------------------------------------
Terminals defined by a genuine regex (``REF``, ``LINE_START_TEXT``,
``PROSE_TEXT``, ``LINE_CHAR``, and the anonymous inline character
classes ``[^#\n]`` and ``[ \t]`` used inside ``MOD_HEAD``/``INDENT``/
``BULLET``) cannot be mechanically turned into EBNF -- translating a
regex like the lookahead-conditioned prose terminals into readable BNF
is a judgement call, not a transcription (see notlob/docs/DESIGN.md,
"The grammar is the specification"). These get a small hand-authored
entry in ``_REGEX_OVERRIDES``, keyed by the terminal's *exact* extracted
regex source. If ``grammar.lark`` adds, removes, or changes one of these
regexes without a matching update here, ``parse_grammar()`` raises
loudly (missing-override *and* stale-override are both detected) instead
of silently rendering something wrong or out of date.

``_PRIORITY_TIERS`` (used to generate the disambiguation section's
priority-grouping sentence) is cross-checked the same way against the
real ``.N`` priorities parsed from the file.

``_DISAMBIGUATION``'s surrounding prose (what priority even means,
positional constraints, lookahead-conditioned terminal definitions) stays
hand-written -- turning that narrative into something mechanically
generated isn't worth the complexity it would add.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Union

from lark import Lark, Token, Tree

# ── A small BNF expression AST ──────────────────────────────────────

@dataclass(frozen=True)
class NT:
    """A nonterminal reference."""
    name: str


@dataclass(frozen=True)
class T:
    """A literal terminal string."""
    text: str


@dataclass(frozen=True)
class D:
    """A descriptive phrase -- an ISO 14977-style "special sequence",
    used where spelling a terminal out character-by-character isn't
    practical (e.g. "any character other than newline")."""
    text: str


@dataclass(frozen=True)
class Seq:
    """Concatenation."""
    items: tuple["Node", ...]

    def __init__(self, *items: "Node"):
        object.__setattr__(self, "items", items)


@dataclass(frozen=True)
class Or:
    """Alternation. Rendered with one alternative per line."""
    items: tuple["Node", ...]

    def __init__(self, *items: "Node"):
        object.__setattr__(self, "items", items)


@dataclass(frozen=True)
class Opt:
    """Zero or one -- not native to backnaur; rendered as [ item ]."""
    item: "Node"


@dataclass(frozen=True)
class Rep:
    """Zero or more -- not native to backnaur; rendered as { item }."""
    item: "Node"


@dataclass(frozen=True)
class RepPlus:
    """One or more -- not native to backnaur; rendered as item+."""
    item: "Node"


@dataclass(frozen=True)
class Except:
    """item, minus the strings matched by minus (ISO 14977 "-")."""
    item: "Node"
    minus: "Node"


Node = Union[NT, T, D, Seq, Or, Opt, Rep, RepPlus, Except]


# ── Escaping and rendering ──────────────────────────────────────────

_TERMINAL_ESCAPES = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "%": r"\%",
    "&": r"\&",
    "_": r"\_",
    "#": r"\#",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "-": "{-}",   # prevent -- and --- ligatures (en/em dash)
}


def escape_terminal(text: str) -> str:
    """Escape *text* for safe use inside \\bnfts{...}."""
    return "".join(_TERMINAL_ESCAPES.get(ch, ch) for ch in text)


def escape_name(name: str) -> str:
    """Escape a rule/terminal identifier for use as a \\bnfpn{...} or
    \\bnfprod{...} argument. Unlike escape_terminal, this only needs to
    handle the one special character valid Lark identifiers can contain
    (``_``) -- real grammar.lark names are otherwise plain ASCII
    letters/digits."""
    return name.replace("_", r"\_")


def _needs_group(node: Node) -> bool:
    """True if *node* renders as multiple bnfsp/bnfor-separated tokens,
    and so needs explicit parens when nested inside another Seq/Or or a
    Rep/RepPlus/Opt/Except wrapper -- none of backnaur's own commands
    imply any operator precedence, so without this, e.g. RepPlus(Or(A,
    B, C)) would render as "A or B or C+", visually binding the '+' to
    C alone instead of the whole alternation."""
    return isinstance(node, (Or, Seq)) and len(node.items) > 1


def render_grouped(node: Node) -> str:
    text = render(node)
    return f"({text})" if _needs_group(node) else text


def render(node: Node) -> str:
    if isinstance(node, NT):
        return f"\\bnfpn{{{escape_name(node.name)}}}"
    if isinstance(node, T):
        if node.text == " ":
            # A bare space as a \bnfts{} argument is illegible -- see
            # the backnaur manual's own "kludge" note on this exact
            # problem. Use NT("Space") (a real production, see
            # TERMINALS) instead of T(" ") for a literal space.
            raise ValueError('use NT("Space") instead of T(" ")')
        return f"\\bnfts{{{escape_terminal(node.text)}}}"
    if isinstance(node, D):
        return f"\\bnftd{{{node.text}}}"
    if isinstance(node, Seq):
        return " \\bnfsp ".join(render_grouped(i) for i in node.items)
    if isinstance(node, Or):
        return " \\bnfor ".join(render_grouped(i) for i in node.items)
    if isinstance(node, Opt):
        return f"[\\,{render_grouped(node.item)}\\,]"
    if isinstance(node, Rep):
        return f"\\{{\\,{render_grouped(node.item)}\\,\\}}"
    if isinstance(node, RepPlus):
        # \textsuperscript, not $^+$: these macros are used inside a
        # bnf/bnf* environment whose own math/text-mode status isn't
        # documented precisely enough to risk nesting math mode here.
        return f"{render_grouped(node.item)}\\textsuperscript{{+}}"
    if isinstance(node, Except):
        return f"{render_grouped(node.item)} - {render_grouped(node.minus)}"
    raise TypeError(f"unhandled node type: {node!r}")


def render_production(name: str, rhs: Node) -> list[str]:
    """Return the backnaur source lines for one production (no
    trailing '\\\\' -- the caller joins lines across all productions)."""
    display_name = escape_name(name)
    if isinstance(rhs, Or) and len(rhs.items) > 1:
        first, *rest = rhs.items
        lines = [f"\\bnfprod{{{display_name}}}\n    {{{render(first)}}}"]
        lines += [f"\\bnfmore{{\\bnfor {render(item)}}}" for item in rest]
        return lines
    return [f"\\bnfprod{{{display_name}}}\n    {{{render(rhs)}}}"]


def render_bnf_block(productions: list[tuple[str, Node]]) -> str:
    lines: list[str] = []
    for name, rhs in productions:
        lines += render_production(name, rhs)
    body = " \\\\\n".join(lines)
    return f"\\begin{{bnf*}}\n{body}\n\\end{{bnf*}}"


# ── Parsing grammar.lark via Lark's own meta-grammar ─────────────────
#
# Every "rule" (lowercase, e.g. `module`, `named_test`) becomes a
# PRODUCTIONS entry; every "token" (uppercase, e.g. `MOD_HEAD`,
# `TEST_SIGIL`) becomes a TERMINALS entry. Both are derived by walking
# the real parse tree -- see the module docstring for what's still
# hand-maintained and why.

_REGEX_OVERRIDES: dict[str, Node] = {
    r"[^\n]": D("any character other than newline"),
    r"[^#\n]": NT("NonHashLineChar"),
    r"[ \t]": Or(NT("Space"), NT("Tab")),
    r"[ \t]+": RepPlus(Or(NT("Space"), NT("Tab"))),
    # REF -- deliberately omits the "not preceded by a word char or /"
    # lookbehind from the formal grammar; that constraint is prose-only
    # (see _DISAMBIGUATION), not expressible with EBNF's own operators.
    r"(?<![\w\/])##?[\p{Lu}\p{Lt}\p{Lo}][\p{L}\p{Nd}_]*(?:[ ][\p{Lu}\p{Lt}\p{Lo}][\p{L}\p{Nd}_]*)*": Seq(
        Or(T("#"), T("##")), NT("RefInitial"), Rep(NT("WordChar")),
        Rep(Seq(NT("Space"), NT("RefInitial"), Rep(NT("WordChar")))),
    ),
    # LINE_START_TEXT / PROSE_TEXT reference ProseInitial/ProseTail,
    # which are deliberately NOT in _EXTRA_TERMINALS -- their own
    # definitions depend on one-token lookahead, not expressible with
    # EBNF's own operators, so they're described in _DISAMBIGUATION's
    # prose instead of the terminals table.
    r"(?<=\n)(?:[^#~\n]|#(?!#?[\p{Lu}\p{Lt}\p{Lo}])|~(?![a-z]))(?:[^#\n]|#(?!#?[\p{Lu}\p{Lt}\p{Lo}]))*":
        Seq(NT("ProseInitial"), Rep(NT("ProseTail"))),
    r"(?<!\n)(?:[^#\n]|#(?!#?[\p{Lu}\p{Lt}\p{Lo}]))+":
        RepPlus(NT("ProseTail")),
}

# Synthetic terminals referenced by _REGEX_OVERRIDES above but not
# present as their own named terminal in grammar.lark -- appended to
# the mechanically-derived TERMINALS list so they still get a row in
# the rendered table.
_EXTRA_TERMINALS: list[tuple[str, Node]] = [
    ("NonHashLineChar", Except(NT("LINE_CHAR"), T("#"))),
    ("RefInitial", D(
        "an uppercase or titlecase letter, or a letter from a script "
        "with no case distinction (Unicode categories Lu, Lt, Lo -- "
        "e.g. Latin/Cyrillic/Greek capitals, or any CJK/Arabic/"
        "Hebrew/Thai/Devanagari letter)"
    )),
    ("WordChar", D("any Unicode letter, decimal digit, or underscore")),
    ("Space", D("a space character")),
    ("Tab", D("the tab character")),
    ("NewLine", D("the newline character")),
]

# Priority tiers referenced by the generated disambiguation sentence,
# cross-checked against grammar.lark's real `.N` values in
# parse_grammar() -- add/remove/repriority a terminal there without
# updating this and generation fails loudly instead of the paper
# silently describing a stale priority order.
_PRIORITY_TIERS: dict[int, list[str]] = {
    20: ["SEPARATOR", "TESTS_HEAD", "BINDING_HEAD", "REFERENCES_HEAD",
         "APPENDIX_HEAD"],
    10: ["MOD_HEAD", "SUBHEAD", "SIGIL", "TEST_SIGIL"],
    8: ["INDENTED_LINE", "BLANK", "BULLET"],
    5: ["REF"],
    1: ["LINE_START_TEXT", "PROSE_TEXT"],
}


def _string_value(token: Token) -> str:
    """Unescape a Lark STRING token's raw source text (e.g. '"\\n"',
    quotes and backslash included) into the string it represents."""
    body = token.value if token.value.endswith('"') else token.value[:-1]
    return ast.literal_eval(body)


_REGEXP_RE = re.compile(r"^/((?:\\/|\\\\|[^/])*)/[a-zA-Z]*$")


def _regexp_pattern(token: Token) -> str:
    """Strip a Lark REGEXP token's delimiters and flags, returning its
    raw pattern source (backslash escapes left as-is, not unescaped --
    this is a regex, not a string)."""
    m = _REGEXP_RE.match(token.value)
    if not m:
        raise ValueError(f"could not parse REGEXP token: {token.value!r}")
    return m.group(1)


def _convert_string(value: str) -> Node:
    """Convert a literal string's *value* into a Node, splitting out
    any embedded newline character(s) as NT("NewLine") -- a raw
    newline surviving into a \\bnfts{...} argument is invisible/broken
    in the typeset output (same reasoning as the Space/Tab handling
    below). grammar.lark writes some terminals' trailing newline as
    its own separate literal (e.g. MOD_HEAD's `... REST_OF_LINE "\n"`)
    and others with the newline embedded in a longer literal (e.g.
    SIGIL's `"~example\n"`) -- this handles both uniformly."""
    if "\n" not in value:
        return T(value)
    pieces: list[Node] = []
    parts = value.split("\n")
    for i, part in enumerate(parts):
        if part:
            pieces.append(T(part))
        if i < len(parts) - 1:
            pieces.append(NT("NewLine"))
    return pieces[0] if len(pieces) == 1 else Seq(*pieces)


def _convert_literal(token: Token, used_overrides: set[str]) -> Node:
    if token.type == "STRING":
        return _convert_string(_string_value(token))
    if token.type == "REGEXP":
        pattern = _regexp_pattern(token)
        if pattern not in _REGEX_OVERRIDES:
            raise KeyError(
                f"grammar.lark uses regex {pattern!r} with no matching "
                f"entry in _REGEX_OVERRIDES -- add one describing what "
                f"it means for the paper's grammar section"
            )
        used_overrides.add(pattern)
        return _REGEX_OVERRIDES[pattern]
    raise TypeError(f"unknown literal token type: {token.type!r}")


def _convert_expr(tree: Tree, used_overrides: set[str]) -> Node:
    atom = tree.children[0]
    inner = _convert(atom, used_overrides)
    if len(tree.children) == 1:
        return inner
    op = tree.children[1]
    if not (isinstance(op, Token) and op.type == "OP"):
        raise NotImplementedError(
            f"bounded repetition (item~N or item~N..M) is not used "
            f"anywhere in grammar.lark today and isn't supported here: "
            f"{tree!r}"
        )
    return {"+": RepPlus, "*": Rep, "?": Opt}[str(op)](inner)


def _convert(node: Tree | Token, used_overrides: set[str]) -> Node:
    if isinstance(node, Token):
        raise TypeError(
            f"unexpected bare token in expansion position: {node!r} -- "
            f"grammar.lark uses a Lark construct this script doesn't "
            f"handle yet"
        )
    data = node.data
    if data == "expansions":
        return Or(*[_convert(c, used_overrides) for c in node.children])
    if data == "expansion":
        return Seq(*[_convert(c, used_overrides) for c in node.children])
    if data == "expr":
        return _convert_expr(node, used_overrides)
    if data == "maybe":
        return Opt(_convert(node.children[0], used_overrides))
    if data == "name":
        return NT(str(node.children[0]))
    if data == "literal":
        return _convert_literal(node.children[0], used_overrides)
    raise TypeError(
        f"unhandled grammar.lark construct: {data!r} ({node!r}) -- this "
        f"script covers the subset of Lark syntax grammar.lark actually "
        f"uses, not the whole Lark meta-grammar"
    )


def _priority_of(item: Tree) -> int:
    for c in item.children:
        if isinstance(c, Tree) and c.data == "priority":
            return int(str(c.children[0]))
    return 0


def _load_meta_grammar() -> Lark:
    """Load Lark's own grammar-of-grammars (the .lark file describing
    .lark syntax) as an ordinary Lark instance, so it can be used to
    parse notlob/grammar.lark itself. Not how Lark bootstraps its own
    parser (see grammars/lark.lark's own comment) -- just a convenient,
    always-in-sync-with-the-installed-Lark-version parser for our
    purposes."""
    meta_src = (
        resources.files("lark.grammars")
        .joinpath("lark.lark")
        .read_text(encoding="utf-8")
    )
    return Lark(meta_src, parser="lalr", maybe_placeholders=False)


def _check_priority_tiers(priorities: dict[str, int]) -> None:
    declared = {
        name: prio
        for prio, names in _PRIORITY_TIERS.items()
        for name in names
    }
    actual = {name: prio for name, prio in priorities.items() if prio != 0}
    if declared == actual:
        return
    missing = set(actual) - set(declared)
    stale = set(declared) - set(actual)
    wrong_tier = {
        n for n in (set(declared) & set(actual)) if declared[n] != actual[n]
    }
    raise ValueError(
        "_PRIORITY_TIERS is out of sync with grammar.lark's real "
        f"terminal priorities -- missing (in grammar.lark, not in "
        f"_PRIORITY_TIERS): {missing or None}; stale (in "
        f"_PRIORITY_TIERS, no longer in grammar.lark): {stale or None}; "
        f"wrong tier: {wrong_tier or None}"
    )


def _priority_table() -> str:
    """Render the priority tiers as a LaTeX tabular, highest first."""
    tiers = sorted(_PRIORITY_TIERS, reverse=True)
    rows: list[str] = []
    for prio in tiers:
        names = _PRIORITY_TIERS[prio]
        note = " (fallback)" if prio == tiers[-1] else ""
        cells = ", ".join(f"\\synt{{{escape_name(n)}}}" for n in names)
        rows.append(f"    {prio} & {cells}{note} \\\\")
    body = "\n".join(rows)
    return (
        "  \\begin{tabular}{rl}\n"
        "    \\textbf{Priority} & \\textbf{Terminals} \\\\\n"
        "    \\hline\n"
        + body + "\n"
        "  \\end{tabular}"
    )


def parse_grammar(
    path: Path,
) -> tuple[list[tuple[str, Node]], list[tuple[str, Node]], dict[str, int]]:
    """Parse *path* (notlob/grammar.lark) into (PRODUCTIONS, TERMINALS,
    priorities) -- PRODUCTIONS/TERMINALS in the same AST
    render_bnf_block already knows how to render; priorities is a
    terminal-name -> `.N` value map (0 for terminals with no explicit
    priority), used by both _check_priority_tiers and downstream
    consumers such as gen_listings_lang.py. Raises if a regex terminal
    has no _REGEX_OVERRIDES entry, if _REGEX_OVERRIDES has a stale
    entry no longer used, or if _PRIORITY_TIERS is out of sync with
    the file's real `.N` values."""
    meta = _load_meta_grammar()
    tree = meta.parse(path.read_text(encoding="utf-8"))

    productions: list[tuple[str, Node]] = []
    terminals: list[tuple[str, Node]] = []
    priorities: dict[str, int] = {}
    used_overrides: set[str] = set()

    for item in tree.children:
        if item is None:
            continue
        if item.data not in ("rule", "token"):
            raise NotImplementedError(
                f"unsupported top-level grammar.lark construct "
                f"{item.data!r} -- only rule/token declarations are "
                f"used today, no %import/%ignore/%declare/%override"
            )
        name = str(item.children[0])
        rhs = _convert(item.children[-1], used_overrides)
        if item.data == "rule":
            productions.append((name, rhs))
        else:
            terminals.append((name, rhs))
            priorities[name] = _priority_of(item)

    unused = set(_REGEX_OVERRIDES) - used_overrides
    if unused:
        raise KeyError(
            f"_REGEX_OVERRIDES has entries no longer used by "
            f"grammar.lark: {unused!r} -- remove them"
        )
    _check_priority_tiers(priorities)

    terminals += _EXTRA_TERMINALS
    return productions, terminals, priorities


_DISAMBIGUATION_INTRO = r"""
\synt{ProseInitial} and \synt{ProseTail} are omitted from the table
above: unlike the other terminals, their definitions depend on
one-token lookahead (what follows a character, not the character
itself), which is not expressible with EBNF's own operators. They are
defined below instead, alongside the other apparatus a deterministic
parse needs beyond the grammar proper.

\subsection*{Disambiguation strategy (not part of the grammar above)}

The productions and terminal definitions above are a complete
description of the \emph{language} -- what strings are valid .lob
source. They are not, by themselves, sufficient to determine a
\emph{unique parse}: several terminals are deliberately allowed to
overlap in the strings they can match (e.g.\ \synt{SUBHEAD} and
\synt{REF} can both match \term{\#\#Stacking Discounts}), because
which one applies depends on where the text occurs, not what it looks
like in isolation. A deterministic single-pass (LALR) parser resolves
this the same way lexer generators conventionally do -- by an explicit
disambiguation rule external to the grammar, analogous to flex/lex's
``longest match, first rule wins'' or the standard resolution of the
dangling-\term{else} ambiguity in C's grammar:

\begin{itemize}
  \item \textbf{Priority.} Where more than one terminal can match the
    same input at the same point in a parse, the one with higher
    priority is chosen:
""".strip()

_DISAMBIGUATION_REST = r"""
  \item \textbf{Positional constraints.} \synt{LINE\_START\_TEXT} may
    only begin immediately after a \synt{NewLine} or at the start of
    input; \synt{PROSE\_TEXT} may not begin in that position (reserved
    for \synt{LINE\_START\_TEXT}); \synt{REF} may not be immediately
    preceded by a word character or \term{/} (so it does not match
    inside identifiers or URLs).
  \item \textbf{Lookahead-conditioned terminals.} \synt{ProseInitial}
    and \synt{ProseTail} (used by \synt{LINE\_START\_TEXT} and
    \synt{PROSE\_TEXT} respectively) admit \term{\#} and
    \term{\textasciitilde} except where doing so would swallow a
    character that a higher-priority terminal is entitled to:
    \begin{itemize}
      \item \synt{ProseTail} is \synt{LINE\_CHAR}, except where the
        character is \term{\#} immediately followed by an optional
        \term{\#} and an uppercase letter (that prefix belongs to
        \synt{REF} instead).
      \item \synt{ProseInitial} is the same as \synt{ProseTail},
        additionally excluding \term{\textasciitilde} when
        immediately followed by a lowercase letter (that prefix
        belongs to \synt{SIGIL}/\synt{TEST\_SIGIL} instead).
    \end{itemize}
\end{itemize}
""".strip()


def _disambiguation() -> str:
    return "\n\n".join([
        _DISAMBIGUATION_INTRO,
        _priority_table(),
        _DISAMBIGUATION_REST,
    ])


# \synt and \term aren't backnaur commands -- backnaur only documents
# \bnfpn/\bnfts/\bnftd/etc. for use *inside* a bnf/bnf* environment (its
# "inline expressions" section covers \bnfpn/\bnfpo specifically, wrapped
# in math mode; it says nothing about using \bnfts in plain prose). Since
# that's unverified, \synt/\term are thin local aliases -- plain
# \textit/\texttt -- used only in the disambiguation prose below, which
# sits outside any bnf*  environment.
_PREAMBLE = r"""
% Grammar for .lob, typeset with the backnaur package
% (https://ctan.org/pkg/backnaur) -- chosen over mdwtools' `syntax`
% package after `syntax` turned out to clash with acmart.
%
% Generated by notlob/util/gen_grammar_latex.py from notlob/grammar.lark
% -- do not hand-edit; regenerate instead. See that script's own
% docstring for what parts of this file are mechanically derived vs
% hand-maintained.

\documentclass{article}
\usepackage[margin=1in]{geometry}
\usepackage[altpo]{backnaur}  % altpo: use ::= instead of the default |=

\newcommand{\synt}[1]{\textit{#1}}
\newcommand{\term}[1]{\texttt{#1}}

\begin{document}

\section*{Grammar}

Notation: \synt{italic} names are nonterminals (rendered
$\langle$like this$\rangle$ by \texttt{\textbackslash bnfpn}); typewriter
text is a literal terminal string (\texttt{\textbackslash bnfts}); italic
non-typewriter text in the terminals table is an ISO 14977 special
sequence -- a terminal described in prose because it is impractical to
spell out character-by-character (\texttt{\textbackslash bnftd}).
\texttt{|} separates alternatives, one per line for anything with more
than one. \texttt{[\,x\,]} means $x$ is optional; \texttt{\{\,x\,\}}
means zero or more repetitions of $x$; $x$\textsuperscript{+} means one
or more; \texttt{$x$ - $y$} means $x$ except for strings also matched by
$y$ (none of these four are backnaur primitives -- backnaur is a BNF, not
EBNF, tool, so this is a local convention layered on top, same as it
would be with any other BNF-only package).

\subsection*{Productions}

""".strip()

_MIDDLE = r"""

\subsection*{Terminals}

""".strip()

_END = r"""

\end{document}
""".strip()


def _render_figure(body: str, caption: str, label: str) -> str:
    return (
        "\\begin{figure}[t]\n"
        "  \\centering\n"
        "  \\grammarsize\n\n"
        + body + "\n\n"
        + f"\\caption{{{caption}}}\n"
        + f"\\label{{{label}}}\n"
        "\\end{figure}"
    )


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(
        description="Generate a backnaur-flavoured LaTeX fragment for notlob's grammar."
    )
    ap.add_argument(
        "--two-column", action="store_true",
        help=(
            "Emit two separate figure environments (productions and terminals) "
            "for inclusion in a paper via \\input{}. "
            "Default: emit a standalone LaTeX document for preview."
        ),
    )
    args = ap.parse_args()

    grammar_path = Path(__file__).resolve().parent.parent / "grammar.lark"
    productions, terminals, _priorities = parse_grammar(grammar_path)

    if args.two_column:
        fig_productions = _render_figure(
            render_bnf_block(productions),
            caption="Notlob grammar -- Productions.",
            label="fig:notlob_grammar_productions",
        )
        fig_terminals = _render_figure(
            render_bnf_block(terminals),
            caption="Notlob grammar -- Terminals.",
            label="fig:notlob_grammar_terminals",
        )
        print(fig_productions + "\n\n" + fig_terminals)
    else:
        parts = [
            _PREAMBLE,
            render_bnf_block(productions),
            _MIDDLE,
            render_bnf_block(terminals),
            _disambiguation(),
            _END,
        ]
        print("\n\n".join(parts))


if __name__ == "__main__":
    main()
