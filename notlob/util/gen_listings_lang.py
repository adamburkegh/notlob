r"""Generate a \lstdefinelanguage{notlob} block for typesetting .lob
source in the paper with the `listings` package (chosen over `minted`
for ACM-template compatibility and no Python/shell-escape dependency).

Usage::

    notlobenv/Scripts/python notlob/util/gen_listings_lang.py > var/notlob_listings.tex

Then in the paper's preamble::

    \usepackage{listings}
    \usepackage{xcolor}
    \input{var/notlob_listings.tex}
    ...
    \begin{lstlisting}[language=notlob]
    ...
    \end{lstlisting}

Where the keyword list comes from
----------------------------------
The *fixed* keywords -- ``~example``, ``~run``, ``~property``, ``~test``,
``---`` -- are extracted from gen_grammar_latex.parse_grammar()'s
output, the same parse of ``notlob/grammar.lark`` Step 1 uses. This is a
deliberate reuse, not a second hand-typed keyword list that could drift
independently of the grammar: if a sigil is renamed or removed in
grammar.lark, this list changes with it automatically.

Why ``#``-prefixed markers are NOT colored
--------------------------------------------
``#Tests``, ``#Binding``, ``#References``, ``#Appendix:``, ``##``, and
bare ``#`` are deliberately absent from the generated `literate` table,
confirmed against a real compile (MiKTeX 23.12 / listings, pdflatex) --
this is not an oversight, it's a real limitation of this listings
version's `literate` implementation:

- A bare ``#`` in a `literate` *pattern* is TeX's catcode-6
  macro-parameter character in the context listings scans it --
  ``{#Tests}...`` fails at ``\lstdefinelanguage`` parse time with
  "Illegal parameter number in definition of \\lstlang@notlob$".
- Doubling it (``##Tests``, TeX's usual escape for a literal ``#`` in
  parameter-text position) gets past parse time, but then fails later,
  the first time the language is actually used in a listing, with
  "Illegal parameter number in definition of \\lst@literate" --
  `literate`'s internal dispatch table is compiled lazily at first use,
  and something about the doubled pattern breaks *that* macro
  construction instead.
- Escaping it as ``\#`` (the normally-correct LaTeX way to print a
  literal hash) fails a third, different way: "Improper alphabetic
  constant" -- `literate` apparently expects single catcode-12
  characters in its pattern, not a control-symbol token.
- Switching to `moredelim` (a different listings mechanism, used by
  listings' own bundled languages for ``#``-comment syntax via
  ``morecomment=[l]\#``) avoids the compile error, but silently
  corrupts the *typeset content* instead: characters from the matched
  delimiter go missing (``##Subhead`` renders as ``#Subhead``,
  ``#Tests`` renders as ``Tests`` with no hash at all). That's worse
  than a compile error -- wrong `.lob` source shown in the paper with
  no warning.

Every one of these was verified with an actual pdflatex compile, not
inferred from documentation. ``~``-prefixed sigils and the ``*``
bullet marker have no such problem (confirmed working, including with
multiple entries active together) -- only ``#`` is affected. The
practical consequence: ``#``-prefixed structural markers in a rendered
`.lob` listing appear in the listing's plain `basicstyle`, uncolored,
which is faithful and uncorrupted, just not extra-highlighted.

Replacements MUST use \textcolor{color}{text}, not \color{color}text
-----------------------------------------------------------------------
``\color{X}`` is not self-scoping -- it applies from that point to the
end of the enclosing TeX group. `literate` does not appear to preserve
a replacement's outer ``{{...}}`` as a real group boundary during
typesetting, so a bare ``\color{X}`` in a replacement stains every
following line in the listing the same color (confirmed against a real
compile: an entire multi-line snippet after a single ``~property``
match all rendered in the sigil's color). ``\textcolor{X}{text}`` is
self-contained and doesn't leak.

What's still hand-authored
----------------------------
Colors, and the ``*`` bullet marker (a variadic prefix -- it's followed
by arbitrary item text, so there's no fixed grammar.lark terminal to
extract it from; the grammar defines BULLET as a whole-line pattern,
not a marker-plus-content pair). This is a presentation/styling choice,
not a semantic transcription of the grammar, so unlike
gen_grammar_latex.py there's no fail-loud staleness check to add here.
"""

from __future__ import annotations

from pathlib import Path

from notlob.util.gen_grammar_latex import Node, Or, Seq, T, parse_grammar

# ── Which terminals contribute fixed keywords ────────────────────
#
# Deliberately excludes TESTS_HEAD/BINDING_HEAD/REFERENCES_HEAD/
# APPENDIX_HEAD -- all "#"-prefixed, and "#" cannot be reliably used in
# a `literate` pattern in this listings version (see module docstring).

_KEYWORD_TERMINALS = ["SIGIL", "TEST_SIGIL", "SEPARATOR"]


def _leading_literal(node: Node) -> str | None:
    """Return the fixed literal text *node* begins with (the keyword
    itself), or None if it doesn't start with one -- shouldn't happen
    for the terminals in _KEYWORD_TERMINALS, all of which begin with a
    literal string by construction."""
    if isinstance(node, T):
        return node.text
    if isinstance(node, Seq) and node.items:
        return _leading_literal(node.items[0])
    return None


def extract_keywords(terminals: list[tuple[str, Node]]) -> list[str]:
    """Pull the fixed keyword strings out of _KEYWORD_TERMINALS'
    parsed definitions, deduped (e.g. ``~property``'s bare and named
    forms both start with the same literal) and sorted longest-first
    for safe `listings` literate ordering."""
    by_name = dict(terminals)
    keywords: list[str] = []
    for name in _KEYWORD_TERMINALS:
        node = by_name[name]
        alternatives = node.items if isinstance(node, Or) else [node]
        for alt in alternatives:
            literal = _leading_literal(alt)
            if literal is None:
                raise ValueError(
                    f"terminal {name!r} alternative {alt!r} doesn't "
                    f"start with a literal -- _KEYWORD_TERMINALS "
                    f"assumes all of these are literal-prefixed"
                )
            keywords.append(literal.rstrip())

    seen: set[str] = set()
    unique: list[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return sorted(unique, key=len, reverse=True)


# ── Hand-authored: colors and the bullet marker ──────────────────
#
# Muted, print-safe tones chosen to stay distinguishable under
# grayscale conversion (varying lightness, not just hue) -- a
# reasonable starting point, easy to retint once the paper has a
# settled visual style.

_COLORS: dict[str, str] = {
    "notlobstruct": "1B3A5C",   # --- separator
    "notlobsigil": "5B2A6E",    # claim sigils (~example, ~test, ...)
    "notlobbullet": "6E5B1B",   # *
}

# (pattern, color-name) -- the one variadic marker that's safe to
# highlight (see module docstring for why "#"/"##" are excluded).
_VARIADIC_MARKERS: list[tuple[str, str]] = [
    ("*", "notlobbullet"),
]


def _literate_entry(text: str, color: str) -> str:
    if "#" in text:
        raise ValueError(
            f"{text!r} contains '#', which cannot be reliably used in "
            f"a listings `literate` pattern in this environment -- "
            f"every escaping strategy tried (bare, doubled, "
            f"backslash-escaped) fails differently, and moredelim "
            f"silently corrupts matched content instead of colouring "
            f"it. See this module's docstring. Don't add '#'-prefixed "
            f"entries to _KEYWORD_TERMINALS or _VARIADIC_MARKERS."
        )
    # \textcolor{color}{...}, not \color{color}..., so the color is
    # self-scoped to just this replacement -- see module docstring.
    replacement_text = (
        text.replace("\\", r"\textbackslash{}")
        .replace("#", r"\#")
        .replace("~", r"\textasciitilde{}")
    )
    return (
        f"    {{{text}}}"
        f"{{{{\\textcolor{{{color}}}{{{replacement_text}}}}}}}{len(text)}"
    )


def render_listings_language(keywords: list[str]) -> str:
    color_defs = "\n".join(
        f"\\definecolor{{{name}}}{{HTML}}{{{hexcode}}}"
        for name, hexcode in _COLORS.items()
    )
    literate_lines = []
    for kw in keywords:
        color = "notlobsigil" if kw.startswith("~") else "notlobstruct"
        literate_lines.append(_literate_entry(kw, color))
    for text, color in _VARIADIC_MARKERS:
        literate_lines.append(_literate_entry(text, color))
    # listings' `literate` value is a bare sequence of {c}{r}{n}
    # triples, delimited only by their own braces -- NOT a
    # comma-separated list. A comma between triples would prematurely
    # end listings' custom scan for `literate`'s value and break
    # parsing of the surrounding \lstdefinelanguage options.
    literate_body = "\n".join(literate_lines)

    return f"""\
% Generated by notlob/util/gen_listings_lang.py from notlob/grammar.lark
% -- do not hand-edit; regenerate instead. See that script's own
% docstring for what's mechanically derived vs hand-authored, and for
% why "#"-prefixed markers (#Tests, #Binding, ##, ...) are deliberately
% not colored here.
%
% Requires: \\usepackage{{listings}} \\usepackage{{xcolor}}

{color_defs}

\\lstdefinelanguage{{notlob}}{{
  literate=
{literate_body},
  basicstyle=\\ttfamily\\small,
  columns=fullflexible,
  keepspaces=true,
  breaklines=true,
  showstringspaces=false,
  morecomment=[l]{{}},   % .lob has no comment syntax -- prose is content
}}
"""


def main() -> None:
    grammar_path = Path(__file__).resolve().parent.parent / "grammar.lark"
    _productions, terminals, _priorities = parse_grammar(grammar_path)
    keywords = extract_keywords(terminals)
    print(render_listings_language(keywords), end="")


if __name__ == "__main__":
    main()
