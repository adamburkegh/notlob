"""One ``--format`` flag, and one path convention.

``test`` and ``check`` take ``--format text|json`` as ``graph`` and ``query
content`` do, and ``--json`` is gone. Every ``file:line`` notlob prints is
relative to the project root, with ``/`` separators, and a claim written
over several lines is printed on one.

The examples are run through the command line, once for each output, from
the repository root with ``-C``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from functools import cache
from pathlib import Path

import jsonschema
import pytest

from notlob.commands import cmd_test

from test_example_projects import _PARAMS

ROOT = Path(__file__).parent.parent
SCHEMAS = ROOT / "notlob" / "schema"
RETAIL = ROOT / "examples" / "retail"

#: A line of ``test``'s text: its tag, then what it says. A detail line
#: (``left:``, ``right:``, ``error:``) and a ``check`` finding's addresses
#: are indented under one.
_STARTS = re.compile(
    r"^(PASS|FAIL|ERROR|SKIP|LINT|CHECK)\s|^\s|^$|^\d+ passed")
_FILE_LINE = re.compile(r"(\S+\.lob):(\d+)")

_LONE = (
    "#Lone\n\n"
    "    def double(n):\n"
    "        return n * 2\n\n"
    "~example\n"
    "    double(2) == 4\n"
)


@cache
def _run(directory: Path, *args: str) -> tuple[int, str, str]:
    """``(exit code, stdout, stderr)`` of ``notlob -C directory *args``
    from the repository root. The TypeScript tools live in this
    repository's node_modules."""
    bin_dir = ROOT / "node_modules" / ".bin"
    env = {**os.environ, "PYTHONPATH": str(ROOT),
           "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    proc = subprocess.run(
        [sys.executable, "-m", "notlob.cli", "-C", str(directory), *args],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, proc.stdout, proc.stderr


def _schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


# ── One flag ─────────────────────────────────────────────────

@pytest.mark.parametrize("command", ["test", "check"])
class TestTheFlag:
    def test_json_is_rejected(self, command):
        code, out, err = _run(RETAIL, command, "--json")
        assert code == 2
        assert "unrecognized arguments: --json" in err
        assert out == ""

    def test_a_format_it_does_not_have_is_rejected(self, command):
        code, out, err = _run(RETAIL, command, "--format", "turtle")
        assert code == 2
        assert "invalid choice" in err

    def test_the_help_has_format_and_not_json(self, command):
        _, out, _ = _run(RETAIL, command, "--help")
        assert "--format" in out
        assert "--json" not in out

    def test_text_is_the_default(self, command):
        assert _run(RETAIL, command) == _run(
            RETAIL, command, "--format", "text")


@pytest.mark.parametrize("project", _PARAMS)
class TestFormatOnAnExample:
    def test_test_json_is_a_document(self, project):
        _, out, _ = _run(project, "test", "--format", "json")
        jsonschema.validate(json.loads(out), _schema("test_result.json"))

    def test_check_json_is_a_document(self, project):
        _, out, _ = _run(project, "check", "--format", "json")
        jsonschema.validate(json.loads(out), _schema("check_result.json"))

    def test_the_json_and_the_text_agree_on_the_counts(self, project):
        _, text, _ = _run(project, "test")
        _, out, _ = _run(project, "test", "--format", "json")
        summary = json.loads(out)["summary"]
        passed = re.search(r"(\d+) passed", text)
        assert passed and int(passed.group(1)) == summary["passed"]


# ── One path convention ──────────────────────────────────────

@pytest.mark.parametrize("project", _PARAMS)
class TestPathsAreFromTheProjectRoot:
    def test_every_file_in_test_text_exists_from_the_root(self, project):
        _, out, err = _run(project, "test")
        for stream in (out, err):
            for file, _ in _FILE_LINE.findall(stream):
                assert (project / file).is_file(), (file, stream)

    def test_every_claim_line_names_its_file_from_the_root(self, project):
        _, out, _ = _run(project, "test")
        claims = [line for line in out.splitlines()
                  if re.match(r"(PASS|FAIL|ERROR)\s", line)]
        assert claims
        for line in claims:
            found = _FILE_LINE.search(line)
            assert found, line
            assert (project / found.group(1)).is_file(), line

    def test_every_file_in_check_text_exists_from_the_root(self, project):
        for args in (("check",), ("check", "--verbose")):
            _, out, err = _run(project, *args)
            for stream in (out, err):
                for file, _ in _FILE_LINE.findall(stream):
                    assert (project / file).is_file(), (file, stream)

    def test_the_json_names_the_same_files(self, project):
        _, out, _ = _run(project, "test", "--format", "json")
        for claim in json.loads(out)["claims"]:
            assert (project / claim["file"]).is_file(), claim


def test_a_nested_module_is_named_from_the_root():
    _, out, _ = _run(RETAIL, "test")
    assert "PASS   pricing/discounts.lob:15  " in out
    assert " discounts.lob:" not in out


def test_the_root_is_the_same_from_below_it():
    """Run in a subdirectory of the project, on a path given relative to
    it: the paths are still from the project root."""
    _, out, _ = _run(RETAIL / "pricing", "test", "discounts.lob")
    assert "PASS   pricing/discounts.lob:15  " in out


# ── A claim is one line ──────────────────────────────────────

@pytest.mark.parametrize("project", _PARAMS)
def test_nothing_in_test_text_runs_on_to_a_second_line(project):
    _, out, _ = _run(project, "test")
    for line in out.splitlines():
        assert _STARTS.match(line), line


def test_a_claim_over_several_lines_is_joined_by_single_spaces():
    _, out, _ = _run(RETAIL, "test")
    assert (
        "PASS   pricing/discounts.lob:27  "
        "pricing/discounts#Stacking Discounts#example#1  "
        "(apply_discount(Decimal('0.8'), "
        "apply_discount(Decimal('0.9'), Decimal('100'))) "
        "== Decimal('72'))"
    ) in out.splitlines()


def test_the_json_keeps_the_claim_as_written():
    _, out, _ = _run(RETAIL, "test", "--format", "json")
    claim = next(c for c in json.loads(out)["claims"]
                 if c["address"].endswith("Stacking Discounts#example#1"))
    assert "\n" in claim["source"]


# ── A lone file ──────────────────────────────────────────────

class TestALoneFileOutsideAProject:
    @pytest.fixture
    def lone(self, tmp_path, monkeypatch):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "lone.lob").write_text(_LONE, encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        return tmp_path / "sub" / "lone.lob"

    def test_it_still_prints(self, lone, capsys):
        assert cmd_test(lone) == 0
        out = capsys.readouterr().out
        assert "PASS" in out
        assert "1 passed" in out

    def test_its_path_is_as_it_was_given(self, lone, capsys):
        cmd_test(lone)
        assert "PASS   sub/lone.lob:" in capsys.readouterr().out

    def test_the_json_names_it_the_same_way(self, lone, capsys):
        cmd_test(lone, fmt="json")
        doc = json.loads(capsys.readouterr().out)
        jsonschema.validate(doc, _schema("test_result.json"))
        assert {c["file"] for c in doc["claims"]} == {"sub/lone.lob"}
