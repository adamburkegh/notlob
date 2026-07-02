r"""Generate a backnaur-flavoured LaTeX fragment describing notlob's grammar.

Usage::

    notlobenv/Scripts/python scripts/gen_grammar_latex.py > var/notlob_grammar.tex

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
That's the actual "whack-a-mole" problem, not the overall structure (which
has been gotten right by hand several times over already, at this point).

This script doesn't parse ``grammar.lark`` itself -- its regex-heavy
terminal definitions don't map onto BNF notation without human judgement
(see the ``PROSE_TEXT`` / ``PROSE_NL`` "except"/lookahead handling below,
which is a deliberate abstraction, not a mechanical transcription -- see
notlob/docs/DESIGN.md, "The grammar is the specification"). Instead, the
PRODUCTIONS and TERMINALS lists below are a small, hand-maintained model
of the same grammar, and this script's only job is to render that model
into correctly-escaped ``backnaur`` LaTeX, reliably, every time. When
``grammar.lark`` changes, update the model below to match; the rendering
itself never needs touching by hand again.

KNOWN GAP (deliberately deferred, not an oversight): PRODUCTIONS and
TERMINALS can still drift out of sync with the real grammar.lark, since
nothing here checks that. The PRODUCTIONS half of that is fixable without
much difficulty -- grammar.lark's rule syntax (`|`, `*`, `+`, `?`, parens)
is mechanically identical to this script's own AST, so it could be parsed
straight out of the real file instead of hand-duplicated. TERMINALS can't
be auto-derived the same way (that's the regex-to-prose judgement call
above), but could at least be cross-checked against grammar.lark's actual
terminal names/priorities, so a change there that isn't reflected here
fails loudly instead of drifting silently -- the same pattern already
used for the sigil vocabulary in tests/test_graph_completeness.py.
Revisit after the paper's first draft; not worth the extra build-out
before the content itself has been validated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

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


@dataclass(frozen=True)
class Break:
    """A manual line-break point, valid only as a direct item of the
    Seq passed as a production's top-level right-hand side (see
    render_production) -- backnaur's \\bnfmore is a sibling of
    \\bnfprod, not something that can be nested inside a grouped
    sub-expression, so a Break anywhere else can't be honoured."""


Node = Union[NT, T, D, Seq, Or, Opt, Rep, RepPlus, Except, Break]


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
}


def escape_terminal(text: str) -> str:
    """Escape *text* for safe use inside \\bnfts{...}."""
    return "".join(_TERMINAL_ESCAPES.get(ch, ch) for ch in text)


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
        return f"\\bnfpn{{{node.name}}}"
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
    if isinstance(node, Break):
        raise TypeError(
            "Break is only valid as a direct item of a production's "
            "top-level Seq (see render_production) -- it can't be "
            "rendered as part of an ordinary expression"
        )
    raise TypeError(f"unhandled node type: {node!r}")


def _split_on_breaks(items: tuple[Node, ...]) -> list[list[Node]]:
    """Split *items* into segments at each Break marker, dropping the
    markers themselves. Empty segments (e.g. a Break at either end) are
    dropped too."""
    segments: list[list[Node]] = [[]]
    for item in items:
        if isinstance(item, Break):
            segments.append([])
        else:
            segments[-1].append(item)
    return [seg for seg in segments if seg]


def render_production(name: str, rhs: Node) -> list[str]:
    """Return the backnaur source lines for one production (no
    trailing '\\\\' -- the caller joins lines across all productions)."""
    if isinstance(rhs, Or) and len(rhs.items) > 1:
        first, *rest = rhs.items
        lines = [f"\\bnfprod{{{name}}}\n    {{{render(first)}}}"]
        lines += [f"\\bnfmore{{\\bnfor {render(item)}}}" for item in rest]
        return lines
    if isinstance(rhs, Seq) and any(isinstance(i, Break) for i in rhs.items):
        segments = _split_on_breaks(rhs.items)
        first, *rest = segments
        lines = [f"\\bnfprod{{{name}}}\n    {{{render(Seq(*first))}}}"]
        lines += [f"\\bnfmore{{{render(Seq(*seg))}}}" for seg in rest]
        return lines
    return [f"\\bnfprod{{{name}}}\n    {{{render(rhs)}}}"]


def render_bnf_block(productions: list[tuple[str, Node]]) -> str:
    lines: list[str] = []
    for name, rhs in productions:
        lines += render_production(name, rhs)
    body = " \\\\\n".join(lines)
    return f"\\begin{{bnf*}}\n{body}\n\\end{{bnf*}}"


# ── The grammar model ────────────────────────────────────────────
#
# Mirrors notlob/grammar.lark. Keep in sync by hand when that file
# changes; see the module docstring for why this isn't done by parsing
# grammar.lark directly.

PRODUCTIONS: list[tuple[str, Node]] = [
    ("Start", NT("Module")),
    ("Module", Seq(NT("ModHead"), NT("Body"), Opt(NT("PostText")))),
    ("Body", Rep(NT("BodyItem"))),
    ("BodyItem", Or(NT("Subheading"), NT("CodeBlock"), NT("Claim"),
                     NT("ProseBlock"), NT("BulletBlock"), NT("Blank"))),
    ("Subheading", Seq(NT("SubHead"), Rep(NT("SubItem")))),
    ("SubItem", Or(NT("CodeBlock"), NT("Claim"), NT("ProseBlock"),
                    NT("BulletBlock"), NT("Blank"))),
    ("CodeBlock", Seq(NT("Indent"), Rep(NT("BodyLine")))),
    ("BodyLine", Or(NT("Indent"), NT("Blank"))),
    ("Claim", Seq(NT("Sigil"), RepPlus(NT("BodyLine")))),
    ("ProseBlock", RepPlus(NT("ProseLine"))),
    ("ProseLine", Seq(RepPlus(Or(NT("LineStartText"), NT("ProseText"), NT("Ref"))),
                       NT("ProseNL"))),
    ("BulletBlock", RepPlus(NT("Bullet"))),
    ("PostText", Seq(NT("Separator"), Rep(Or(NT("Blank"), NT("PostSection"))))),
    ("PostSection", Or(NT("TestsSection"), NT("BindingSection"),
                        NT("ReferencesSection"), NT("AppendixSection"))),
    ("TestsSection", Seq(NT("TestsHead"), Rep(Or(NT("Blank"), NT("TestItem"))))),
    ("TestItem", Or(NT("TestGroup"), NT("Indent"))),
    ("TestGroup", Seq(NT("SubHead"), Rep(Or(NT("Indent"), NT("Blank"))))),
    ("BindingSection", Seq(NT("BindingHead"), Rep(Or(NT("Indent"), NT("Blank"))))),
    ("ReferencesSection", Seq(NT("ReferencesHead"), Rep(Or(NT("Indent"), NT("Blank"))))),
    ("AppendixSection", Seq(NT("AppendixHead"), Rep(NT("BodyItem")))),
]

TERMINALS: list[tuple[str, Node]] = [
    ("ModHead", Seq(T("#"), NT("NonHashLineChar"), NT("RestOfLine"), NT("NewLine"))),
    ("SubHead", Seq(T("##"), NT("RestOfLine"), NT("NewLine"))),
    ("Sigil", Or(
        Seq(T("~example"), NT("NewLine")),
        Seq(T("~run"), NT("NewLine")),
        Seq(T("~test"), NT("NewLine")),
        Seq(T("~property"), NT("NewLine")),
        Seq(T("~property "), NT("RestOfLine"), NT("NewLine")),
    )),
    ("Separator", Seq(T("---"), NT("NewLine"))),
    ("TestsHead", Seq(T("#Tests"), NT("NewLine"))),
    ("BindingHead", Seq(T("#Binding"), NT("NewLine"))),
    ("ReferencesHead", Seq(T("#References"), NT("NewLine"))),
    ("AppendixHead", Seq(T("#Appendix:"), NT("RestOfLine"), NT("NewLine"))),
    ("Indent", Seq(Or(NT("Space"), NT("Tab")), NT("RestOfLine"), NT("NewLine"))),
    ("Blank", NT("NewLine")),
    ("Bullet", Seq(T("*"), Opt(Seq(Or(NT("Space"), NT("Tab")), NT("RestOfLine"))), NT("NewLine"))),
    ("Ref", Seq(Or(T("#"), T("##")), NT("UpperLetter"), Rep(NT("WordChar")),
                Break(),
                Rep(Seq(NT("Space"), NT("UpperLetter"), Rep(NT("WordChar")))))),
    ("LineStartText", Seq(NT("ProseInitial"), Rep(NT("ProseTail")))),
    ("ProseText", RepPlus(NT("ProseTail"))),
    ("ProseNL", NT("NewLine")),
    ("LineChar", D("any character other than newline")),
    ("RestOfLine", Rep(NT("LineChar"))),
    ("NonHashLineChar", Except(NT("LineChar"), T("#"))),
    ("UpperLetter", D("an uppercase ASCII letter")),
    ("WordChar", D("an ASCII letter, digit, or underscore")),
    ("Space", D("a space character")),
    ("Tab", D("the tab character")),
    ("NewLine", D("the newline character")),
]

_DISAMBIGUATION = r"""
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
overlap in the strings they can match (e.g.\ \synt{SubHead} and
\synt{Ref} can both match \term{\#\#Stacking Discounts}), because
which one applies depends on where the text occurs, not what it looks
like in isolation. A deterministic single-pass (LALR) parser resolves
this the same way lexer generators conventionally do -- by an explicit
disambiguation rule external to the grammar, analogous to flex/lex's
``longest match, first rule wins'' or the standard resolution of the
dangling-\term{else} ambiguity in C's grammar:

\begin{itemize}
  \item \textbf{Priority.} Where more than one terminal can match the
    same input at the same point in a parse, the one with higher
    priority is chosen: \synt{Separator}, \synt{TestsHead},
    \synt{BindingHead}, \synt{ReferencesHead}, \synt{AppendixHead}
    (priority 20) outrank \synt{ModHead}, \synt{SubHead},
    \synt{Sigil} (priority 10), which outrank \synt{Indent},
    \synt{Bullet} (priority 8), which outrank \synt{Ref} (priority
    5), which outranks \synt{ProseText} and \synt{LineStartText}
    (priority 1, the fallback).
  \item \textbf{Positional constraints.} \synt{LineStartText} may only
    begin immediately after a \synt{NewLine} or at the start of input;
    \synt{ProseText} may not begin in that position (reserved for
    \synt{LineStartText}); \synt{Ref} may not be immediately
    preceded by a word character or \term{/} (so it does not match
    inside identifiers or URLs).
  \item \textbf{Lookahead-conditioned terminals.} \synt{ProseInitial}
    and \synt{ProseTail} (used by \synt{LineStartText} and
    \synt{ProseText} respectively) admit \term{\#} and
    \term{\textasciitilde} except where doing so would swallow a
    character that a higher-priority terminal is entitled to:
    \begin{itemize}
      \item \synt{ProseTail} is \synt{LineChar}, except where the
        character is \term{\#} immediately followed by an optional
        \term{\#} and an uppercase letter (that prefix belongs to
        \synt{Ref} instead).
      \item \synt{ProseInitial} is the same as \synt{ProseTail},
        additionally excluding \term{\textasciitilde} when
        immediately followed by a lowercase letter (that prefix
        belongs to \synt{Sigil} instead).
    \end{itemize}
\end{itemize}
""".strip()

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
% Generated by scripts/gen_grammar_latex.py -- do not hand-edit; update
% the PRODUCTIONS/TERMINALS model in that script instead and regenerate.

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


def main() -> None:
    parts = [
        _PREAMBLE,
        render_bnf_block(PRODUCTIONS),
        _MIDDLE,
        render_bnf_block(TERMINALS),
        _DISAMBIGUATION,
        _END,
    ]
    print("\n\n".join(parts))


if __name__ == "__main__":
    main()
