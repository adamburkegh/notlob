"""Meta-test: every structural element in a parsed Module should be
represented in the name graph.

If a new sigil or structural element is added to the parser but not
wired into build() or enrich(), these tests fail.
"""

from __future__ import annotations

from notlob import from_tree, parse
from notlob.graph import (
    NodeKind, build, enrich, claim_address,
    subheading_address,
)
from notlob.bindings.python.symbols import extract_symbols
from notlob.model import Claim, Subheading

# ── Registry of body sigils ──────────────────────────────────
#
# Every sigil that can appear in the module body must be listed
# here, mapped to the NodeKind it produces in the graph.
#
# Adding a new sigil to the parser without updating this mapping
# will cause test_all_body_sigils_are_registered to fail.

_SIGIL_KINDS: dict[str, NodeKind] = {
    "~example":  NodeKind.EXAMPLE,
    "~property": NodeKind.PROPERTY,
    "~run":      NodeKind.RUN,
}


# ── Comprehensive source ────────────────────────────────────

_COMPREHENSIVE = """\
#Comprehensive

A module exercising every structural element.

    CONSTANT = 42

    def helper():
        return CONSTANT

~example
    helper() == 42

~property roundtrip
    def _(n): assert n == n

~property
    def _(x): assert x == x

~run
    print(helper())

##Sub Section

    def sub_func():
        return 1

~example
    sub_func() == 1

---

#Tests
    helper() == 42

##edge cases
    CONSTANT == 42
"""


# ── Tests ────────────────────────────────────────────────────

class TestAllBodySigilsRegistered:
    """Verify that every body-level sigil encountered in the parsed
    module is accounted for in _SIGIL_KINDS or _EXCLUDED_SIGILS.
    """

    def _collect_sigils(self, module):
        """Collect unique sigil prefixes from body Claims."""
        sigils: set[str] = set()
        for item in module.body:
            if isinstance(item, Claim):
                sigils.add(item.sigil.split(None, 1)[0])
            elif isinstance(item, Subheading):
                for sub in item.body:
                    if isinstance(sub, Claim):
                        sigils.add(sub.sigil.split(None, 1)[0])
        return sigils

    def test_all_body_sigils_are_registered(self):
        module = from_tree(parse(_COMPREHENSIVE))
        sigils = self._collect_sigils(module)
        unknown = sigils - set(_SIGIL_KINDS)
        assert unknown == set(), (
            f"Body sigil(s) {unknown} found in parser output but not "
            f"registered in _SIGIL_KINDS — add them to the graph"
        )

    def test_comprehensive_has_all_known_sigils(self):
        module = from_tree(parse(_COMPREHENSIVE))
        sigils = self._collect_sigils(module)
        missing = set(_SIGIL_KINDS) - sigils
        assert missing == set(), (
            f"Registered sigil(s) {missing} not exercised in "
            f"_COMPREHENSIVE source — add an example"
        )

    def test_matches_parser_known_sigils(self):
        """The parser's closed sigil vocabulary and the graph's sigil
        registry must name exactly the same set — the parser rejects
        anything outside it, so the graph can never see anything else.
        """
        from notlob.parser import _KNOWN_SIGILS
        assert set(_KNOWN_SIGILS) == set(_SIGIL_KINDS)


class TestRunInGraph:
    def test_run_node_present(self):
        module = from_tree(parse(_COMPREHENSIVE))
        graph = build(module)
        enrich(graph, module, extract_symbols)
        addr = claim_address("comprehensive", "run", 1)
        node = graph.node(addr)
        assert node is not None
        assert node.kind == NodeKind.RUN

    def test_run_content(self):
        module = from_tree(parse(_COMPREHENSIVE))
        graph = build(module)
        enrich(graph, module, extract_symbols)
        addr = claim_address("comprehensive", "run", 1)
        node = graph.node(addr)
        assert node.content is not None
        assert "print(helper())" in node.content["code"]


class TestExamplesInGraph:
    def test_module_level_example(self):
        module = from_tree(parse(_COMPREHENSIVE))
        graph = build(module)
        enrich(graph, module, extract_symbols)
        addr = claim_address("comprehensive", "example", 1)
        node = graph.node(addr)
        assert node is not None
        assert node.kind == NodeKind.EXAMPLE

    def test_subheading_example(self):
        module = from_tree(parse(_COMPREHENSIVE))
        graph = build(module)
        enrich(graph, module, extract_symbols)
        sub_addr = subheading_address("comprehensive", "Sub Section")
        addr = claim_address(sub_addr, "example", 1)
        node = graph.node(addr)
        assert node is not None
        assert node.kind == NodeKind.EXAMPLE

    def test_example_count(self):
        module = from_tree(parse(_COMPREHENSIVE))
        graph = build(module)
        enrich(graph, module, extract_symbols)
        examples = list(graph.nodes(kind=NodeKind.EXAMPLE))
        assert len(examples) == 2


class TestTestsInGraph:
    def test_bare_tests(self):
        module = from_tree(parse(_COMPREHENSIVE))
        graph = build(module)
        node = graph.node("comprehensive#Tests")
        assert node is not None
        assert node.kind == NodeKind.TEST

    def test_named_group(self):
        module = from_tree(parse(_COMPREHENSIVE))
        graph = build(module)
        node = graph.node("comprehensive#Tests#edge cases")
        assert node is not None
        assert node.kind == NodeKind.TEST

    def test_test_count(self):
        module = from_tree(parse(_COMPREHENSIVE))
        graph = build(module)
        tests = list(graph.nodes(kind=NodeKind.TEST))
        assert len(tests) == 2


class TestPropertiesInGraph:
    def test_named_property(self):
        module = from_tree(parse(_COMPREHENSIVE))
        graph = build(module)
        enrich(graph, module, extract_symbols)
        node = graph.node("comprehensive#roundtrip")
        assert node is not None
        assert node.kind == NodeKind.PROPERTY

    def test_unnamed_property(self):
        module = from_tree(parse(_COMPREHENSIVE))
        graph = build(module)
        enrich(graph, module, extract_symbols)
        node = graph.node("comprehensive#property#2")
        assert node is not None
        assert node.kind == NodeKind.PROPERTY

    def test_property_count(self):
        module = from_tree(parse(_COMPREHENSIVE))
        graph = build(module)
        enrich(graph, module, extract_symbols)
        props = list(graph.nodes(kind=NodeKind.PROPERTY))
        assert len(props) == 2


class TestSymbolsInGraph:
    def test_module_level_symbols(self):
        module = from_tree(parse(_COMPREHENSIVE))
        graph = build(module)
        enrich(graph, module, extract_symbols)
        assert graph.node("comprehensive#CONSTANT") is not None
        assert graph.node("comprehensive#helper") is not None

    def test_subheading_symbols(self):
        module = from_tree(parse(_COMPREHENSIVE))
        graph = build(module)
        enrich(graph, module, extract_symbols)
        assert graph.node("comprehensive#sub_func") is not None


class TestSubheadingsInGraph:
    def test_subheading_present(self):
        module = from_tree(parse(_COMPREHENSIVE))
        graph = build(module)
        sub_addr = subheading_address("comprehensive", "Sub Section")
        node = graph.node(sub_addr)
        assert node is not None
        assert node.kind == NodeKind.SUBHEADING
