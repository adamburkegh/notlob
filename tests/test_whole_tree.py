"""The parse tree is the whole source (slice 11).

Every character of a ``.lob`` file is in exactly one token of the tree, in
order: no marker is dropped, no name is folded into a marker. A token's
type is one thing, and no name in ``grammar.lark`` begins with ``_``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from lark import Lark, Token, Tree
from lark.exceptions import UnexpectedInput

from notlob import parse
from notlob.parser import _GRAMMAR

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"
GRAMMAR = ROOT / "notlob" / "grammar.lark"

LOBS = sorted(EXAMPLES.rglob("*.lob"))

_POST = "#M\n\n---\n\n"
_TESTS = _POST + "#Tests\n\n"

AWKWARD = {
    "spaced title":        "# Title\n",
    "title, trailing":     "#Title \t \n",
    "bare appendix":       _POST + "#Appendix\n",
    "bare appendix, space": _POST + "#Appendix  \t\n\nText.\n",
    "appendix":            _POST + "#Appendix Notes\n\nText.\n",
    "appendix, trailing":  _POST + "#Appendix Notes \t\n\nText.\n",
    "appendix, two words": _POST + "#Appendix  Two  words\n\nText.\n",
    "test, two spaces":    _TESTS + "##g\n~test  two-spaces\n    1 == 1\n",
    "test, tab":           _TESTS + "##g\n~test\tt\n    1 == 1\n",
    "group, spaced":       _TESTS + "## g \t\n    1 == 1\n",
    "heading, trailing":   "#M\n\n##Sub \t \n\nText.\n",
    "heading, spaced":     "#M\n\n## Sub\n\nText.\n",
    "bare property":       "#M\n\n~property\n    True\n",
    "named property":      "#M\n\n~property total\n    True\n",
    "property, spaces":    "#M\n\n~property  total \t\n    True\n",
    "sigils":              "#M\n\n~example\n    1 == 1\n\n~run\n    f()\n",
    "no final newline":    "#M\n\nText.\n",
}


def tokens(tree: Tree) -> list[Token]:
    return list(tree.scan_values(lambda v: isinstance(v, Token)))


def gaps(tree: Tree, source: str) -> list[tuple[int, int, str]]:
    """Where the tokens, in order, do not tile *source*: (from, to, the
    text between) for a gap or an overlap, and the end of it."""
    found, at = [], 0
    for tok in tokens(tree):
        if tok.start_pos != at:
            found.append((at, tok.start_pos, source[at:tok.start_pos]))
        at = tok.end_pos
    if at != len(source):
        found.append((at, len(source), source[at:]))
    return found


def parsed(source: str) -> tuple[Tree, str]:
    return parse(source), (source if source.endswith("\n") else source + "\n")


# ── The tree is whole ────────────────────────────────────────

class TestTheTreeIsWhole:
    def test_there_are_examples(self):
        assert len(LOBS) >= 13

    @pytest.mark.parametrize("path", LOBS, ids=lambda p: p.name)
    def test_an_example_file(self, path):
        tree, source = parsed(path.read_text(encoding="utf-8"))
        assert gaps(tree, source) == []

    @pytest.mark.parametrize("case", AWKWARD)
    def test_an_awkward_source(self, case):
        tree, source = parsed(AWKWARD[case])
        assert gaps(tree, source) == []

    @pytest.mark.parametrize("path", LOBS, ids=lambda p: p.name)
    def test_the_value_of_a_token_is_its_text_in_an_example(self, path):
        tree, source = parsed(path.read_text(encoding="utf-8"))
        for tok in tokens(tree):
            assert str(tok) == source[tok.start_pos:tok.end_pos]

    @pytest.mark.parametrize("case", AWKWARD)
    def test_the_value_of_a_token_is_its_text(self, case):
        tree, source = parsed(AWKWARD[case])
        for tok in tokens(tree):
            assert str(tok) == source[tok.start_pos:tok.end_pos]

    def test_a_marker_dropped_from_the_tree_is_a_gap(self):
        """The check does catch what 790716c did: a copy of the grammar
        whose `#` marker begins with `_`."""
        filtered = _GRAMMAR.replace("MOD_MARK", "_MOD_MARK")
        assert filtered != _GRAMMAR
        lark = Lark(filtered, parser="lalr", propagate_positions=True,
                    regex=True)
        source = "#Title\n\nText.\n"
        assert gaps(lark.parse(source), source) == [(0, 1, "#")]


# ── No name begins with an underscore ────────────────────────

def _names_used(text: str) -> set[str]:
    """The rule and terminal names the grammar writes: what is left of
    it once comments, strings and regexps are taken out."""
    bare = re.sub(r"//[^\n]*", "", text)
    bare = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', bare)
    bare = re.sub(r"/(?:\\.|[^/\\\n])+/[a-z]*", "//", bare)
    return set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", bare))


class TestNoNameBeginsWithAnUnderscore:
    def test_the_grammar_file(self):
        names = _names_used(GRAMMAR.read_text(encoding="utf-8"))
        assert "start" in names and "NAME" in names
        assert sorted(n for n in names if n.startswith("_")) == []

    def test_the_check_sees_one(self):
        assert _names_used("a: _b\n_C: /x_y/ // _d\n") == {"a", "_b", "_C"}


# ── A property ───────────────────────────────────────────────

def _claim(source: str) -> Tree:
    (claim,) = parse(source).find_data("claim")
    return claim


class TestAProperty:
    def test_a_bare_one_is_a_sigil(self):
        claim = _claim("#M\n\n~property\n    True\n")
        assert claim.children[0].type == "SIGIL"
        assert not list(claim.find_data("property_head"))

    def test_a_named_one_is_a_property_head(self):
        claim = _claim("#M\n\n~property total\n    True\n")
        head = claim.children[0]
        assert head.data == "property_head"
        assert [t.type for t in head.children] == [
            "PROPERTY_MARK", "SPACE", "NAME", "EOL"]
        assert [str(t) for t in head.children[:3]] == [
            "~property", " ", "total"]


# ── Names ────────────────────────────────────────────────────

def _names(source: str, rule: str) -> list[str]:
    return [str(t) for node in parse(source).find_data(rule)
            for t in node.children if t.type == "NAME"]


class TestAHeadHoldsItsNameAsANAMEToken:
    def test_a_module(self):
        assert _names("#  Two  words \n", "module_head") == ["Two  words"]

    def test_a_subheading(self):
        assert _names("#M\n\n## Sub \t\n\nText.\n", "sub_head") == ["Sub"]

    def test_a_group(self):
        assert _names(_TESTS + "##g\n    1 == 1\n", "sub_head") == ["g"]

    def test_a_test(self):
        assert _names(
            _TESTS + "##g\n~test  t u\n    1 == 1\n", "test_head") == ["t u"]

    def test_an_appendix(self):
        assert _names(_POST + "#Appendix Notes\n", "appendix_head") == [
            "Notes"]

    def test_a_bare_appendix_has_none(self):
        assert _names(_POST + "#Appendix\n", "appendix_head") == []


class TestSubItemsAndBodyLinesAreNodes:
    def test_a_sub_item(self):
        tree = parse("#M\n\n##Sub\n\nText.\n")
        assert list(tree.find_data("sub_item"))

    def test_a_body_line(self):
        tree = parse("#M\n\n    x = 1\n    y = 2\n")
        assert len(list(tree.find_data("body_line"))) == 1


# ── What is refused ──────────────────────────────────────────

class TestRefused:
    @pytest.mark.parametrize("head", ["#AppendixFoo", "#Appendix: Notes"])
    def test_an_appendix_with_no_space_before_its_name(self, head):
        with pytest.raises(UnexpectedInput):
            parse(_POST + head + "\n\nText.\n")
