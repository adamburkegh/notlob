"""The lint findings over the five example projects, pinned.

Slice 10 took ``Node.label`` out of ``Node``, and the checks read a node's
name where they read its label. This holds what they find to what they
found before: a check that read the wrong string would find different
things, or nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from notlob import build_package
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit
from notlob.check import run_checks

EXAMPLES = Path(__file__).parent.parent / "examples"

_KITS = {
    "roman": python_kit, "retail": python_kit, "gutenberg": python_kit,
    "haskell-roman": haskell_kit, "ts-media": typescript_kit,
}

#: ``(check, severity, message, addresses)`` of every finding, in the
#: order the checks ran.
PINNED: dict[str, list[tuple]] = {
    "gutenberg": [],
    "retail": [],
    "roman": [],
    "ts-media": [],
    "haskell-roman": [
        ("titles", "advisory",
         "similar titles: 'Roman Numerals App' / 'Roman Numerals' "
         "(similarity 67%)",
         ("roman/numerals/app", "roman/numerals")),
    ],
}


def _findings(project: str) -> list[tuple]:
    kit = _KITS[project]
    graph = build_package(
        EXAMPLES / project, kit.extract_symbols,
        call_extractor=kit.extract_calls, split_imports=kit.split_imports)
    found, _counts = run_checks(graph)
    return [(f.check, f.severity, f.message, f.addresses) for f in found]


@pytest.mark.parametrize("project", sorted(_KITS))
def test_the_findings_are_what_they_were(project):
    assert _findings(project) == PINNED[project]


#: Four of the five examples are clean, which pins little: a check that
#: read the wrong string would find nothing and pass. This module has
#: something for each check to find: symbols a letter apart, two verbs
#: for one noun, two titles alike (an appendix's among them), a symbol
#: mentioned and not referenced, two lists of bullets, a promise nothing
#: checks, and an import nothing uses.
SMALL = (
    "#Pricing Rules\n\n"
    "The Discount is applied to each order, and every order is checked.\n\n"
    "    class Discount: pass\n"
    "    def get_total(): pass\n"
    "    def fetch_total(): pass\n"
    "    def apply_discount(): pass\n"
    "    def apply_discoutn(): pass\n\n"
    "##Pricing Rules Set\n\n"
    "* a\n\n"
    "* b\n\n"
    "---\n\n"
    "#References\n    #Other Module\n\n"
    "#Appendix Glossary\n\n"
    "Text.\n"
)

PINNED_SMALL: list[tuple] = [
    ("imports", "error",
     "unused import: Pricing Rules imports Other Module but uses none of "
     "its symbols",
     ("pricing/rules", "other/module")),
    ("typos", "advisory",
     "near-duplicate: apply_discount / apply_discoutn (distance 2)",
     ("pricing/rules#apply_discount", "pricing/rules#apply_discoutn")),
    ("conventions", "advisory",
     "verb inconsistency for 'total': fetch vs get",
     ("pricing/rules#get_total", "pricing/rules#fetch_total")),
    ("titles", "advisory",
     "similar titles: 'Pricing Rules' / 'Pricing Rules Set' "
     "(similarity 67%)",
     ("pricing/rules", "pricing/rules#Pricing Rules Set")),
    ("references", "advisory",
     "'Discount' appears in prose but is never #-referenced",
     ("pricing/rules#Discount",)),
    ("style", "advisory",
     "Found 2 separate bullet point blocks. This suggests concepts need "
     "more articulation, or structure lacking from code or headings is "
     "being sought in prose.",
     ("pricing/rules#Pricing Rules Set",)),
]


def _small_findings() -> list[tuple]:
    from notlob import build, enrich, from_tree, parse
    from notlob.bindings.python import extract_symbols
    module = from_tree(parse(SMALL))
    graph = build(module)
    enrich(graph, module, extract_symbols)
    other = from_tree(parse("#Other Module\n"))
    graph.merge(build(other))
    from notlob import Edge, EdgeKind
    graph.add_edge(Edge(
        source="pricing/rules", target="other/module",
        kind=EdgeKind.IMPORTS))
    found, _counts = run_checks(graph)
    return [(f.check, f.severity, f.message, f.addresses) for f in found]


def test_a_module_that_has_something_for_each_check_to_find():
    assert _small_findings() == PINNED_SMALL
