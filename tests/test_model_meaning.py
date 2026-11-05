"""The model is the meaning (slice 11b).

A claim is a ``kind``, a ``mode`` and a ``name``, not a sigil string that
the graph splits again. An appendix has a ``name`` and no ``title``.
"""

from __future__ import annotations

import dataclasses

import pytest

from notlob import from_tree, parse
from notlob.model import CLAIM_KINDS, AppendixSection, Claim


def _claim(line: str) -> Claim:
    module = from_tree(parse(f"#M\n\n{line}\n    True\n"))
    (claim,) = [i for i in module.body if isinstance(i, Claim)]
    return claim


class TestAClaimIsItsMeaning:
    @pytest.mark.parametrize("line, kind, mode, name", [
        ("~example", "example", None, None),
        ("~run", "run", None, None),
        ("~run on-load", "run", "on-load", None),
        ("~run on-invocation", "run", "on-invocation", None),
        ("~property", "property", None, None),
        ("~property total", "property", None, "total"),
        ("~property  total \t", "property", None, "total"),
        ("~property two  words", "property", None, "two  words"),
    ])
    def test_each_form(self, line, kind, mode, name):
        claim = _claim(line)
        assert (claim.kind, claim.mode, claim.name) == (kind, mode, name)

    def test_there_is_no_sigil(self):
        fields = {f.name for f in dataclasses.fields(Claim)}
        assert "sigil" not in fields
        assert {"kind", "mode", "name", "lines"} <= fields

    def test_the_kinds_are_a_closed_set(self):
        assert set(CLAIM_KINDS) == {"example", "run", "property"}

    def test_the_lines_are_those_under_it(self):
        assert _claim("~run on-load").lines == ["    True"]


class TestAnAppendixHasAName:
    def test_no_title(self):
        fields = {f.name for f in dataclasses.fields(AppendixSection)}
        assert "title" not in fields and "name" in fields

    @pytest.mark.parametrize("line, name", [
        ("#Appendix", None), ("#Appendix Notes", "Notes"),
        ("#Appendix  Two  words ", "Two  words"),
    ])
    def test_its_name(self, line, name):
        module = from_tree(parse(f"#M\n\n---\n\n{line}\n\nText.\n"))
        (appendix,) = module.post_text.sections
        assert appendix.name == name
