"""The shape of ``notlob test --json`` (a stable machine-readable output).

Written for the notlob-vids consumer, which draws a tick beside each
claim's source line:
meta/features/2026-10-03-test-json-shape/design.md.  This replaced an
undocumented shape that mixed claims and lint findings in one ``results``
list, called the assertion text ``line`` and its number ``source_line``,
and gave a bare file name.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from notlob.commands import cmd_test

SCHEMA = (
    Path(__file__).parent.parent / "notlob" / "schema" / "test_result.json"
)

_BINDING = "#Json Repro\n\n---\n\n#Binding\n    ~language python\n"

_CALC = (
    "#Pkg Calc\n\n"
    "Doubles a number.\n\n"
    "    def double(n):\n"
    "        return n * 2\n\n"
    "~example\n"
    "    double(2) == 4\n"
    "    double(2) == 5\n\n"
    "~property\n"
    "    @given(n=st.integers(min_value=0, max_value=5))\n"
    "    def _(n):\n"
    "        assert double(n) == n + n\n\n"
    "---\n\n"
    "#Tests\n\n"
    "##basics\n"
    "    double(1) == 2\n\n"
    "#References\n"
    "    import os\n"
)

# A second module with the same file name, in another directory.
_OTHER = (
    "#Other Calc\n\n"
    "Triples a number.\n\n"
    "    def triple(n):\n"
    "        return n * 3\n\n"
    "~example\n"
    "    triple(2) == 6\n"
)


def _write(root: Path, name: str, content: str) -> Path:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def project(tmp_path, monkeypatch):
    _write(tmp_path, "binding.lob", _BINDING)
    _write(tmp_path, "pkg/calc.lob", _CALC)
    _write(tmp_path, "other/calc.lob", _OTHER)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(capsys, path):
    """Run ``cmd_test`` in JSON mode; return ``(exit_code, document)``.
    Parsing all of stdout as JSON is itself the 'stdout is only the
    document' check."""
    rc = cmd_test(path, json_mode=True)
    return rc, json.loads(capsys.readouterr().out)


def _line_of(text: str, needle: str) -> int:
    return text.splitlines().index(needle) + 1


class TestSingleFile:
    def test_claims_are_their_own_list(self, project, capsys):
        _rc, doc = _run(capsys, project / "pkg" / "calc.lob")
        assert doc["version"] == 1
        assert "results" not in doc
        assert {c["kind"] for c in doc["claims"]} == {
            "EXAMPLE", "PROPERTY", "TEST",
        }
        assert all("code" not in c for c in doc["claims"])

    def test_lint_findings_are_their_own_list(self, project, capsys):
        _rc, doc = _run(capsys, project / "pkg" / "calc.lob")
        assert [f["code"] for f in doc["lint"]] == ["F401"]
        assert all("status" not in f for f in doc["lint"])

    def test_summary_counts(self, project, capsys):
        _rc, doc = _run(capsys, project / "pkg" / "calc.lob")
        assert doc["summary"] == {"passed": 3, "failed": 1, "lint": 1}

    def test_line_is_the_source_line_number(self, project, capsys):
        _rc, doc = _run(capsys, project / "pkg" / "calc.lob")
        by_source = {c["source"]: c for c in doc["claims"]
                     if c["kind"] != "PROPERTY"}
        assert by_source["double(2) == 4"]["line"] == _line_of(
            _CALC, "    double(2) == 4")
        assert by_source["double(2) == 5"]["line"] == _line_of(
            _CALC, "    double(2) == 5")
        assert by_source["double(1) == 2"]["line"] == _line_of(
            _CALC, "    double(1) == 2")
        assert all(isinstance(c["line"], int) for c in doc["claims"])

    def test_property_line_is_its_sigil_line(self, project, capsys):
        _rc, doc = _run(capsys, project / "pkg" / "calc.lob")
        prop = next(c for c in doc["claims"] if c["kind"] == "PROPERTY")
        assert prop["line"] == _line_of(_CALC, "~property")

    def test_failure_carries_both_sides(self, project, capsys):
        _rc, doc = _run(capsys, project / "pkg" / "calc.lob")
        bad = next(c for c in doc["claims"]
                   if c["source"] == "double(2) == 5")
        assert bad["status"] == "FAIL"
        assert (bad["left"], bad["right"]) == ("4", "5")

    def test_file_is_relative_to_the_project_root(self, project, capsys):
        _rc, doc = _run(capsys, project / "pkg" / "calc.lob")
        assert {c["file"] for c in doc["claims"]} == {"pkg/calc.lob"}

    def test_only_that_modules_claims(self, project, capsys):
        _rc, doc = _run(capsys, project / "pkg" / "calc.lob")
        assert all(c["address"].startswith("pkg/calc") for c in doc["claims"])

    def test_address_is_present(self, project, capsys):
        _rc, doc = _run(capsys, project / "pkg" / "calc.lob")
        assert "pkg/calc#example#1" in {c["address"] for c in doc["claims"]}

    def test_exit_code_unchanged_by_json(self, project, capsys):
        rc, _doc = _run(capsys, project / "pkg" / "calc.lob")
        assert rc == 1  # a failing claim and a lint finding

    def test_passing_module_exits_zero(self, project, capsys):
        rc, doc = _run(capsys, project / "other" / "calc.lob")
        assert rc == 0
        assert [c["status"] for c in doc["claims"]] == ["PASS"]

    def test_no_checks_key_for_a_single_file(self, project, capsys):
        _rc, doc = _run(capsys, project / "pkg" / "calc.lob")
        assert "checks" not in doc

    def test_old_names_are_gone(self, project, capsys):
        _rc, doc = _run(capsys, project / "pkg" / "calc.lob")
        for claim in doc["claims"]:
            assert "source_line" not in claim


class TestProject:
    def test_same_file_name_in_two_directories_is_distinguishable(
        self, project, capsys,
    ):
        _rc, doc = _run(capsys, None)
        assert {c["file"] for c in doc["claims"]} == {
            "pkg/calc.lob", "other/calc.lob",
        }

    def test_checks_always_present_in_project_mode(self, project, capsys):
        _rc, doc = _run(capsys, None)
        assert isinstance(doc["checks"], list)

    def test_checks_present_even_when_empty(
        self, tmp_path, monkeypatch, capsys,
    ):
        _write(tmp_path, "binding.lob", _BINDING)
        _write(tmp_path, "other/calc.lob", _OTHER)
        monkeypatch.chdir(tmp_path)
        _rc, doc = _run(capsys, None)
        assert doc["checks"] == []

    def test_summary_spans_the_project(self, project, capsys):
        _rc, doc = _run(capsys, None)
        assert doc["summary"] == {"passed": 4, "failed": 1, "lint": 1}


class TestSchema:
    @pytest.mark.parametrize("target", ["pkg/calc.lob", None])
    def test_output_conforms_to_the_schema(self, project, capsys, target):
        path = project / target if target else None
        _rc, doc = _run(capsys, path)
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        jsonschema.validate(doc, schema)

    def test_every_schema_is_packaged(self):
        """A schema missing from package-data is in a checkout but not an
        install, and a stable output's schema is part of its contract."""
        import fnmatch
        import tomllib
        root = SCHEMA.parent.parent.parent
        listed = tomllib.loads(
            (root / "pyproject.toml").read_text(encoding="utf-8")
        )["tool"]["setuptools"]["package-data"]["notlob"]
        on_disk = {
            p.relative_to(root / "notlob").as_posix()
            for p in SCHEMA.parent.iterdir()
            if p.suffix in (".json", ".ttl")
        }
        assert on_disk  # guard: the glob found the schemas
        unpackaged = {
            f for f in on_disk
            if not any(fnmatch.fnmatch(f, pattern) for pattern in listed)
        }
        assert not unpackaged, unpackaged

    def test_schema_requires_a_version(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        assert "version" in schema["required"]
