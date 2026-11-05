"""The model says what the target needs: a name wherever the document gives
one, a kind for a run of test lines, an appendix named by its title.

A ``~test <name>`` is a ``TEST`` and always has a name; a run of bare
assertions is ``TEST_LINES`` and never has one. An appendix is addressed by
its title (``mod#Glossary``; a bare ``#Appendix`` is ``mod#Appendix``), so
a repeat is a collision. A node has a ``name`` where its address is built
from one; a node with a positional address has none.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest

import notlob
import notlob.graph as graph_module
from notlob import (
    AddressCollisionError, NodeKind, build, build_package, from_tree, parse,
)
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit
from notlob.commands import cmd_test
from notlob.graph import KINDS, claims_to_run, enrich, positional_address
from notlob.view import level_view
from notlob.writers import write_json, write_text, write_turtle

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"
SCHEMAS = ROOT / "notlob" / "schema"

_PROJECTS = [
    ("roman", python_kit), ("retail", python_kit),
    ("gutenberg", python_kit), ("haskell-roman", haskell_kit),
    ("ts-media", typescript_kit),
]

K = NodeKind


def _graph(source: str, enriched: bool = False):
    module = from_tree(parse(source))
    graph = build(module)
    if enriched:
        enrich(graph, module, python_kit.extract_symbols)
    return graph


@pytest.fixture(scope="module", params=_PROJECTS, ids=lambda p: p[0])
def example_graph(request):
    name, kit = request.param
    return build_package(
        EXAMPLES / name, kit.extract_symbols, call_extractor=kit.extract_calls)


# ── A test and a run of test lines are two kinds ─────────────

class TestTwoKindsOfTest:
    def test_a_test_always_has_a_name_and_lines_never(self, example_graph):
        tests = list(example_graph.nodes(K.TEST))
        lines = list(example_graph.nodes(K.TEST_LINES))
        assert all(n.name for n in tests)
        assert all(n.name is None for n in lines)

    def test_the_examples_have_both(self):
        graph = build_package(
            EXAMPLES / "roman", python_kit.extract_symbols,
            call_extractor=python_kit.extract_calls)
        assert list(graph.nodes(K.TEST)) and list(graph.nodes(K.TEST_LINES))

    def test_romans_lines_stay_at_the_address_they_had(self):
        graph = build_package(
            EXAMPLES / "roman", python_kit.extract_symbols,
            call_extractor=python_kit.extract_calls)
        lines = graph.node("roman/numerals#Tests#encoding#test#1")
        assert lines.kind == K.TEST_LINES
        assert lines.name is None

    def test_romans_named_test_is_a_test_with_its_name(self):
        graph = build_package(
            EXAMPLES / "roman", python_kit.extract_symbols,
            call_extractor=python_kit.extract_calls)
        named = graph.node("roman/numerals#Tests#encoding#mcmxciv")
        assert (named.kind, named.name) == (K.TEST, "mcmxciv")

    def test_a_test_has_no_segment_and_lines_keep_theirs(self):
        assert KINDS[K.TEST].segment is None
        assert not KINDS[K.TEST].numbered
        assert KINDS[K.TEST_LINES].segment == "test"
        assert KINDS[K.TEST_LINES].numbered
        assert KINDS[K.TEST_LINES].runnable and KINDS[K.TEST].runnable

    def test_only_a_test_has_the_sigil(self):
        assert KINDS[K.TEST].sigil == "~test"
        assert KINDS[K.TEST_LINES].sigil is None
        assert not hasattr(KINDS[K.TEST], "sigil_needs_name")

    def test_the_claims_to_run_say_which(self):
        graph = _graph(
            "#M\n\n---\n\n#Tests\n\n##g\n    1 == 1\n\n~test t\n"
            "    2 == 2\n")
        kinds = {c.address: c.kind for c in claims_to_run(graph, "m")}
        assert kinds == {"m#Tests#g#test#1": "TEST_LINES",
                         "m#Tests#g#t": "TEST"}

    def test_the_outline_and_index_print_no_line_for_lines(
        self, example_graph,
    ):
        for level in ("outline", "index"):
            text = write_text(level_view(example_graph, level))
            assert not re.search(r"^ *test#\d+ ", text, re.M)

    def test_block_prints_one(self, example_graph):
        text = write_text(level_view(example_graph, "block"))
        assert re.search(r"^ *test#\d+ ", text, re.M)

    def test_test_json_reports_both_kinds(self, capsys):
        cmd_test(EXAMPLES / "roman" / "roman" / "numerals.lob", fmt="json")
        doc = json.loads(capsys.readouterr().out)
        kinds = {c["kind"] for c in doc["claims"]}
        assert {"TEST", "TEST_LINES"} <= kinds

    def test_each_result_names_the_kind_of_what_ran(self, capsys):
        cmd_test(EXAMPLES / "roman" / "roman" / "numerals.lob", fmt="json")
        doc = json.loads(capsys.readouterr().out)
        by_address = {c["address"]: c["kind"] for c in doc["claims"]}
        assert by_address["roman/numerals#Tests#encoding#test#1"] == (
            "TEST_LINES")
        assert by_address["roman/numerals#Tests#encoding#mcmxciv"] == "TEST"

    @pytest.mark.parametrize(
        "name", ["name_graph.json", "query_result.json", "test_result.json"])
    def test_the_schemas_list_the_kind(self, name):
        text = (SCHEMAS / name).read_text(encoding="utf-8")
        assert '"TEST_LINES"' in text


# ── An appendix is named by its title ────────────────────────

_POST = "#M\n\n---\n\n"


class TestAnAppendixIsNamedByItsTitle:
    def test_a_titled_appendix_is_at_its_title(self):
        graph = _graph(_POST + "#Appendix Glossary\n\nA word.\n")
        node = graph.node("m#Glossary")
        assert node.kind == K.APPENDIX
        assert node.name == "Glossary"

    def test_a_bare_appendix_is_named_appendix(self):
        graph = _graph(_POST + "#Appendix\n\nA word.\n")
        node = graph.node("m#Appendix")
        assert node.kind == K.APPENDIX
        assert node.name == "Appendix"

    def test_what_is_in_it_is_under_that_address(self):
        graph = _graph(_POST + "#Appendix Glossary\n\nA word.\n")
        assert graph.node("m#Glossary#prose#1") is not None
        assert graph.parent_of("m#Glossary#prose#1").address == "m#Glossary"

    def test_what_is_in_a_bare_one_is_under_its_address(self):
        graph = _graph(_POST + "#Appendix\n\nA word.\n\n    x = 1\n")
        assert graph.node("m#Appendix#prose#1") is not None
        assert graph.node("m#Appendix#code#1") is not None

    def test_a_title_of_several_words(self):
        graph = _graph(_POST + "#Appendix The long tail\n\nA word.\n")
        assert graph.node("m#The long tail").name == "The long tail"

    def test_it_hangs_from_the_post_text(self):
        graph = _graph(_POST + "#Appendix Glossary\n\nA word.\n")
        assert graph.parent_of("m#Glossary").address == "m#post-text"

    def test_the_old_address_is_gone(self):
        graph = _graph(_POST + "#Appendix Glossary\n\nA word.\n")
        assert graph.node("m#appendix#1") is None

    @pytest.mark.parametrize(
        "heading", ["#Appendix Glossary", "#Appendix"])
    def test_there_is_no_hash_past_the_modules(self, heading):
        graph = _graph(_POST + f"{heading}\n\nA word.\n")
        (node,) = graph.nodes(K.APPENDIX)
        assert node.address.count("#") == 1
        assert "#" not in node.name

    def test_a_titled_and_a_bare_one_are_two_nodes(self):
        graph = _graph(
            _POST + "#Appendix Glossary\n\nA.\n\n#Appendix\n\nB.\n")
        assert [n.address for n in graph.nodes(K.APPENDIX)] == [
            "m#Glossary", "m#Appendix"]

    def test_two_titles_are_two_nodes_in_order(self):
        graph = _graph(_POST + "#Appendix One\n\nA.\n\n#Appendix Two\n\nB.\n")
        assert [(n.address, n.name) for n in graph.nodes(K.APPENDIX)] == [
            ("m#One", "One"), ("m#Two", "Two")]

    def test_a_subheading_of_one_is_still_the_modules(self):
        graph = _graph(_POST + "#Appendix Notes\n\n##Sub\n\nText.\n")
        assert graph.node("m#Sub").kind == K.SUBHEADING
        assert graph.parent_of("m#Sub").address == "m#Notes"


#: Each is a collision: a name written twice in one scope.
COLLIDING = {
    "two titles": (
        _POST + "#Appendix Glossary\n\nA.\n\n#Appendix Glossary\n\nB.\n"),
    "two bare": _POST + "#Appendix\n\nA.\n\n#Appendix\n\nB.\n",
    "a title and a heading": (
        "#M\n\n##Glossary\n\nA.\n\n---\n\n#Appendix Glossary\n\nB.\n"),
}


class TestAnAppendixRepeatedIsACollision:
    @pytest.mark.parametrize("source", COLLIDING.values(),
                             ids=COLLIDING.keys())
    def test_it_raises(self, source):
        with pytest.raises(AddressCollisionError):
            _graph(source)

    @pytest.mark.parametrize(
        "source", [COLLIDING["two titles"], COLLIDING["two bare"]],
        ids=["two titles", "two bare"])
    def test_it_is_collected_when_a_list_is_given(self, source):
        found: list[AddressCollisionError] = []
        build(from_tree(parse(source)), collisions=found)
        assert len(found) == 1
        assert found[0].existing_kind == found[0].new_kind == K.APPENDIX

    def test_the_message_names_the_address(self):
        with pytest.raises(AddressCollisionError, match="m#Glossary"):
            _graph(COLLIDING["two titles"])


# ── A name where the document gives one ──────────────────────

#: The kinds that always have a name, the kinds that never do, and
#: PROPERTY, which has one if the document gives it.
ALWAYS = {K.MODULE, K.SUBHEADING, K.SYMBOL, K.EXTERNAL, K.APPENDIX,
          K.TEST_GROUP, K.TEST}
NEVER = {K.EXAMPLE, K.RUN, K.TEST_LINES, K.PROSE, K.CODE, K.BULLETS,
         K.POST_TEXT, K.LISTING, K.IMPORT, K.DECLARATION,
         K.TESTS, K.REFERENCES, K.BINDING}
SOMETIMES = {K.PROPERTY}

_EVERY_KIND = (
    "#Mod\n\nIntro, with #Other.\n\n    def f(): pass\n\n* a\n* b\n\n"
    "~example\n    f() == 1\n\n~run\n    f()\n\n"
    "~property p\n    def _(): pass\n\n~property\n    def _(): pass\n\n"
    "##Sec\n\nText.\n\n---\n\n#Tests\n\n    f() == 1\n\n##grp\n"
    "    f() == 1\n\n~test t\n    f() == 1\n\n"
    "#References\n    #Other\n    import os\n\n"
    "#Appendix Glossary\n\nA word.\n")


class TestNameWhereTheDocumentGivesOne:
    def test_the_kinds_are_all_accounted_for(self):
        assert ALWAYS | NEVER | SOMETIMES == set(NodeKind)
        assert not ALWAYS & NEVER

    def test_every_example_node_follows_its_kind(self, example_graph):
        for node in example_graph.nodes():
            if node.kind in ALWAYS:
                assert node.name, node.address
            elif node.kind in NEVER:
                assert node.name is None, node.address

    def test_a_property_has_one_if_the_document_gives_it(self):
        graph = _graph(_EVERY_KIND, enriched=True)
        assert graph.node("mod#p").name == "p"
        assert graph.node("mod#property#2").name is None

    def test_what_follows_the_last_hash_is_the_name(self, example_graph):
        for node in example_graph.nodes():
            if node.name is None or node.kind == K.MODULE:
                continue
            assert node.address.rsplit("#", 1)[-1] == node.name, node.address

    def test_a_module_has_its_title(self, example_graph):
        for node in example_graph.nodes(K.MODULE):
            assert node.name
            assert graph_module.module_address(node.name) == node.address

    def test_an_external_has_its_file(self, example_graph):
        for node in example_graph.nodes(K.EXTERNAL):
            assert node.name == node.address

    def test_a_node_with_a_positional_address_has_none(self, example_graph):
        for node in example_graph.nodes():
            last = node.address.rsplit("#", 1)[-1]
            if re.fullmatch(r"\d+", last) or last == "post-text":
                assert node.name is None, node.address

    def test_every_kind_in_a_small_module(self):
        graph = _graph(_EVERY_KIND, enriched=True)
        seen = {n.kind for n in graph.nodes()}
        for node in graph.nodes():
            if node.kind in NEVER:
                assert node.name is None, node.address
            if node.kind in (K.MODULE, K.SYMBOL, K.APPENDIX, K.TEST_GROUP,
                             K.SUBHEADING, K.TEST):
                assert node.name, node.address
        assert {K.MODULE, K.SYMBOL, K.APPENDIX, K.TEST, K.TEST_LINES,
                K.TEST_GROUP, K.SUBHEADING, K.PROPERTY} <= seen

    def test_the_keywords_of_the_post_text_have_none(self):
        graph = _graph(_EVERY_KIND)
        for address in ("mod#Tests", "mod#References"):
            assert graph.node(address).name is None


# ── Positional, not anonymous ────────────────────────────────

class TestPositional:
    def test_positional_address_is_public(self):
        assert "positional_address" in notlob.__all__
        assert notlob.positional_address is positional_address

    def test_it_is_what_anonymous_address_was(self):
        assert positional_address("m#Sub", K.EXAMPLE, 2) == "m#Sub#example#2"
        assert positional_address("m", K.POST_TEXT, 1) == "m#post-text"
        assert positional_address("m", K.TEST_LINES, 1) == "m#test#1"

    def test_anonymous_address_is_gone(self):
        assert "anonymous_address" not in notlob.__all__
        assert not hasattr(notlob, "anonymous_address")
        assert not hasattr(graph_module, "anonymous_address")
        assert not hasattr(graph_module, "_anonymous_identity")

    def test_a_kind_with_no_segment_is_named_not_positional(self):
        with pytest.raises(ValueError):
            positional_address("m", K.TEST, 1)
        with pytest.raises(ValueError):
            positional_address("m", K.APPENDIX, 1)


# ── The old documents carry the model ────────────────────────

def _schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


class TestTheDocumentsCarryTheModel:
    @pytest.mark.parametrize("level", ["outline", "index", "block", "full"])
    def test_a_document_validates_and_has_no_named(
        self, example_graph, level,
    ):
        doc = json.loads(write_json(level_view(example_graph, level)))
        jsonschema.validate(doc, _schema("name_graph.json"))
        assert all("named" not in node for node in doc["nodes"])

    def test_a_run_of_lines_is_written_by_its_kind(self):
        graph = build_package(
            EXAMPLES / "roman", python_kit.extract_symbols,
            call_extractor=python_kit.extract_calls)
        doc = json.loads(write_json(level_view(graph, "block")))
        nodes = {n["address"]: n for n in doc["nodes"]}
        assert nodes["roman/numerals#Tests#encoding#test#1"]["kind"] == (
            "TEST_LINES")
        assert nodes["roman/numerals#Tests#encoding#mcmxciv"]["kind"] == (
            "TEST")

    def test_an_appendix_is_written_at_its_title(self):
        graph = _graph(_POST + "#Appendix Glossary\n\nA word.\n")
        doc = json.loads(write_json(level_view(graph, "outline")))
        jsonschema.validate(doc, _schema("name_graph.json"))
        entry = [n for n in doc["nodes"] if n["kind"] == "APPENDIX"]
        assert [n["address"] for n in entry] == ["m#Glossary"]

    @pytest.mark.parametrize("level", ["outline", "index", "block", "full"])
    def test_the_turtle_has_no_named(self, example_graph, level):
        assert "notlob:named" not in write_turtle(
            level_view(example_graph, level))

    def test_no_schema_or_ontology_has_named(self):
        for name in ("name_graph.json", "query_result.json"):
            assert '"named"' not in (SCHEMAS / name).read_text(
                encoding="utf-8"), name
        assert "notlob:named" not in (SCHEMAS / "notlob.ttl").read_text(
            encoding="utf-8")

    def test_the_ontology_has_the_class(self):
        text = (SCHEMAS / "notlob.ttl").read_text(encoding="utf-8")
        assert re.search(r"^notlob:TestLines a owl:Class", text, re.M)
