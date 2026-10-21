"""The projects under examples/ work end to end.

Until now the suite ran claims on two example modules (roman numerals and
retail discounts), one module at a time, and built a graph of a third; the
Haskell and TypeScript examples were not run at all, and no test ran the
whole command (claims, lint and the project checks together) on any of
them. These tests run, for every project under examples/, `notlob test`
and `notlob build`, and check the graph export against its schema. A new
example is covered automatically. A project whose language toolchain is
not installed is skipped, with the reason.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

import jsonschema
import pytest

from notlob.bindings.python import extract_calls, extract_symbols
from notlob.commands import cmd_build, cmd_test
from notlob.project import build_package

_REPO_ROOT = Path(__file__).resolve().parent.parent
_EXAMPLES = _REPO_ROOT / "examples"
_SCHEMA = _REPO_ROOT / "notlob" / "schema" / "name_graph.json"


def _projects() -> list[Path]:
    return sorted(p.parent for p in _EXAMPLES.glob("*/binding.lob"))


def _language(project: Path) -> str:
    text = (project / "binding.lob").read_text(encoding="utf-8")
    m = re.search(r"~language\s+(\w+)", text)
    return m.group(1) if m else "python"


#: Claims that fail on purpose, by project: address of each. roman's
#: second ~example is "deliberately wrong and expected to fail — it is
#: here to exercise the runner's failure path" (numerals.lob).
_EXPECTED_FAILURES: dict[str, set[str]] = {
    "roman": {"roman/numerals#example#2"},
}


def _skip_reason(language: str, project: Path) -> str | None:
    """Why this project's examples cannot run here, or None."""
    bin_dir = _REPO_ROOT / "node_modules" / ".bin"
    package = project / "package.json"
    if package.exists():
        wanted = json.loads(package.read_text(encoding="utf-8"))
        names = [*wanted.get("dependencies", {}),
                 *wanted.get("devDependencies", {})]
        missing = [n for n in names
                   if not (project / "node_modules" / n).is_dir()]
        if missing:
            return (f"run `npm install` in examples/{project.name} "
                    f"(not installed there: {', '.join(missing)})")
    if language == "haskell":
        if not (shutil.which("runghc") or shutil.which("stack")):
            return "no runghc or stack"
        if not shutil.which("hlint"):
            return "no hlint (the Haskell linter is part of notlob test)"
    if language == "typescript":
        if not (bin_dir / ("tsx.cmd" if os.name == "nt" else "tsx")).exists():
            return "no tsx in node_modules/.bin (npm install)"
        if not (bin_dir / ("tsc.cmd" if os.name == "nt" else "tsc")).exists():
            return "no tsc in node_modules/.bin (npm install)"
    return None


@pytest.fixture(autouse=True)
def _tools_on_path(monkeypatch):
    """The TypeScript tools live in this repository's node_modules, not
    in the example project's."""
    bin_dir = _REPO_ROOT / "node_modules" / ".bin"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


def _project_param(project: Path):
    language = _language(project)
    reason = _skip_reason(language, project)
    return pytest.param(
        project, id=f"{project.name}-{language}",
        marks=pytest.mark.skipif(reason is not None,
                                 reason=reason or ""),
    )


_PARAMS = [_project_param(p) for p in _projects()]


def test_there_are_example_projects():
    """Guard: discovery found the examples."""
    assert len(_projects()) >= 5


@pytest.mark.parametrize("project", _PARAMS)
class TestExampleProject:
    def test_notlob_test_gives_the_expected_result(
        self, project, monkeypatch, capsys,
    ):
        """Claims, lint and the project checks together, as a user runs
        `notlob test` in the project: no failure except the ones an
        example makes on purpose, no lint finding, no check error."""
        monkeypatch.chdir(project)
        rc = cmd_test(None, json_mode=True)
        captured = capsys.readouterr()
        doc = json.loads(captured.out)
        failing = {c["address"] for c in doc["claims"]
                   if c["status"] in ("FAIL", "ERROR")}
        expected = _EXPECTED_FAILURES.get(project.name, set())
        assert failing == expected, doc
        assert doc["lint"] == [], doc["lint"]
        assert [c for c in doc["checks"] if c["severity"] == "error"] == []
        assert doc["claims"], "the project ran no claims"
        # A module that could not be checked at all (a parse, address or
        # reference error) is counted as a failure but is not a claim;
        # its message is on stderr.
        assert rc == (1 if expected else 0), captured.err + str(doc)

    def test_notlob_build_succeeds(self, project, monkeypatch, tmp_path,
                                   capsys):
        monkeypatch.chdir(project)
        rc = cmd_build(None, output_dir=tmp_path / "dist", skip_tests=True)
        out = capsys.readouterr()
        assert rc == 0, out.out + out.err
        assert list((tmp_path / "dist").iterdir()), "nothing was built"


@pytest.mark.parametrize("project", [
    p for p in _projects() if _language(p) == "python"
], ids=lambda p: p.name)
class TestExampleGraph:
    def test_export_conforms_to_the_schema(self, project):
        """The graph of a real project, with content, against the
        published schema (the schema once rejected bullet-list content
        that tests with small sources never produced)."""
        graph = build_package(project, extract_symbols,
                              call_extractor=extract_calls)
        schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
        jsonschema.validate(graph.to_dict(include_content=True), schema)
