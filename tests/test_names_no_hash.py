"""A name is a terminal of the grammar, and may not hold ``#``.

A module's title, a ``##heading`` or ``##group``, the name of a
``~property`` or a ``~test`` and the title of an ``#Appendix`` are each a
``NAME`` beside a marker, and the grammar alone refuses a ``#`` in one:
``#`` is the address separator and the reference sigil. ``##`` and ``#`` are
the markers, not the name, so ``###Notes`` is a name that holds ``#``. A name
has at least one character that is not a space. ``parse`` words Lark's
refusal and holds no rule of its own.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest
from lark.exceptions import UnexpectedInput

from notlob import NodeKind, build, build_package, from_tree, parse, parse_file
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit
from notlob.model import Claim, NamedTest, Subheading
from notlob.parser import _parser

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"

_TESTS = "#M\n\n---\n\n#Tests\n\n"
_APPENDIX = "#M\n\n---\n\n"

#: (source, line, name as reported): each kind of name with a ``#`` at the
#: start, in the middle and at the end, where it can be written there.
BAD = {
    "module, middle":       ("#Calling C# from Python\n", 1,
                             "Calling C# from Python"),
    "module, end":          ("#Module C#\n", 1, "Module C#"),
    "module, second":       ("#Module#1\n", 1, "Module#1"),
    "heading, middle":      ("#M\n\n##Calling C# from Python\n\nText.\n", 3,
                             "Calling C# from Python"),
    "heading, start":       ("#M\n\n###Notes\n\nText.\n", 3, "#Notes"),
    "heading, ordinal":     ("#M\n\n##g#2\n\nText.\n", 3, "g#2"),
    "heading, end":         ("#M\n\n##Trailing#\n\nText.\n", 3, "Trailing#"),
    "heading, spaced":      ("#M\n\n##a #b\n\nText.\n", 3, "a #b"),
    "group, middle":        (_TESTS + "##g#2\n    a == 1\n", 7, "g#2"),
    "group, ordinal":       (_TESTS + "##h#1\n\n    1 == 1\n", 7, "h#1"),
    "group, start":         (_TESTS + "###g\n    a == 1\n", 7, "#g"),
    "group, end":           (_TESTS + "##g#\n    a == 1\n", 7, "g#"),
    "property, middle":     ("#M\n\n~property a#b\n    def _(): pass\n", 3,
                             "a#b"),
    "property, start":      ("#M\n\n~property #a\n    def _(): pass\n", 3,
                             "#a"),
    "property, end":        ("#M\n\n~property a#\n    def _(): pass\n", 3,
                             "a#"),
    "test, ordinal":        (_TESTS + "##g\n~test test#1\n    b == 2\n", 8,
                             "test#1"),
    "test, start":          (_TESTS + "##g\n~test #a\n    b == 2\n", 8, "#a"),
    "test, end":            (_TESTS + "##g\n~test a#\n    b == 2\n", 8, "a#"),
    "appendix, end":        (_APPENDIX + "#Appendix C#\n\nText.\n", 5, "C#"),
    "appendix, start":      (_APPENDIX + "#Appendix #C\n\nText.\n", 5, "#C"),
    "appendix, middle":     (_APPENDIX + "#Appendix C#D\n\nText.\n", 5,
                             "C#D"),
    "appendix, a later one": (
        _APPENDIX + "#Appendix B\n\nText.\n\n#Appendix C#\n\nText.\n", 9,
        "C#"),
}

#: Bare markers: a name has a character that is not a space.
NO_NAME = {
    "heading":       "#M\n\n##\n\nText.\n",
    "heading, spaces": "#M\n\n##   \n\nText.\n",
    "group":         _TESTS + "##\n    a == 1\n",
    "group, spaces": _TESTS + "##  \n    a == 1\n",
}


def _message(file: str, line: int, name: str) -> str:
    return f"{file}:{line}: a name may not hold '#': {name!r}"


# ── The grammar refuses such a name ──────────────────────────

@pytest.mark.parametrize("case", BAD)
class TestRefused:
    def test_by_the_grammar_alone(self, case):
        source, _, _ = BAD[case]
        with pytest.raises(UnexpectedInput):
            _parser.parse(source)

    def test_with_the_file_the_line_and_the_name(self, case, tmp_path):
        source, line, name = BAD[case]
        path = tmp_path / "sharp.lob"
        path.write_text(source, encoding="utf-8")
        with pytest.raises(ValueError) as raised:
            parse_file(path)
        assert str(raised.value) == _message(path.as_posix(), line, name)

    def test_from_a_string_with_the_line_alone(self, case):
        source, line, name = BAD[case]
        with pytest.raises(ValueError) as raised:
            parse(source)
        assert str(raised.value) == (
            f"line {line}: a name may not hold '#': {name!r}")


@pytest.mark.parametrize("case", NO_NAME)
class TestAMarkerAloneIsNotAName:
    def test_the_grammar_refuses_it(self, case):
        with pytest.raises(UnexpectedInput):
            _parser.parse(NO_NAME[case])

    def test_parse_refuses_it_in_lark_s_words(self, case):
        with pytest.raises(UnexpectedInput):
            parse(NO_NAME[case])


# ── What is accepted, with these names ───────────────────────

def _heading(source: str) -> str:
    module = from_tree(parse(source))
    (sub,) = [i for i in module.body if isinstance(i, Subheading)]
    return sub.title


def _group(source: str) -> str:
    module = from_tree(parse(source))
    (group,) = module.post_text.sections[0].items
    return group.title


def _test_name(source: str) -> str:
    module = from_tree(parse(source))
    (group,) = module.post_text.sections[0].items
    (named,) = [i for i in group.items if isinstance(i, NamedTest)]
    return named.name


def _sigil(source: str) -> str:
    module = from_tree(parse(source))
    (claim,) = [i for i in module.body if isinstance(i, Claim)]
    return claim.sigil


def _appendix(source: str) -> str:
    module = from_tree(parse(source))
    return module.post_text.sections[0].title


class TestAccepted:
    @pytest.mark.parametrize("line, name", [
        ("##Notes", "Notes"),
        ("## Spaced", "Spaced"),
        ("##Trailing  ", "Trailing"),
        ("##Two words  here", "Two words  here"),
        ("## C notes", "C notes"),
    ])
    def test_a_heading(self, line, name):
        assert _heading(f"#M\n\n{line}\n\nText.\n") == name

    @pytest.mark.parametrize("line, name", [
        ("##Notes", "Notes"), ("## Spaced", "Spaced"),
        ("##Trailing  ", "Trailing"),
    ])
    def test_a_group(self, line, name):
        assert _group(_TESTS + f"{line}\n    a == 1\n") == name

    @pytest.mark.parametrize("line", ["~test total", "~test  total",
                                      "~test total  "])
    def test_a_named_test(self, line):
        assert _test_name(_TESTS + f"##g\n{line}\n    1 == 1\n") == "total"

    def test_a_named_test_keeps_inner_spaces(self):
        assert _test_name(
            _TESTS + "##g\n~test two  words\n    1 == 1\n") == "two  words"

    @pytest.mark.parametrize("line, sigil", [
        ("~property total", "~property total"),
        ("~property  total", "~property total"),
        ("~property", "~property"),
    ])
    def test_a_property(self, line, sigil):
        assert _sigil(f"#M\n\n{line}\n    True\n") == sigil

    @pytest.mark.parametrize("line, title", [
        ("#Appendix", "#Appendix"),
        ("#Appendix A", "#Appendix A"),
        ("#Appendix Two words", "#Appendix Two words"),
    ])
    def test_an_appendix(self, line, title):
        assert _appendix(_APPENDIX + f"{line}\n\nText.\n") == title

    def test_a_module_title_with_spaces_inside(self):
        assert from_tree(parse("#Two  words\n")).title == "Two  words"
        assert from_tree(parse("# Spaced\n")).title == "Spaced"


class TestWhatIsNotAName:
    def test_a_reference_in_prose_is_a_reference(self):
        module = from_tree(parse("#M\n\nSee ##Notes and #Other.\n"))
        (prose,) = module.body
        refs = [s for s in prose.spans if not isinstance(s, str)]
        assert [(r.label, r.sub) for r in refs] == [
            ("Notes", True), ("Other", False)]

    def test_a_reference_at_column_zero_is_prose(self):
        module = from_tree(parse("#M\n\n#Other is cited here.\n"))
        (prose,) = module.body
        assert [s.label for s in prose.spans if not isinstance(s, str)] == [
            "Other"]

    def test_a_hash_and_a_lowercase_word_are_prose(self):
        module = from_tree(parse("#M\n\n#5 and #lower are prose.\n"))
        (prose,) = module.body
        assert all(isinstance(s, str) for s in prose.spans)

    def test_an_external_may_hold_a_fragment(self):
        module = from_tree(parse(
            "#M\n\n---\n\n#Binding\n    ~language python\n"
            "    ~external index.html#top\n"))
        assert module.post_text.sections[0].externals == ["index.html#top"]

    def test_a_listing_is_not_a_name(self):
        module = from_tree(parse(
            "#M\n\n---\n\n#References\n    #Other Module\n"))
        assert module.post_text.sections[0].listings[0].title == (
            "Other Module")

    def test_code_and_an_assertion_may_hold_it(self):
        source = (
            "#M\n\nWe like C# and issue #5 and #hashtag.\n\n"
            "    x = '#'  # a comment\n\n"
            "* item C#\n\n"
            "~example\n    x == '#'\n\n"
            "---\n\n#Tests\n\n##g\n    '#' == '#'\n\n"
            "~test t\n    'a#b' == 'a#b'\n")
        graph = build(from_tree(parse(source)))
        assert graph.node("m#Tests#g#t").name == "t"

    def test_the_address_of_an_anonymous_node_has_one(self):
        graph = build(from_tree(parse(
            "#M\n\nText.\n\n~example\n    1 == 1\n")))
        assert graph.node("m#prose#1") is not None
        assert graph.node("m#example#1") is not None

    def test_a_clash_with_no_hash_in_a_name_is_still_one(self):
        from notlob import AddressCollisionError
        with pytest.raises(AddressCollisionError):
            build(from_tree(parse("#M\n\n##A\n\n##A\n")))


# ── Over every example ───────────────────────────────────────

_PROJECTS = [
    ("roman", python_kit), ("retail", python_kit),
    ("gutenberg", python_kit), ("haskell-roman", haskell_kit),
    ("ts-media", typescript_kit),
]

#: The model of each example file, and the graph document of each project
#: at ``full``, as they were before a name was a terminal: a short digest of
#: the dataclasses as JSON, and of the document.
MODELS = {
    "gutenberg/binding.lob": "2ac74075a445920f",
    "gutenberg/gutenberg/corpus.lob": "29246d50af7939f5",
    "gutenberg/gutenberg/hamlet.lob": "732f66c423d6e575",
    "haskell-roman/binding.lob": "1342f46e610357c1",
    "haskell-roman/roman/numerals/app.lob": "d15b90528d02cf37",
    "haskell-roman/roman/numerals.lob": "cf292fe8f1828ffa",
    "retail/binding.lob": "12663be1935550f7",
    "retail/pricing/discounts.lob": "4a3e66efe067403d",
    "roman/binding.lob": "d39fe96fc4022a58",
    "roman/roman/numerals.lob": "e4a24c2669517178",
    "ts-media/binding.lob": "d3e93d63a2f68f1d",
    "ts-media/media-attributes/analysis.lob": "3fa38380ae3af0a7",
    "ts-media/media-attributes/render.lob": "ff1b3053118e3f30",
}
GRAPHS = {
    "roman": "198545e96505027f",
    "retail": "9a04bb447ac9720e",
    "gutenberg": "928ff0505a07ede0",
    "haskell-roman": "177786d25d453d35",
    "ts-media": "ca41422848c61d50",
}


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class TestNothingDownstreamChanges:
    def test_every_example_file_is_in_the_table(self):
        found = {p.relative_to(EXAMPLES).as_posix()
                 for p in EXAMPLES.rglob("*.lob")}
        assert found == set(MODELS)

    @pytest.mark.parametrize("name", MODELS)
    def test_the_model_of_a_file(self, name):
        module = from_tree(parse_file(EXAMPLES / name))
        text = json.dumps(dataclasses.asdict(module), sort_keys=True,
                          default=str, ensure_ascii=False)
        assert _digest(text) == MODELS[name]

    @pytest.mark.parametrize("project", _PROJECTS, ids=lambda p: p[0])
    def test_the_graph_document_at_full(self, project):
        name, kit = project
        graph = build_package(
            EXAMPLES / name, kit.extract_symbols,
            call_extractor=kit.extract_calls)
        assert _digest(graph.to_json(level="full")) == GRAPHS[name]


#: The kinds a document gives a name to.
_NAMED = (NodeKind.SUBHEADING, NodeKind.TEST_GROUP)


@pytest.fixture(scope="module", params=_PROJECTS, ids=lambda p: p[0])
def example_graph(request):
    name, kit = request.param
    return build_package(
        EXAMPLES / name, kit.extract_symbols, call_extractor=kit.extract_calls)


class TestOverTheExamples:
    def test_a_named_node_has_a_label_with_no_hash(self, example_graph):
        named = [n for n in example_graph.nodes()
                 if n.kind in _NAMED or n.name is not None]
        assert named
        for node in named:
            assert "#" not in node.label, node.address

    def test_the_rule_of_the_schema_gives_that_label(self, example_graph):
        """A named node's label is what follows the last ``#`` of its
        address (name_graph.json)."""
        for node in example_graph.nodes():
            if node.kind in _NAMED or node.name is not None:
                assert node.address.rsplit("#", 1)[-1] == node.label, (
                    node.address)

    def test_a_module_and_an_appendix_have_none_either(self, example_graph):
        for node in example_graph.nodes():
            if node.kind in (NodeKind.MODULE, NodeKind.APPENDIX):
                assert "#" not in node.label, node.address


# ── A file that does not parse stops a project command ───────

@cache
def _notlob(directory: Path, *args: str) -> tuple[int, str, str]:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    proc = subprocess.run(
        [sys.executable, "-m", "notlob.cli", "-C", str(directory), *args],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, proc.stdout, proc.stderr


_BINDING = "#Sharp Project\n\n---\n\n#Binding\n    ~language python\n"
_GOOD = ("#Good\n\n    def f(): return 1\n\n"
         "~example\n    f() == 1\n")
_BAD = ("#Bad\n\n    def g(): return 1\n\n"
        "##Calling C# from Python\n\nText.\n")
_OTHER_BAD = "#Other Bad\n\n##\n\nText.\n"


def _project(root: Path, **files: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "binding.lob").write_text(_BINDING, encoding="utf-8")
    for name, text in files.items():
        (root / f"{name}.lob").write_text(text, encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def good_project(tmp_path_factory) -> Path:
    return _project(tmp_path_factory.mktemp("good"), good=_GOOD)


@pytest.fixture(scope="module")
def bad_project(tmp_path_factory) -> Path:
    return _project(tmp_path_factory.mktemp("bad"), good=_GOOD, bad=_BAD)


@pytest.fixture(scope="module")
def two_bad_projects(tmp_path_factory) -> Path:
    return _project(tmp_path_factory.mktemp("two"), good=_GOOD, bad=_BAD,
                    other=_OTHER_BAD)


#: Every command that reads a project.
PROJECT_COMMANDS = [
    ["test"], ["test", "--format", "json"], ["test", "good.lob"],
    ["check"], ["check", "--format", "json"],
    ["graph"], ["graph", "--format", "json"], ["graph", "--format", "turtle"],
    ["graph", "good.lob"],
    ["query", "search", "f"], ["query", "children", "good"],
    ["query", "content", "good", "--format", "json"],
    ["build"], ["build", "good.lob"], ["weave"],
]


class TestAFileThatDoesNotParse:
    @pytest.mark.parametrize("argv", PROJECT_COMMANDS, ids=" ".join)
    def test_stops_the_command(self, bad_project, argv):
        code, out, err = _notlob(bad_project, *argv)
        assert code == 1, (out, err)
        assert out == ""
        assert err == (
            "ERROR  <parse>  bad.lob:5: a name may not hold '#': "
            "'Calling C# from Python'\n")

    @pytest.mark.parametrize("argv", [["test"], ["check"], ["graph"],
                                      ["weave"], ["query", "search", "f"]],
                             ids=" ".join)
    def test_each_failure_is_reported(self, two_bad_projects, argv):
        code, out, err = _notlob(two_bad_projects, *argv)
        assert (code, out) == (1, "")
        lines = [ln for ln in err.splitlines() if ln.startswith("ERROR")]
        assert lines[0].startswith("ERROR  <parse>  bad.lob:5: a name may")
        assert any(ln.startswith("ERROR  <parse>  other.lob:3: ")
                   for ln in err.splitlines())

    @pytest.mark.parametrize("argv", [
        ["test"], ["check"], ["graph"], ["graph", "--format", "json"],
        ["query", "search", "f"], ["weave"],
    ], ids=" ".join)
    def test_with_no_bad_file_they_answer_as_before(self, good_project, argv):
        code, out, err = _notlob(good_project, *argv)
        assert code == 0, (out, err)
        assert out.strip()
        assert "<parse>" not in err

    @pytest.mark.parametrize("source, line, what", [
        ("#Bad\n\n~lemma\n    x == 1\n", 3, "an unknown sigil"),
        ("#Bad\n\n##\n\nText.\n", 3, "a bare ##"),
        ("#Bad\n\n##   \n\nText.\n", 3, "## and spaces"),
        ("", 1, "an empty file"),
    ], ids=["sigil", "bare", "spaces", "empty"])
    @pytest.mark.parametrize("argv", [["test"], ["check"], ["graph"],
                                      ["weave"], ["query", "search", "f"]],
                             ids=" ".join)
    def test_any_failure_is_one_line(
            self, tmp_path_factory, argv, source, line, what):
        root = _project(tmp_path_factory.mktemp("oneline"),
                        good=_GOOD, bad=source)
        code, out, err = _notlob(root, *argv)
        assert (code, out) == (1, ""), what
        lines = err.splitlines()
        assert len(lines) == 1, err
        assert lines[0].startswith(f"ERROR  <parse>  bad.lob:{line}: ")

    def test_the_message_does_not_vary_between_runs(self, tmp_path_factory):
        """Lark lists what it expected from a set, whose order varies."""
        root = _project(tmp_path_factory.mktemp("stable"),
                        good=_GOOD, bad="#Bad\n\n~lemma\n    x == 1\n")
        seen = {subprocess.run(
            [sys.executable, "-m", "notlob.cli", "-C", str(root), "graph"],
            cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT),
                           "PYTHONHASHSEED": str(seed)},
            capture_output=True, text=True, encoding="utf-8").stderr
            for seed in (1, 2, 3)}
        assert len(seen) == 1

    def test_a_bad_binding_stops_every_command(self, tmp_path_factory):
        root = tmp_path_factory.mktemp("badbinding")
        _project(root, good=_GOOD)
        (root / "binding.lob").write_text(
            _BINDING + "    ~property-testing hypothesis\n",
            encoding="utf-8")
        for argv in (["test"], ["check"], ["graph"], ["weave"],
                     ["query", "search", "f"]):
            code, out, err = _notlob(root, *argv)
            assert (code, out) == (1, ""), argv
            assert err.startswith("ERROR  <parse>  binding.lob:7: "), argv
            assert len(err.splitlines()) == 1, err

    def test_weave_does_not_print_the_binding(self, good_project):
        code, out, _ = _notlob(good_project, "weave")
        assert code == 0
        assert "Sharp Project" not in out
        assert "Good" in out

    def test_a_lone_file_outside_a_project_is_named_as_given(self, tmp_path):
        (tmp_path / "sharp.lob").write_text(_BAD, encoding="utf-8")
        # `test` of a file that does not parse reports it as one failure,
        # as it always has.
        for argv, stdout in ((["test", "sharp.lob"],
                              "\n0 passed, 1 failed\n"),
                             (["graph", "sharp.lob"], ""),
                             (["weave", "sharp.lob"], "")):
            code, out, err = _notlob(tmp_path, *argv)
            assert (code, out) == (1, stdout)
            assert err.rstrip().endswith(
                "sharp.lob:5: a name may not hold '#': "
                "'Calling C# from Python'")
            assert err.startswith("ERROR  <parse>  ")
