"""`notlob test` builds one graph, and reports a collision as it always has.

In a project the package graph is built once, before the modules are
tested; each module's references are validated against it and the closing
checks read it. A module whose names collide is reported as a document
error of its own, and the others are still tested.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import notlob.commands as commands
import notlob.project as project
from notlob.commands import cmd_test

_BINDING = "#One Graph\n\n---\n\n#Binding\n    ~language python\n"

_ALPHA = (
    "#Alpha\n\n    def double(x):\n        return x * 2\n\n"
    "~example\n    double(3) == 6\n"
)
_SHAPES = (
    "#Shapes\n\n    class Layout:\n        pass\n\n"
    "##Layout\n\nPlacing.\n\n    def place():\n        return Layout()\n\n"
    "~example\n    place() is not None\n\n"
    "---\n\n#References\n"
)
# Uses a function of the module that collides: with that module's symbols
# missing from the graph this import would look unused.
_CLIENT = (
    "#Client\n\n    def use():\n        return place()\n\n"
    "~example\n    use() is not None\n\n"
    "---\n\n#References\n    #Shapes\n    from shapes import place\n"
)


def _write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def counted(monkeypatch):
    """How often the graph is built: `build_package` calls, `build` calls
    made by the command itself, and `build` calls made for the package."""
    calls = {"package": 0, "command": 0, "module": 0}
    real_package = commands.build_package
    real_build = commands.build
    real_module = project.build

    def package(*args, **kwargs):
        calls["package"] += 1
        return real_package(*args, **kwargs)

    def command_build(*args, **kwargs):
        calls["command"] += 1
        return real_build(*args, **kwargs)

    def module_build(*args, **kwargs):
        calls["module"] += 1
        return real_module(*args, **kwargs)

    monkeypatch.setattr(commands, "build_package", package)
    monkeypatch.setattr(commands, "build", command_build)
    monkeypatch.setattr(project, "build", module_build)
    return calls


@pytest.fixture
def root(tmp_path, monkeypatch):
    _write(tmp_path, "binding.lob", _BINDING)
    _write(tmp_path, "alpha.lob", _ALPHA)
    _write(tmp_path, "beta.lob", _ALPHA.replace("Alpha", "Beta"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestOneGraphPerCommand:
    def test_a_whole_project_builds_the_package_once(self, root, counted):
        assert cmd_test(None) == 0
        assert counted["package"] == 1
        assert counted["command"] == 0
        assert counted["module"] == 3     # binding, alpha, beta: once each

    def test_one_file_in_a_project_builds_the_package_once(
        self, root, counted,
    ):
        assert cmd_test(root / "alpha.lob") == 0
        assert counted["package"] == 1
        assert counted["command"] == 0

    def test_a_file_with_no_project_builds_and_enriches_once(
        self, tmp_path, monkeypatch, counted,
    ):
        monkeypatch.chdir(tmp_path)
        path = _write(tmp_path, "alone.lob", _ALPHA.replace("Alpha", "Alone"))
        cmd_test(path)
        assert counted["package"] == 0
        assert counted["command"] == 1

    def test_json_mode_reads_the_same_graph_for_its_checks(
        self, root, counted, capsys,
    ):
        assert cmd_test(None, fmt="json") == 0
        assert counted["package"] == 1
        assert "checks" in json.loads(capsys.readouterr().out)


class TestARestatedHeading:
    """A heading written twice in one scope is reported as a collision by
    each command that builds a graph, not left to crash."""

    SOURCE = "#Notes\n\n##Same\n\nOne.\n\n##Same\n\nTwo.\n"

    def test_notlob_graph_on_a_file_alone(self, tmp_path, capsys):
        from notlob.commands import cmd_graph
        path = _write(tmp_path, "notes.lob", self.SOURCE)
        assert cmd_graph(path) == 1
        err = capsys.readouterr().err
        assert "<names>" in err and "notes#Same" in err

    def test_notlob_test_on_a_file_alone(self, tmp_path, capsys):
        path = _write(tmp_path, "notes.lob", self.SOURCE)
        assert cmd_test(path) == 1
        assert "<names>" in capsys.readouterr().err

    def test_notlob_test_in_a_project(self, root, capsys):
        _write(root, "notes.lob", self.SOURCE)
        assert cmd_test(None) == 1
        assert "notes#Same" in capsys.readouterr().err


class TestACollision:
    @pytest.fixture
    def shapes(self, root):
        _write(root, "shapes.lob", _SHAPES)
        _write(root, "client.lob", _CLIENT)
        return root

    def test_the_package_is_still_built_once(self, shapes, counted):
        cmd_test(None)
        assert counted["package"] == 1
        assert counted["command"] == 0

    def test_it_is_that_modules_document_error(self, shapes, capsys):
        assert cmd_test(None) == 1
        err = capsys.readouterr().err
        assert "<names>" in err and "shapes#Layout" in err

    def test_the_other_modules_still_run_their_claims(self, shapes, capsys):
        cmd_test(None)
        out = capsys.readouterr().out
        assert "alpha#example#1" in out
        assert "beta#example#1" in out

    def test_the_colliding_module_runs_none_of_its_claims(
        self, shapes, capsys,
    ):
        cmd_test(None)
        assert "shapes#example#1" not in capsys.readouterr().out

    def test_the_closing_checks_report_the_collision_and_nothing_else(
        self, shapes, capsys,
    ):
        """On a graph without that module's symbols, `client`'s import
        would look unused; the collision is the one finding."""
        cmd_test(None, fmt="json")
        checks = json.loads(capsys.readouterr().out)["checks"]
        assert [(f["check"], f["severity"]) for f in checks] == [
            ("names", "error")]

    def test_the_closing_checks_report_it_in_text_too(self, shapes, capsys):
        cmd_test(None)
        captured = capsys.readouterr()
        assert captured.err.count("<names>") == 2   # the module's, the check
        assert "[imports]" not in captured.out

    def test_one_file_in_a_project_with_a_collision_elsewhere(
        self, shapes, capsys,
    ):
        """Only the module being tested matters to its own run."""
        assert cmd_test(shapes / "alpha.lob") == 0
        assert "alpha#example#1" in capsys.readouterr().out

    def test_the_colliding_file_alone_is_reported(self, shapes, capsys):
        assert cmd_test(shapes / "shapes.lob") == 1
        assert "<names>" in capsys.readouterr().err
