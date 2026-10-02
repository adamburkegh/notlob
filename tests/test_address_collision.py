"""Regression tests for the address-collision crash.

A ##Subheading and a symbol (e.g. a class) sharing one name in the same
module both resolve to the same graph address -- a real document error
(all named things share one namespace per module), but it used to
surface as an uncaught ValueError with a full Python traceback instead
of a reported ``ERROR`` line, because nothing calling enrich()/
build_package() caught it. Fixed by giving NameGraph.add_node a
dedicated AddressCollisionError (ValueError subclass, with structured
address/kind/line fields) and catching it at every place a graph gets
built: _require_graph, _run_check_advisory, cmd_test's per-file
_build_ref_graph path and its project-mode json/advisory paths, and
cmd_graph's single-file and project-mode build_package calls.
"""

from __future__ import annotations

from pathlib import Path

from notlob import AddressCollisionError, NodeKind, enrich, from_tree, parse
from notlob.commands import cmd_check, cmd_graph, cmd_test

_BINDING = (
    "#Collision Repro\n\n---\n\n"
    "#Binding\n"
    "    ~language python\n"
)

_SHAPES_LOB = (
    "#Shapes\n\n"
    "A subheading and a class share the name Layout.\n\n"
    "    class Layout:\n"
    "        pass\n\n"
    "##Layout\n\n"
    "Placing shapes.\n\n"
    "    def place():\n"
    "        return Layout()\n\n"
    "~example\n"
    "    isinstance(place(), Layout)\n"
)


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _project(tmp_path: Path) -> Path:
    _write(tmp_path, "binding.lob", _BINDING)
    return tmp_path


# ── AddressCollisionError itself ────────────────────────────────

class TestAddressCollisionError:
    def test_raised_instead_of_bare_value_error(self):
        from notlob.bindings.python.symbols import extract_symbols

        module = from_tree(parse(_SHAPES_LOB))
        graph = __import__("notlob").build(module)
        try:
            enrich(graph, module, extract_symbols)
        except AddressCollisionError as exc:
            assert exc.address == "shapes#Layout"
            assert {exc.existing_kind, exc.new_kind} == {
                NodeKind.SUBHEADING, NodeKind.SYMBOL,
            }
            assert exc.existing_line is not None
            assert exc.new_line is not None
            assert "shapes#Layout" in str(exc)
            assert "namespace" in str(exc)
        else:
            raise AssertionError("expected AddressCollisionError")


# ── cmd_test: single file (the exact bug-report repro) ──────────

class TestCmdTestSingleFile:
    def test_reports_error_not_traceback(self, tmp_path, capsys):
        root = _project(tmp_path)
        lob = _write(root, "shapes.lob", _SHAPES_LOB)

        # Must not raise -- this is the actual crash from the report.
        rc = cmd_test(lob)

        assert rc == 1
        err = capsys.readouterr().err
        assert "ERROR" in err
        assert "<names>" in err
        assert "shapes#Layout" in err

    def test_other_modules_in_project_still_run(
        self, tmp_path, capsys, monkeypatch,
    ):
        """One module's collision must not stop a sibling module's
        claims from running, in project mode."""
        root = _project(tmp_path)
        _write(root, "shapes.lob", _SHAPES_LOB)
        _write(root, "alpha.lob", (
            "#Alpha\n\n"
            "    def double(x):\n        return x * 2\n\n"
            "~example\n"
            "    double(3) == 6\n"
        ))
        monkeypatch.chdir(root)

        rc = cmd_test(None)

        assert rc == 1  # shapes.lob's collision still fails the run
        out = capsys.readouterr().out
        assert "1 passed" in out or "passed" in out


# ── cmd_test: project mode, json ─────────────────────────────────

class TestCmdTestProjectJson:
    def test_json_mode_reports_collision_as_finding(
        self, tmp_path, capsys, monkeypatch,
    ):
        root = _project(tmp_path)
        _write(root, "shapes.lob", _SHAPES_LOB)
        monkeypatch.chdir(root)

        rc = cmd_test(None, json_mode=True)

        assert rc == 1
        import json
        output = json.loads(capsys.readouterr().out)
        findings = output.get("check_findings", [])
        assert any(
            f["check"] == "names" and f["severity"] == "error"
            for f in findings
        )


# ── cmd_graph ─────────────────────────────────────────────────

class TestCmdGraph:
    def test_single_file_reports_error_not_traceback(
        self, tmp_path, capsys,
    ):
        root = _project(tmp_path)
        lob = _write(root, "shapes.lob", _SHAPES_LOB)

        rc = cmd_graph(lob)

        assert rc == 1
        err = capsys.readouterr().err
        assert "ERROR" in err
        assert "<names>" in err

    def test_project_mode_reports_error_not_traceback(
        self, tmp_path, capsys, monkeypatch,
    ):
        root = _project(tmp_path)
        _write(root, "shapes.lob", _SHAPES_LOB)
        monkeypatch.chdir(root)

        rc = cmd_graph(None)

        assert rc == 1
        err = capsys.readouterr().err
        assert "ERROR" in err
        assert "<names>" in err


# ── cmd_check (exercises _require_graph's own fix) ──────────────

class TestCmdCheck:
    def test_reports_error_not_traceback(self, tmp_path, capsys, monkeypatch):
        root = _project(tmp_path)
        _write(root, "shapes.lob", _SHAPES_LOB)
        monkeypatch.chdir(root)

        rc = cmd_check()

        assert rc == 1
        err = capsys.readouterr().err
        assert "ERROR" in err
        assert "<names>" in err
