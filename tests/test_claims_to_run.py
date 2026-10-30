"""The claims and tests of a module, as notlob collects them for a binding.

`claims_to_run` reads them from the graph, in document order, wherever
they are written: the body, subheadings, an `#Appendix` and its
subheadings, `#Tests` and its groups. A binding is handed what it runs
and keeps everything about its language.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from notlob import NodeKind, build, build_package, from_tree, parse, parse_file
from notlob.bindings import ClaimToRun, run_bodies
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.haskell import runner as haskell_runner
from notlob.bindings.python import kit as python_kit
from notlob.bindings.python import runner as python_runner
from notlob.bindings.typescript import kit as typescript_kit
from notlob.bindings.typescript import runner as typescript_runner
from notlob.graph import (
    _descendants, claims_to_run, module_address, named_address,
)

DATA = Path(__file__).parent / "data"
EXAMPLES = Path(__file__).parent.parent / "examples"

#: One of each claim, in every place one can be written. The comment on
#: each line is its line number.
_EVERYWHERE = (
    "#M\n"                       # 1
    "\n"                         # 2
    "    def f():\n"             # 3
    "        return 1\n"         # 4
    "\n"                         # 5
    "~example\n"                 # 6
    "    f() == 1\n"             # 7
    "\n"                         # 8
    "~property p\n"              # 9
    "    @given()\n"             # 10
    "    def _(n):\n"            # 11
    "        pass\n"             # 12
    "\n"                         # 13
    "~run\n"                     # 14
    "    print(f())\n"           # 15
    "\n"                         # 16
    "~run on-load\n"             # 17
    "    boot()\n"               # 18
    "\n"                         # 19
    "##S\n"                      # 20
    "\n"                         # 21
    "~example\n"                 # 22
    "    f() == 2\n"             # 23
    "\n"                         # 24
    "---\n"                      # 25
    "\n"                         # 26
    "#Tests\n"                   # 27
    "\n"                         # 28
    "    f() == 3\n"             # 29
    "\n"                         # 30
    "Commentary.\n"              # 31
    "\n"                         # 32
    "    f() == 4\n"             # 33
    "\n"                         # 34
    "##g\n"                      # 35
    "    f() == 5\n"             # 36
    "\n"                         # 37
    "~test nm\n"                 # 38
    "    f() == 6\n"             # 39
    "\n"                         # 40
    "#Appendix Notes\n"          # 41
    "\n"                         # 42
    "~example\n"                 # 43
    "    f() == 7\n"             # 44
    "\n"                         # 45
    "##AppSub\n"                 # 46
    "\n"                         # 47
    "~property\n"                # 48
    "    def _(): pass\n"        # 49
)


def _claims(source: str) -> list[ClaimToRun]:
    module = from_tree(parse(source))
    return claims_to_run(build(module), module_address(module.title))


def _as_tuple(claim: ClaimToRun) -> tuple:
    return (claim.address, claim.kind, claim.name, claim.mode,
            claim.first_line, claim.sigil_line, claim.lines)


class TestWhereClaimsAreWritten:
    def test_every_claim_and_test_in_document_order(self):
        assert [_as_tuple(c) for c in _claims(_EVERYWHERE)] == [
            ("m#example#1", "EXAMPLE", None, None, 7, 6,
             ["f() == 1"]),
            ("m#p", "PROPERTY", "p", None, 10, 9,
             ["@given()", "def _(n):", "    pass"]),
            ("m#run#1", "RUN", None, "on-invocation", 15, 14,
             ["print(f())"]),
            ("m#run#2", "RUN", None, "on-load", 18, 17, ["boot()"]),
            ("m#S#example#1", "EXAMPLE", None, None, 23, 22,
             ["f() == 2"]),
            ("m#Tests#test#1", "TEST", None, None, 29, None,
             ["    f() == 3"]),
            ("m#Tests#test#2", "TEST", None, None, 33, None,
             ["    f() == 4"]),
            ("m#Tests#g#test#1", "TEST", None, None, 36, None,
             ["    f() == 5"]),
            ("m#Tests#g#nm", "TEST", "nm", None, 39, 38,
             ["    f() == 6"]),
            ("m#appendix#1#example#1", "EXAMPLE", None, None, 44, 43,
             ["f() == 7"]),
            ("m#AppSub#property#1", "PROPERTY", None, None, 49, 48,
             ["def _(): pass"]),
        ]

    def test_symbols_prose_and_code_are_not_claims(self):
        kinds = {c.kind for c in _claims(_EVERYWHERE)}
        assert kinds == {"EXAMPLE", "PROPERTY", "RUN", "TEST"}

    def test_a_run_of_assertions_reports_at_its_own_address(self):
        claims = _claims(_EVERYWHERE)
        runs = [c for c in claims if c.kind == "TEST" and c.name is None]
        assert [c.address for c in runs] == [
            "m#Tests#test#1", "m#Tests#test#2", "m#Tests#g#test#1"]

    def test_that_address_is_a_node_of_the_graph(self):
        module = from_tree(parse(_EVERYWHERE))
        graph = build(module)
        runs = [c for c in claims_to_run(graph, "m")
                if c.kind == "TEST" and c.name is None]
        assert [graph.node(c.address).kind for c in runs] == (
            [NodeKind.TEST] * 3)
        assert [graph.node(c.address).start_line for c in runs] == [
            c.first_line for c in runs]

    def test_a_run_has_no_sigil_line_and_its_own_first_line(self):
        runs = [c for c in _claims(_EVERYWHERE)
                if c.kind == "TEST" and c.name is None]
        assert [(c.sigil_line, c.first_line) for c in runs] == [
            (None, 29), (None, 33), (None, 36)]

    def test_commentary_ends_a_run(self):
        runs = [c for c in _claims(_EVERYWHERE)
                if c.kind == "TEST" and c.address.startswith("m#Tests#test#")]
        assert [(c.address, c.first_line, c.lines) for c in runs] == [
            ("m#Tests#test#1", 29, ["    f() == 3"]),
            ("m#Tests#test#2", 33, ["    f() == 4"])]

    def test_a_named_test_keeps_its_own_address(self):
        (named,) = [c for c in _claims(_EVERYWHERE) if c.name == "nm"]
        assert (named.address, named.sigil_line) == ("m#Tests#g#nm", 38)

    def test_a_module_with_no_claims(self):
        assert _claims("#M\n\nText.\n\n    x = 1\n") == []

    def test_blank_lines_before_the_first_assertion_are_kept(self):
        (claim,) = _claims("#M\n\n~example\n\n\n    f() == 1\n")
        assert claim.first_line == 4
        assert claim.lines == ["", "", "f() == 1"]

    def test_only_the_modules_own_claims(self):
        a = from_tree(parse("#A\n\n~example\n    1 == 1\n"))
        b = from_tree(parse("#B\n\n~example\n    2 == 2\n"))
        graph = build(a)
        graph.merge(build(b))
        assert [c.address for c in claims_to_run(graph, "b")] == [
            "b#example#1"]


class TestRunBodies:
    def test_grouped_by_mode_in_document_order(self):
        claims = _claims(
            "#M\n\n~run\n    a()\n\n~run on-load\n    b()\n\n##S\n\n"
            "~run on-invocation\n    c()\n\n~run on-load\n    d()\n")
        assert run_bodies(claims) == (["b()", "d()"], ["a()", "c()"])

    def test_a_bare_run_is_on_invocation(self):
        assert run_bodies(_claims("#M\n\n~run\n    a()\n")) == ([], ["a()"])

    def test_only_runs_count(self):
        assert run_bodies(_claims(_EVERYWHERE)) == (
            ["boot()"], ["print(f())"])

    def test_text_is_stripped_and_empty_runs_are_left_out(self):
        claims = _claims("#M\n\n~run\n\n    a()\n    b()\n\n")
        assert run_bodies(claims) == ([], ["a()\nb()"])


class TestWhatTheRunnerReports:
    """`notlob test` on the Roman example, as the command runs it."""

    def _claims(self, capsys):
        from notlob.commands import cmd_test
        cmd_test(EXAMPLES / "roman" / "roman" / "numerals.lob",
                 fmt="json")
        return json.loads(capsys.readouterr().out)["claims"]

    def test_a_bare_assertion_carries_its_blocks_address(self, capsys):
        tests = [c for c in self._claims(capsys) if c["kind"] == "TEST"]
        assert {c["address"] for c in tests} == {
            "roman/numerals#Tests#encoding#test#1",
            "roman/numerals#Tests#encoding#mcmxciv",
            "roman/numerals#Tests#decoding#test#1",
            "roman/numerals#Tests#round-trip#test#1",
        }

    def test_each_assertion_of_the_block_is_reported_at_its_line(
        self, capsys,
    ):
        block = [c for c in self._claims(capsys)
                 if c["address"] == "roman/numerals#Tests#encoding#test#1"]
        assert [c["line"] for c in block] == list(range(78, 87))

    def test_an_unnamed_property_stays_at_its_section(self, capsys):
        properties = [c for c in self._claims(capsys)
                      if c["kind"] == "PROPERTY"]
        assert [c["address"] for c in properties] == [
            "roman/numerals#Round-Trip#property#1"]


class TestNoGraphKeepsACollisionList:
    def test_build_leaves_none_behind(self):
        collected = []
        graph = build(from_tree(parse(
            "#M\n\n##Same\n\nOne.\n\n##Same\n\nTwo.\n")),
            collisions=collected)
        assert len(collected) == 1
        assert not any(value is collected for value in vars(graph).values())
        assert getattr(graph, "_collisions", None) is None

    def test_nor_does_a_package_graph(self, tmp_path):
        (tmp_path / "notes.lob").write_text(
            "#Notes\n\n##Same\n\nOne.\n\n##Same\n\nTwo.\n", encoding="utf-8")
        graph = build_package(tmp_path, collisions=[])
        assert getattr(graph, "_collisions", None) is None


# ── What the runners collected before notlob collected the claims ──

_KITS = {
    "roman": ("python", python_kit, python_runner),
    "retail": ("python", python_kit, python_runner),
    "gutenberg": ("python", python_kit, python_runner),
    "haskell-roman": ("haskell", haskell_kit, haskell_runner),
    "ts-media": ("typescript", typescript_kit, typescript_runner),
}


def _recorded(project: str) -> dict:
    return json.loads(
        (DATA / f"claims_{project}.json").read_text(encoding="utf-8"))


def _in_an_appendix(graph) -> set[int]:
    """The ids of the nodes written in an `#Appendix` of the graph."""
    found = set()
    for appendix in graph.nodes(NodeKind.APPENDIX):
        found.update(n.address for n in _descendants(graph, appendix.address))
    return found


def _module_claims(path: Path):
    module = from_tree(parse_file(path))
    graph = build(module)
    return graph, claims_to_run(graph, module_address(module.title))


def _as_recorded(graph, claim) -> str:
    """The address the runners reported *claim* at before notlob
    collected the claims: a run of bare assertions at the node it is
    written in, a named property in the scope of its section."""
    holder = graph.parent_of(claim.address).address
    if claim.kind == "TEST" and claim.name is None:
        return holder
    if claim.kind == "PROPERTY" and claim.name is not None:
        return named_address(holder, claim.name)
    return claim.address


@pytest.mark.parametrize("project", sorted(_KITS))
class TestAgainstWhatTheRunnersCollected:
    """`tests/data/claims_*.json` is what each runner collected from every
    example module, before the collection moved to the graph. Two
    addresses have moved since, on purpose, and are compared through
    `_as_recorded`."""

    def _expand(self, project, graph, claims, kind):
        iterate = _KITS[project][2]._iter_assertions
        return [
            [_as_recorded(graph, c), expr, c.first_line + offset]
            for c in claims if c.kind == kind
            for expr, offset in iterate(c.lines)
        ]

    def test_examples(self, project):
        for name, recorded in _recorded(project).items():
            graph, claims = _module_claims(EXAMPLES / project / name)
            assert self._expand(project, graph, claims, "EXAMPLE") == (
                recorded["examples"]), name

    def test_tests(self, project):
        for name, recorded in _recorded(project).items():
            graph, claims = _module_claims(EXAMPLES / project / name)
            assert self._expand(project, graph, claims, "TEST") == (
                recorded["tests"]), name

    def test_properties(self, project):
        for name, recorded in _recorded(project).items():
            graph, claims = _module_claims(EXAMPLES / project / name)
            got = [[_as_recorded(graph, c),
                    "~property" + (f" {c.name}" if c.name else ""),
                    c.sigil_line]
                   for c in claims if c.kind == "PROPERTY"]
            assert got == recorded["properties"], name

    def test_runs(self, project):
        for name, recorded in _recorded(project).items():
            _graph, claims = _module_claims(EXAMPLES / project / name)
            on_load, on_invocation = run_bodies(claims)
            assert {"on_load": on_load, "on_invocation": on_invocation} == (
                recorded["runs"]), name

    def test_no_example_has_a_claim_in_an_appendix(self, project):
        for name in _recorded(project):
            module = from_tree(parse_file(EXAMPLES / project / name))
            graph = build(module)
            held = _in_an_appendix(graph)
            claims = claims_to_run(graph, module_address(module.title))
            assert [c.address for c in claims if c.address in held] == [], (
                name)
