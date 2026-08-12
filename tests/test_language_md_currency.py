"""Currency checks for notlob/docs/LANGUAGE.md against the real grammar
and CLI -- not a generator, a drift detector.

LANGUAGE.md is hand-written prose (see notlob/docs/DESIGN.md's "The
grammar is the specification" for why generating a narrative document
mechanically isn't the right fix), so it can't be auto-derived the way
gen_grammar_latex.py derives the paper's BNF listing. But the specific
things that actually went stale in practice -- an enumerable list of
sigils, #Binding declarations, CLI subcommands, semantic check names --
*can* be extracted from the real source and compared against what
LANGUAGE.md claims, the same way gen_listings_lang.py already extracts
the sigil keyword list from grammar.lark instead of hand-typing it.

This catches "we added/removed/renamed a thing and forgot to update
the reference" -- exactly what happened with #Appendix, `notlob mcp`,
`~run`'s on-load/on-invocation modes, and the removed
`~property-testing`/`~unit-testing` declarations, all found by hand in
one currency pass. It does NOT catch prose that's stale in *content*
while still naming the right thing (e.g. describing removed behaviour
for a sigil that still exists) -- that class still needs a human
rereading the doc occasionally.
"""

from __future__ import annotations

import re
from pathlib import Path

from notlob.util.gen_grammar_latex import Or, parse_grammar
from notlob.util.gen_listings_lang import _leading_literal, extract_keywords

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GRAMMAR = _REPO_ROOT / "notlob" / "grammar.lark"
_CLI = _REPO_ROOT / "notlob" / "cli.py"
_LANGUAGE_MD = _REPO_ROOT / "notlob" / "docs" / "LANGUAGE.md"


def _language_md() -> str:
    return _LANGUAGE_MD.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """Return the text of the section starting at *heading* (a line
    matched exactly, e.g. '### #Binding') up to the next heading of the
    same or coarser level. Raises if *heading* isn't found.

    Skips fenced code blocks while scanning for the next heading --
    LANGUAGE.md's own worked examples contain lines like `#Binding` or
    `#Tests` that would otherwise look like real markdown headings and
    end the section immediately.
    """
    lines = text.splitlines()
    level = len(heading) - len(heading.lstrip("#"))
    start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    end = len(lines)
    in_fence = False
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith("#"):
            other_level = len(stripped) - len(stripped.lstrip("#"))
            if other_level <= level:
                end = i
                break
    return "\n".join(lines[start:end])


def _cli_source() -> str:
    return _CLI.read_text(encoding="utf-8")


def _top_level_commands() -> set[str]:
    """Every ``sub.add_parser("name", ...)`` call -- top-level
    subcommands only, not ``qsub.add_parser(...)`` (the `notlob query`
    sub-subcommands, which LANGUAGE.md documents differently, as
    `notlob query <op>` lines rather than a flat command list)."""
    return set(re.findall(
        r'(?<!q)sub\.add_parser\(\s*["\'](\w+)["\']', _cli_source(),
    ))


def _check_only_choices() -> list[str]:
    """The ``choices=[...]`` list for ``check``'s ``--only`` argument."""
    src = _cli_source()
    check_block = src[src.index('"check",'):src.index('"check",') + 500]
    match = re.search(r"choices=\[([^\]]+)\]", check_block, re.DOTALL)
    return re.findall(r'"(\w+)"', match.group(1))


class TestSigilVocabulary:
    def test_every_base_sigil_mentioned(self):
        _, terminals, _ = parse_grammar(_GRAMMAR)
        keywords = extract_keywords(terminals)
        base_forms = {kw.split(" ", 1)[0] for kw in keywords if kw.startswith("~")}
        text = _language_md()
        missing = [kw for kw in base_forms if kw not in text]
        assert not missing, (
            f"grammar.lark defines sigil(s) {missing} that LANGUAGE.md "
            f"never mentions"
        )


class TestBindingDeclarations:
    def test_every_declaration_mentioned_in_binding_section(self):
        productions, terminals, _ = parse_grammar(_GRAMMAR)
        by_name_p = dict(productions)
        by_name_t = dict(terminals)
        rule = by_name_p["bind_detail_decl"]
        names = (
            [item.name for item in rule.items]
            if isinstance(rule, Or) else [rule.name]
        )
        declared = {
            _leading_literal(by_name_t[n]).strip() for n in names
        }
        section = _section(_language_md(), "### #Binding")
        missing = [d for d in declared if d not in section]
        assert not missing, (
            f"grammar.lark's #Binding declarations {missing} aren't "
            f"mentioned in LANGUAGE.md's '### #Binding' section"
        )


class TestCommandsSection:
    def test_every_cli_subcommand_mentioned(self):
        commands = _top_level_commands()
        section = _section(_language_md(), "## Commands")
        missing = [c for c in commands if f"notlob {c}" not in section]
        assert not missing, (
            f"cli.py registers subcommand(s) {missing} that LANGUAGE.md's "
            f"'## Commands' section never shows as `notlob {{name}}`"
        )


class TestSemanticChecksTable:
    def test_every_check_name_mentioned(self):
        choices = _check_only_choices()
        section = _section(_language_md(), "## Linting and checks")
        missing = [c for c in choices if f"`{c}`" not in section]
        assert not missing, (
            f"cli.py's `check --only` choices {missing} aren't listed in "
            f"LANGUAGE.md's '## Linting and checks' table"
        )
