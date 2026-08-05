r"""Tests for notlob.util.gen_listings_lang.

The keyword list itself is mechanically derived (see
tests/test_gen_grammar_latex.py for the grammar-parsing guarantees);
what's specific to this module is the prefix-safety ordering `listings`
literate scanning depends on, the escaping in rendered entries, and
guarding against the two real compile-time/render-time bugs found by
actually pdflatex-compiling the generated output against a real paper
build (not just eyeballing the .tex text) -- see the module docstring
for the full story on why "#"-prefixed markers are excluded and why
replacements use \textcolor{}{} instead of \color{}.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from notlob.util.gen_grammar_latex import parse_grammar
from notlob.util.gen_listings_lang import (
    _VARIADIC_MARKERS,
    extract_keywords,
    render_listings_language,
)

_GRAMMAR_PATH = Path(__file__).parent.parent / "notlob" / "grammar.lark"


class TestExtractKeywords:
    def test_expected_keywords_present(self):
        _, terminals, _priorities = parse_grammar(_GRAMMAR_PATH)
        keywords = extract_keywords(terminals)
        assert set(keywords) == {
            "~example", "~run", "~run on-load", "~run on-invocation",
            "~property", "~test", "---",
        }

    def test_hash_prefixed_heads_excluded(self):
        # Regression: #Tests/#Binding/#References/#Appendix used to be
        # included, but "#" cannot be reliably used in a `literate`
        # pattern in this listings version (confirmed via real pdflatex
        # compiles -- see module docstring). Excluding them at the
        # source (not just leaving them unstyled) means there's nothing
        # left in the keyword list that could accidentally reintroduce
        # the bug.
        _, terminals, _priorities = parse_grammar(_GRAMMAR_PATH)
        keywords = extract_keywords(terminals)
        assert not any(kw.startswith("#") for kw in keywords)

    def test_sorted_longest_first(self):
        _, terminals, _priorities = parse_grammar(_GRAMMAR_PATH)
        keywords = extract_keywords(terminals)
        lengths = [len(kw) for kw in keywords]
        assert lengths == sorted(lengths, reverse=True)

    def test_deduplicated(self):
        # ~property's bare and named forms both start with "~property"
        _, terminals, _priorities = parse_grammar(_GRAMMAR_PATH)
        keywords = extract_keywords(terminals)
        assert keywords.count("~property") == 1


class TestPrefixSafety:
    def test_no_earlier_entry_shadows_a_later_one(self):
        # This is the property listings' `literate` scanning actually
        # depends on: at each input position it tries entries in list
        # order and uses the first match, so an earlier short pattern
        # that's a prefix of a later, more specific one would silently
        # steal the match.
        _, terminals, _priorities = parse_grammar(_GRAMMAR_PATH)
        keywords = extract_keywords(terminals)
        full_order = keywords + [text for text, _color in _VARIADIC_MARKERS]
        for i, earlier in enumerate(full_order):
            for later in full_order[i + 1:]:
                assert not later.startswith(earlier), (
                    f"{earlier!r} (position {i}) would shadow "
                    f"{later!r} later in the literate list"
                )


class TestRenderListingsLanguage:
    def test_no_commas_between_literate_triples(self):
        # Regression: `literate`'s value is a bare sequence of
        # {c}{r}{n} triples, not a comma-separated list -- a comma
        # between triples breaks listings' own scanning of the option.
        text = render_listings_language(["~example", "~test"])
        literate_section = text.split("literate=", 1)[1].split("basicstyle", 1)[0]
        # every line inside the literate block must not end with a
        # comma (only the very last line before basicstyle= does, as
        # the outer key=value separator)
        lines = [ln for ln in literate_section.splitlines() if ln.strip()]
        for line in lines[:-1]:
            assert not line.rstrip().endswith(","), line

    def test_hash_prefixed_pattern_raises(self):
        # Regression: confirmed via real pdflatex compile that "#" in a
        # `literate` pattern fails every escaping strategy tried (bare,
        # doubled, backslash-escaped all fail differently; moredelim
        # silently corrupts matched content instead). The renderer
        # fails loud rather than silently emitting a broken pattern, in
        # case a caller ever passes a "#"-prefixed keyword in.
        with pytest.raises(ValueError, match="#"):
            render_listings_language(["~example", "#Tests"])

    def test_replacement_uses_textcolor_not_bare_color(self):
        # Regression: confirmed via real pdflatex compile that a bare
        # \color{X} in a literate replacement is not self-scoping and
        # leaks its color onto every subsequent line in the listing
        # (the whole rest of a multi-line snippet after one match ended
        # up colored). \textcolor{X}{...} is self-contained.
        text = render_listings_language(["~example"])
        assert r"\textcolor{notlobsigil}{\textasciitilde{}example}" in text
        assert "\\color{notlobsigil}\\textasciitilde" not in text

    def test_produces_valid_lstdefinelanguage_block(self):
        text = render_listings_language(["~example"])
        assert "\\lstdefinelanguage{notlob}{" in text
        assert text.strip().endswith("}")

    def test_tilde_escaped_in_output(self):
        text = render_listings_language(["~example"])
        assert r"\textasciitilde{}example" in text
