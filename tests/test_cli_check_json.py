"""The shape of ``notlob check --json`` (a stable machine-readable output).

Specified by ``notlob/schema/check_result.json``. A finding has the same
shape here as in the ``checks`` list of ``notlob test --json``
(``test_result.json``); the two schemas carry identical ``CheckFinding``
definitions and a test below keeps them identical.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from notlob.check import CHECK_NAMES
from notlob.commands import cmd_check

SCHEMA_DIR = Path(__file__).parent.parent / "notlob" / "schema"
SCHEMA = SCHEMA_DIR / "check_result.json"

_BINDING = "#Check Repro\n\n---\n\n#Binding\n    ~language python\n"

# An advisory (`quantifier`: a quantified claim with nothing pinning it).
_A = (
    "#A\n\n"
    "Each token fires a randomly chosen transition.\n\n"
    "    def alpha_thing():\n        return 1\n"
)
# An error (`imports`: references #A but uses none of its symbols).
_B = (
    "#B\n\nBeta.\n\n"
    "    def beta_thing():\n        return 2\n\n"
    "---\n\n#References\n    #A\n"
)
_CLEAN = "#A\n\nAlpha.\n\n    def alpha_thing():\n        return 1\n"


def _write(root: Path, name: str, content: str) -> Path:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def project(tmp_path, monkeypatch):
    _write(tmp_path, "binding.lob", _BINDING)
    _write(tmp_path, "a.lob", _A)
    _write(tmp_path, "b.lob", _B)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(capsys, only=None):
    rc = cmd_check(only=only, fmt="json")
    return rc, json.loads(capsys.readouterr().out)


def _schema(name: str = "check_result.json") -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


class TestDocument:
    def test_shape(self, project, capsys):
        _rc, doc = _run(capsys)
        assert doc["version"] == 1
        assert set(doc) == {"version", "findings", "counts"}

    def test_findings(self, project, capsys):
        _rc, doc = _run(capsys)
        by_check = {f["check"]: f for f in doc["findings"]}
        assert by_check["imports"]["severity"] == "error"
        assert by_check["quantifier"]["severity"] == "advisory"
        assert by_check["imports"]["addresses"]
        assert all(isinstance(a, str)
                   for f in doc["findings"] for a in f["addresses"])

    def test_counts_cover_every_check_that_ran(self, project, capsys):
        _rc, doc = _run(capsys)
        assert set(doc["counts"]) == set(CHECK_NAMES)
        assert doc["counts"]["imports"] == 1
        assert doc["counts"]["quantifier"] == 1

    def test_only_restricts_the_counts(self, project, capsys):
        _rc, doc = _run(capsys, only={"quantifier"})
        assert set(doc["counts"]) == {"quantifier"}
        assert {f["check"] for f in doc["findings"]} == {"quantifier"}

    def test_exit_code_unchanged_by_json(self, project, capsys):
        rc, _doc = _run(capsys)
        assert rc == 1          # an error-severity finding

    def test_advisory_only_exits_zero(self, project, capsys):
        rc, doc = _run(capsys, only={"quantifier"})
        assert rc == 0
        assert doc["findings"]

    def test_clean_project(self, tmp_path, monkeypatch, capsys):
        _write(tmp_path, "binding.lob", _BINDING)
        _write(tmp_path, "a.lob", _CLEAN)
        monkeypatch.chdir(tmp_path)
        rc, doc = _run(capsys)
        assert rc == 0
        assert doc["findings"] == []
        assert set(doc["counts"].values()) == {0}


_COLLISION = (
    "#Shapes\n\n"
    "A subheading and a class share the name Layout.\n\n"
    "    class Layout:\n        pass\n\n"
    "##Layout\n\nPlacing shapes.\n\n"
    "    def place():\n        return Layout()\n"
)


class TestAddressCollision:
    """Under an address collision (a subheading and a symbol sharing a
    name) `--json` still prints a valid document, as `test --json` does:
    a consumer must be able to `json.loads` stdout whenever there is a
    project, and the failure is a finding, not only a line on stderr."""

    def _collide(self, tmp_path, monkeypatch):
        _write(tmp_path, "binding.lob", _BINDING)
        _write(tmp_path, "shapes.lob", _COLLISION)
        monkeypatch.chdir(tmp_path)

    def test_valid_document_with_a_names_finding(
        self, tmp_path, monkeypatch, capsys,
    ):
        self._collide(tmp_path, monkeypatch)
        rc, doc = _run(capsys)
        assert rc == 1
        jsonschema.validate(doc, _schema())
        assert [f["check"] for f in doc["findings"]] == ["names"]
        finding = doc["findings"][0]
        assert finding["severity"] == "error"
        assert finding["addresses"] == ["shapes#Layout"]
        assert "Layout" in finding["message"]

    def test_no_checks_ran_so_counts_is_empty(
        self, tmp_path, monkeypatch, capsys,
    ):
        self._collide(tmp_path, monkeypatch)
        _rc, doc = _run(capsys)
        assert doc["counts"] == {}

    def test_text_mode_still_reports_on_stderr(
        self, tmp_path, monkeypatch, capsys,
    ):
        self._collide(tmp_path, monkeypatch)
        rc = cmd_check()
        captured = capsys.readouterr()
        assert rc == 1
        assert "ERROR  <names>" in captured.err
        assert captured.out == ""


class TestNoProject:
    def test_no_document_and_exit_one(self, tmp_path, monkeypatch, capsys):
        """With no project there is nothing to check: an error on
        stderr, nothing on stdout, exit 1. (Documented in the schema.)"""
        monkeypatch.chdir(tmp_path)
        rc = cmd_check(fmt="json")
        captured = capsys.readouterr()
        assert rc == 1
        assert captured.out == ""
        assert "no binding.lob" in captured.err


class TestSchema:
    def test_documents_conform(self, project, capsys):
        for only in (None, {"quantifier"}):
            _rc, doc = _run(capsys, only=only)
            jsonschema.validate(doc, _schema())

    def test_clean_document_conforms(self, tmp_path, monkeypatch, capsys):
        _write(tmp_path, "binding.lob", _BINDING)
        _write(tmp_path, "a.lob", _CLEAN)
        monkeypatch.chdir(tmp_path)
        _rc, doc = _run(capsys)
        jsonschema.validate(doc, _schema())

    def test_schema_is_valid_json_schema(self):
        jsonschema.Draft7Validator.check_schema(_schema())

    def test_schema_requires_a_version(self):
        assert "version" in _schema()["required"]

    def test_counts_names_are_exactly_the_registered_checks(self):
        """Adding a check without updating the schema must fail here."""
        counts = _schema()["properties"]["counts"]["properties"]
        assert set(counts) == set(CHECK_NAMES)

    def test_finding_check_names_are_the_registered_checks(self):
        """`check` is an enum of the registered checks, plus `names`,
        the synthetic finding `test --json` reports for an address
        collision."""
        enum = _schema()["definitions"]["CheckFinding"]["properties"][
            "check"]["enum"]
        assert set(enum) == set(CHECK_NAMES) | {"names"}

    def test_finding_definition_matches_test_result_schema(self):
        """One shape, specified twice (a cross-file $ref would need a
        resolver in every consumer, and the written schemas must each
        stand alone): the two definitions must not drift apart."""
        assert (
            _schema()["definitions"]["CheckFinding"]
            == _schema("test_result.json")["definitions"]["CheckFinding"]
        )
