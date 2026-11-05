"""A node has a name, not a label (slice 10).

``Node.label`` is gone: a node's name is ``Node.name``, ``None`` for a node
addressed by position and for a keyword section. A node is its address and
its kind. ``search`` matches names, and so finds no node without one.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from notlob import Node, NodeKind, build_package
from notlob.bindings.python import kit as python_kit

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture(scope="module")
def roman():
    return build_package(
        EXAMPLES / "roman", python_kit.extract_symbols,
        call_extractor=python_kit.extract_calls)


class TestNode:
    def test_it_has_no_label_field(self):
        assert "label" not in {f.name for f in dataclasses.fields(Node)}

    def test_it_cannot_be_given_one(self):
        with pytest.raises(TypeError):
            Node(address="a", label="a", kind=NodeKind.MODULE)

    def test_one_address_and_kind_are_one_node(self):
        one = Node(address="m#x", kind=NodeKind.SYMBOL, name="x")
        other = Node(address="m#x", kind=NodeKind.SYMBOL, name="y",
                     start_line=3)
        assert one == other and hash(one) == hash(other)

    def test_a_kind_tells_two_apart(self):
        assert Node(address="m#x", kind=NodeKind.SYMBOL) != Node(
            address="m#x", kind=NodeKind.SUBHEADING)

    def test_the_address_and_kind_are_the_first_two_fields(self):
        names = [f.name for f in dataclasses.fields(Node)]
        assert names[:2] == ["address", "kind"]


class TestSearchMatchesNames:
    def test_a_positional_name_finds_nothing(self, roman):
        assert list(roman.search("prose*")) == []
        assert list(roman.search("prose#1")) == []
        assert list(roman.search("*#*")) == []

    def test_a_title_is_found(self, roman):
        found = list(roman.search("*Roman*"))
        modules = [n.address for n in found if n.kind == NodeKind.MODULE]
        assert "roman/numerals" in modules
        assert all(roman.node(a).name for a in modules)

    def test_a_node_without_a_name_is_found_by_no_pattern(self, roman):
        nameless = [n for n in roman.nodes() if n.name is None]
        assert nameless
        found = {n.address for n in roman.search("*")}
        assert not found & {n.address for n in nameless}

    def test_nor_by_its_kind(self, roman):
        assert list(roman.search("*", NodeKind.PROSE)) == []
        assert list(roman.search("*", NodeKind.CODE)) == []
        assert list(roman.search("*", NodeKind.TEST_LINES)) == []

    def test_every_node_found_has_a_name(self, roman):
        found = list(roman.search("*"))
        assert found and all(n.name is not None for n in found)

    def test_a_kind_restricts_the_names_it_finds(self, roman):
        symbols = list(roman.search("*", NodeKind.SYMBOL))
        assert symbols and all(n.kind == NodeKind.SYMBOL for n in symbols)

    def test_the_keyword_sections_have_no_name_and_are_not_found(self, roman):
        for kind in (NodeKind.TESTS, NodeKind.REFERENCES):
            assert list(roman.search("*", kind)) == []
