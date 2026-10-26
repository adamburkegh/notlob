"""What a kind is, the scope a name belongs to, and how a node is addressed.

A node's kind is an adjective: a claim, a block, a section. The table of
kinds states each such fact once, and the code asks the table. A name
belongs to a scope (the module, or a ``~property``, ``#Tests`` or a
``##group`` that opens its own), and a named node is addressed by its
scope and its name; an anonymous one by where it is written, its kind's
segment and an ordinal.
"""

from __future__ import annotations

import inspect

import pytest

import notlob
from notlob import NodeKind, build, build_package, enrich, from_tree, parse
from notlob import graph as graph_module
from notlob.bindings.python import extract_symbols
from notlob.graph import KINDS, anonymous_address, named_address

K = NodeKind


def _with(fact: str) -> set[NodeKind]:
    return {kind for kind in NodeKind if getattr(KINDS[kind], fact)}


# ── The table ────────────────────────────────────────────────

class TestTheTable:

    def test_every_kind_has_a_row(self):
        assert set(KINDS) == set(NodeKind)

    @pytest.mark.parametrize("fact, kinds", [
        ("opens_scope", {K.MODULE, K.PROPERTY, K.TESTS, K.TEST_GROUP}),
        ("claim", {K.EXAMPLE, K.PROPERTY, K.RUN}),
        ("runnable", {K.EXAMPLE, K.PROPERTY, K.RUN, K.TEST}),
        ("block", {K.PROSE, K.CODE, K.BULLETS}),
        ("section", {K.SUBHEADING, K.APPENDIX}),
        ("region", {K.POST_TEXT}),
        ("text_in_holder", {K.SYMBOL}),
    ])
    def test_the_kinds_that_have_the_fact(self, fact, kinds):
        assert _with(fact) == kinds

    def test_the_segment_of_each_anonymous_kind(self):
        assert {kind: KINDS[kind].segment for kind in NodeKind
                if KINDS[kind].segment is not None} == {
            K.PROSE: "prose", K.CODE: "code", K.BULLETS: "bullets",
            K.EXAMPLE: "example", K.RUN: "run", K.PROPERTY: "property",
            K.TEST: "test", K.APPENDIX: "appendix",
            K.POST_TEXT: "post-text",
        }

    def test_all_but_the_post_text_are_numbered(self):
        have_segment = {k for k in NodeKind if KINDS[k].segment}
        assert _with("numbered") == have_segment - {K.POST_TEXT}

    def test_no_kind_is_both_a_block_and_a_section(self):
        assert not _with("block") & _with("section")


# ── Scope ────────────────────────────────────────────────────

SOURCE = """\
#Roman Numerals

Intro.

* first point

    def to_roman(n):
        return 'I'

~example
    to_roman(1) == 'I'

~run
    main()

##Decoding

Decoding is the inverse.

    def from_roman(s):
        return 1

##Round-Trip

The pair are inverses.

~property commutativity
    def check_it(n):
        pass

~property
    def other_check(n):
        pass

---

#Tests

Commentary on the tests.

##encoding
    to_roman(1) == 'I'

~test named_one
    to_roman(2) == 'II'

#Appendix Notes

Appendix prose.

##Extras

    def helper():
        pass
"""


def _graph():
    module = from_tree(parse(SOURCE))
    graph = build(module)
    enrich(graph, module, extract_symbols)
    return graph


MOD = "roman/numerals"


class TestScopeOf:

    @pytest.fixture(scope="class")
    def graph(self):
        return _graph()

    @pytest.mark.parametrize("address, scope", [
        # a code block in a subheading, and its symbol: the module's
        (f"{MOD}#Decoding#code#1", MOD),
        (f"{MOD}#from_roman", MOD),
        (f"{MOD}#Decoding", MOD),
        # a symbol a ~property defines: the property's
        (f"{MOD}#commutativity#check_it", f"{MOD}#commutativity"),
        # a subheading in an Appendix: the module's
        (f"{MOD}#Extras", MOD),
        (f"{MOD}#helper", MOD),
        (f"{MOD}#appendix#1", MOD),
        # a named test in a group: the group's. The scope of the group's
        # own name is that of what holds it, #Tests, and of #Tests' own,
        # the module's, through the post-text
        (f"{MOD}#Tests#encoding#named_one", f"{MOD}#Tests#encoding"),
        (f"{MOD}#Tests#encoding#test#1", f"{MOD}#Tests#encoding"),
        (f"{MOD}#Tests#prose#1", f"{MOD}#Tests"),
        (f"{MOD}#post-text", MOD),
        (MOD, MOD),
    ])
    def test_the_scope_of_a_node(self, graph, address, scope):
        assert graph.scope_of(address) == scope

    @pytest.mark.parametrize("address, scope", [
        # a node that opens a scope is in its own
        (f"{MOD}#commutativity", f"{MOD}#commutativity"),
        (f"{MOD}#Tests", f"{MOD}#Tests"),
        (f"{MOD}#Tests#encoding", f"{MOD}#Tests#encoding"),
    ])
    def test_a_node_that_opens_a_scope_is_in_it(self, graph, address,
                                               scope):
        assert KINDS[graph.node(address).kind].opens_scope
        assert graph.scope_of(address) == scope

    @pytest.mark.parametrize("address, scope", [
        (f"{MOD}#Tests#encoding#named_one", f"{MOD}#Tests#encoding"),
        (f"{MOD}#Tests#encoding", f"{MOD}#Tests"),
        (f"{MOD}#Tests", MOD),
        (f"{MOD}#Extras", MOD),
        (f"{MOD}#Decoding", MOD),
        (f"{MOD}#from_roman", MOD),
        (f"{MOD}#commutativity", MOD),
        (f"{MOD}#commutativity#check_it", f"{MOD}#commutativity"),
    ])
    def test_a_name_belongs_to_the_scope_of_what_holds_it(
            self, graph, address, scope):
        holder = graph.parent_of(address)
        assert graph.scope_of(holder.address) == scope
        assert address == named_address(scope, graph.node(address).label)

    def test_an_unknown_address_has_no_scope(self, graph):
        assert graph.scope_of("no/such#thing") is None


# ── Addresses ────────────────────────────────────────────────

class TestTheTwoAddressFunctions:

    def test_a_named_address_is_its_scope_and_its_name(self):
        assert named_address("roman/numerals", "to_roman") == (
            "roman/numerals#to_roman")
        assert named_address("pricing/discounts", "Stacking Discounts") == (
            "pricing/discounts#Stacking Discounts")

    def test_a_scope_may_be_a_property_or_a_group(self):
        assert named_address("m#Tests#group", "t") == "m#Tests#group#t"

    def test_an_anonymous_address_is_its_kinds_segment_and_ordinal(self):
        assert anonymous_address("m#Sub", K.EXAMPLE, 2) == "m#Sub#example#2"
        assert anonymous_address("m", K.PROSE, 1) == "m#prose#1"
        assert anonymous_address("m", K.BULLETS, 3) == "m#bullets#3"
        assert anonymous_address("m", K.APPENDIX, 2) == "m#appendix#2"

    def test_the_post_text_has_no_ordinal(self):
        assert anonymous_address("m", K.POST_TEXT, 1) == "m#post-text"

    def test_a_kind_with_no_segment_is_never_anonymous(self):
        for kind in NodeKind:
            if KINDS[kind].segment is None:
                with pytest.raises(ValueError):
                    anonymous_address("m", kind, 1)


class TestAddressesAsWritten:
    """Every node of the module above, with its address in full. A named
    ``~property`` is in the scope of its module, wherever it is written."""

    def test_the_address_and_kind_of_each_node(self):
        graph = _graph()
        assert {node.address: node.kind.name for node in graph.nodes()} == {
            MOD: "MODULE",
            f"{MOD}#prose#1": "PROSE",
            f"{MOD}#bullets#1": "BULLETS",
            f"{MOD}#code#1": "CODE",
            f"{MOD}#to_roman": "SYMBOL",
            f"{MOD}#example#1": "EXAMPLE",
            f"{MOD}#run#1": "RUN",
            f"{MOD}#Decoding": "SUBHEADING",
            f"{MOD}#Decoding#prose#1": "PROSE",
            f"{MOD}#Decoding#code#1": "CODE",
            f"{MOD}#from_roman": "SYMBOL",
            f"{MOD}#Round-Trip": "SUBHEADING",
            f"{MOD}#Round-Trip#prose#1": "PROSE",
            f"{MOD}#commutativity": "PROPERTY",
            f"{MOD}#commutativity#check_it": "SYMBOL",
            f"{MOD}#Round-Trip#property#2": "PROPERTY",
            f"{MOD}#Round-Trip#property#2#other_check": "SYMBOL",
            f"{MOD}#post-text": "POST_TEXT",
            f"{MOD}#Tests": "TESTS",
            f"{MOD}#Tests#prose#1": "PROSE",
            f"{MOD}#Tests#encoding": "TEST_GROUP",
            f"{MOD}#Tests#encoding#test#1": "TEST",
            f"{MOD}#Tests#encoding#named_one": "TEST",
            f"{MOD}#appendix#1": "APPENDIX",
            f"{MOD}#appendix#1#prose#1": "PROSE",
            f"{MOD}#Extras": "SUBHEADING",
            f"{MOD}#Extras#code#1": "CODE",
            f"{MOD}#helper": "SYMBOL",
        }

    def test_every_kind_a_module_holds_is_among_them(self):
        kinds = {node.kind for node in _graph().nodes()}
        assert kinds == set(NodeKind) - {K.EXTERNAL}


class TestANamedPropertyIsInItsModulesScope:
    """Sections are not scopes: a name written in a section belongs to the
    module, and so does a named ``~property``'s, wherever it is written."""

    PROPERTY = ("~property {name}\n"
                "    def check_it(n):\n"
                "        pass\n\n")

    def _build(self, source: str, collisions=None):
        module = from_tree(parse(source))
        graph = build(module, collisions=collisions)
        enrich(graph, module, extract_symbols)
        return graph

    def test_it_is_at_its_module_and_name(self):
        graph = self._build(
            "#T\n\n##Section\n\n" + self.PROPERTY.format(name="same"))
        node = graph.node("t#same")
        assert node.kind == K.PROPERTY
        assert node.label == "same"
        assert graph.node("t#Section#same") is None
        assert graph.parent_of("t#same").address == "t#Section"

    def test_what_it_defines_is_under_it(self):
        graph = self._build(
            "#T\n\n##Section\n\n" + self.PROPERTY.format(name="same"))
        assert graph.node("t#same#check_it").kind == K.SYMBOL
        assert graph.parent_of("t#same#check_it").address == "t#same"
        assert graph.scope_of("t#same#check_it") == "t#same"

    def test_it_is_a_scope_of_its_own(self):
        graph = self._build(
            "#T\n\n##Section\n\n" + self.PROPERTY.format(name="same"))
        assert graph.scope_of("t#same") == "t#same"

    def test_an_unnamed_one_is_still_at_its_section(self):
        graph = self._build(
            "#T\n\n##Section\n\n" + self.PROPERTY.format(name="same")
            + "~property\n    def other(n):\n        pass\n")
        assert graph.node("t#Section#property#2").kind == K.PROPERTY
        assert graph.node("t#Section#property#2#other") is not None

    def test_two_of_one_name_in_different_sections_collide(self):
        source = ("#T\n\n##One\n\n" + self.PROPERTY.format(name="same")
                  + "##Two\n\n" + self.PROPERTY.format(name="same"))
        with pytest.raises(graph_module.AddressCollisionError) as raised:
            build(from_tree(parse(source)))
        assert raised.value.address == "t#same"

    def test_the_collision_is_collected_when_a_list_is_given(self):
        source = ("#T\n\n##One\n\n" + self.PROPERTY.format(name="same")
                  + "##Two\n\n" + self.PROPERTY.format(name="same"))
        collected = []
        self._build(source, collisions=collected)
        assert [c.address for c in collected] == ["t#same"]

    def test_a_package_reports_it_as_it_does_other_collisions(
            self, tmp_path):
        (tmp_path / "t.lob").write_text(
            "#T\n\n##One\n\n" + self.PROPERTY.format(name="same")
            + "##Two\n\n" + self.PROPERTY.format(name="same"),
            encoding="utf-8")
        collected = []
        build_package(tmp_path, extract_symbols, collisions=collected)
        assert [(path.name, error.address) for path, error in collected] == [
            ("t.lob", "t#same")]

    def test_one_of_a_subheadings_name_collides_with_it(self):
        source = ("#T\n\n##Same\n\nProse.\n\n##Other\n\n"
                  + self.PROPERTY.format(name="Same"))
        with pytest.raises(graph_module.AddressCollisionError) as raised:
            build(from_tree(parse(source)))
        assert raised.value.address == "t#Same"

    def test_one_of_a_symbols_name_collides_with_it(self):
        source = ("#T\n\n##One\n\n" + self.PROPERTY.format(name="total")
                  + "##Two\n\n    def total():\n        pass\n")
        module = from_tree(parse(source))
        graph = build(module)
        with pytest.raises(graph_module.AddressCollisionError) as raised:
            enrich(graph, module, extract_symbols)
        assert raised.value.address == "t#total"


# ── What went ────────────────────────────────────────────────

class TestTheOldNamesAreGone:

    @pytest.mark.parametrize("name", [
        "subheading_address", "symbol_address", "property_address",
        "appendix_address", "post_text_address", "claim_address",
        "ANONYMOUS_LEAVES",
    ])
    def test_the_name_is_gone(self, name):
        assert not hasattr(graph_module, name)
        assert not hasattr(notlob, name)

    def test_the_module_address_stays(self):
        assert graph_module.module_address("Roman Numerals") == MOD
        assert notlob.module_address is graph_module.module_address

    @pytest.mark.parametrize("function", [
        graph_module._add_items, graph_module._add_tests,
    ])
    def test_the_module_is_no_longer_threaded_beside_the_parent(
            self, function):
        assert "mod_addr" not in inspect.signature(function).parameters
