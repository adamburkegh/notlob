"""Tests for notlob.util.gen_grammar_latex.

Most of this module's job is mechanical (parse grammar.lark via Lark's
own meta-grammar, render the result as backnaur LaTeX) -- the tests
here mainly guard the parts that are still hand-maintained: the
_REGEX_OVERRIDES / _PRIORITY_TIERS staleness checks, and the newline/
name escaping fixes that make the output actually typeset correctly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from notlob.util.gen_grammar_latex import (
    D,
    NT,
    Except,
    Or,
    RepPlus,
    Seq,
    T,
    _check_priority_tiers,
    _convert_string,
    _priority_sentence,
    escape_name,
    escape_terminal,
    parse_grammar,
    render,
    render_bnf_block,
)

_GRAMMAR_PATH = Path(__file__).parent.parent / "notlob" / "grammar.lark"


# ── Real grammar.lark integration ───────────────────────────────

class TestParseRealGrammar:
    def test_parses_without_raising(self):
        productions, terminals, _priorities = parse_grammar(_GRAMMAR_PATH)
        assert productions
        assert terminals

    def test_named_test_production_present(self):
        productions, _, _priorities = parse_grammar(_GRAMMAR_PATH)
        names = {name for name, _ in productions}
        assert "named_test" in names
        assert "test_group" in names

    def test_test_sigil_is_its_own_terminal_not_in_sigil(self):
        # Regression: the old hand-maintained model had a stale bare
        # "~test" alternative folded into SIGIL, left over from before
        # TEST_SIGIL existed as its own terminal.
        _, terminals, _priorities = parse_grammar(_GRAMMAR_PATH)
        by_name = dict(terminals)
        assert "TEST_SIGIL" in by_name
        sigil = by_name["SIGIL"]
        assert isinstance(sigil, Or)
        rendered_alts = [render(alt) for alt in sigil.items]
        assert not any("test" in alt for alt in rendered_alts)

    def test_full_render_produces_nonempty_latex(self):
        productions, terminals, _priorities = parse_grammar(_GRAMMAR_PATH)
        prod_tex = render_bnf_block(productions)
        term_tex = render_bnf_block(terminals)
        assert prod_tex.startswith("\\begin{bnf*}")
        assert term_tex.startswith("\\begin{bnf*}")

    def test_no_raw_newline_survives_into_rendered_output(self):
        # Regression: literals like "~example\n" or "---\n" must have
        # their trailing newline split into NT("NewLine"), not embedded
        # raw in a \bnfts{...} argument.
        productions, terminals, _priorities = parse_grammar(_GRAMMAR_PATH)
        tex = render_bnf_block(productions) + render_bnf_block(terminals)
        for line in tex.splitlines():
            assert "\\bnfts{" not in line or line.count("{") == line.count("}")


# ── Regex-override staleness checks ─────────────────────────────

class TestOverrideStaleness:
    def test_unregistered_regex_terminal_raises(self, tmp_path):
        bad = tmp_path / "bad.lark"
        bad.write_text('start: FOO\nFOO: /[a-z]+/\n', encoding="utf-8")
        with pytest.raises(KeyError, match="_REGEX_OVERRIDES"):
            parse_grammar(bad)

    def test_priority_tier_mismatch_raises(self):
        with pytest.raises(ValueError, match="_PRIORITY_TIERS"):
            _check_priority_tiers({"SOME_TERMINAL": 99})


# ── Newline splitting ────────────────────────────────────────────

class TestConvertString:
    def test_plain_string_unaffected(self):
        assert _convert_string("abc") == T("abc")

    def test_bare_newline_becomes_newline_nt(self):
        assert _convert_string("\n") == NT("NewLine")

    def test_trailing_newline_split_out(self):
        result = _convert_string("~example\n")
        assert result == Seq(T("~example"), NT("NewLine"))


# ── Name/terminal escaping ───────────────────────────────────────

class TestEscaping:
    def test_underscore_escaped_in_name(self):
        assert escape_name("TEST_SIGIL") == r"TEST\_SIGIL"

    def test_plain_name_unaffected(self):
        assert escape_name("module") == "module"

    def test_tilde_escaped_in_terminal(self):
        assert escape_terminal("~test") == r"\textasciitilde{}test"

    def test_hash_escaped_in_terminal(self):
        assert escape_terminal("#Tests") == r"\#Tests"


# ── Priority sentence ─────────────────────────────────────────────

class TestPrioritySentence:
    def test_mentions_test_sigil(self):
        # Regression: the old hand-written disambiguation prose never
        # mentioned TEST_SIGIL's priority tier at all.
        assert "TEST" in _priority_sentence()

    def test_verb_agreement_singleton_tier(self):
        sentence = _priority_sentence()
        assert "which outranks" in sentence  # REF tier has one member


# ── Render pipeline (unchanged from the hand-written model) ──────

class TestRenderPipeline:
    def test_seq_renders_with_bnfsp(self):
        assert render(Seq(T("a"), T("b"))) == r"\bnfts{a} \bnfsp \bnfts{b}"

    def test_or_groups_nested_seq(self):
        node = RepPlus(Or(T("a"), Seq(T("b"), T("c"))))
        text = render(node)
        assert "(\\bnfts{b} \\bnfsp \\bnfts{c})" in text

    def test_except_renders_with_minus(self):
        assert render(Except(NT("X"), T("#"))) == r"\bnfpn{X} - \bnfts{\#}"

    def test_descriptive_phrase_renders_bnftd(self):
        assert render(D("any character")) == r"\bnftd{any character}"

    def test_space_literal_rejected(self):
        with pytest.raises(ValueError):
            render(T(" "))
