"""The ``~on-build`` hook manifest: the JSON a hook script is given.

A hook script is code written against this document (pn-chomper's
``inject-bundle.ts`` reads ``entry_points`` and ``externals``), so it is
structured output meant for a program and has a schema:
``notlob/schema/build_manifest.json``. These tests run a real hook that
saves the manifest it receives, and validate that.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from notlob.commands import cmd_build

SCHEMA = (
    Path(__file__).parent.parent / "notlob" / "schema" / "build_manifest.json"
)

_BINDING = (
    "#Hook Repro\n\n---\n\n"
    "#Binding\n"
    "    ~language python\n"
    "    ~external index.html.tmpl\n"
    "    ~on-build hook.py\n"
)

# Saves the manifest it is handed, next to itself.
_HOOK = (
    "import shutil, sys\n"
    "from pathlib import Path\n"
    "shutil.copy(sys.argv[1], Path(__file__).parent / 'manifest_copy.json')\n"
)

_APP = (
    "#App\n\nThe program.\n\n"
    "    def main():\n        return 1\n\n"
    "~run\n    print(main())\n"
)
_LIB = "#Lib\n\nA library.\n\n    def helper():\n        return 1\n"


def _write(root: Path, name: str, content: str) -> Path:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def project(tmp_path, monkeypatch):
    _write(tmp_path, "binding.lob", _BINDING)
    _write(tmp_path, "hook.py", _HOOK)
    _write(tmp_path, "index.html.tmpl", "<html></html>\n")
    _write(tmp_path, "app.lob", _APP)
    _write(tmp_path, "lib.lob", _LIB)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _manifest(root: Path) -> dict:
    return json.loads(
        (root / "manifest_copy.json").read_text(encoding="utf-8")
    )


class TestWholeProjectBuild:
    def test_manifest_conforms_to_the_schema(self, project):
        cmd_build(None, output_dir=project / "out", skip_tests=True)
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        jsonschema.validate(_manifest(project), schema)

    def test_contents(self, project):
        cmd_build(None, output_dir=project / "out", skip_tests=True)
        m = _manifest(project)
        assert m["version"] == 1
        assert m["language"] == "python"
        assert sorted(Path(a).name for a in m["artifacts"]) == [
            "app.py", "lib.py",
        ]
        assert [Path(e).name for e in m["entry_points"]] == ["app.py"]
        assert set(m["entry_points"]) <= set(m["artifacts"])
        assert [Path(e).name for e in m["externals"]] == ["index.html.tmpl"]
        assert Path(m["project_root"]) == project.resolve()
        assert Path(m["output_dir"]) == (project / "out").resolve()

    def test_all_paths_are_absolute(self, project):
        cmd_build(None, output_dir=project / "out", skip_tests=True)
        m = _manifest(project)
        paths = (m["artifacts"] + m["entry_points"] + m["externals"]
                 + [m["project_root"], m["output_dir"]])
        assert all(Path(p).is_absolute() for p in paths)


class TestSingleFileBuild:
    """A single-module build gets the same document, listing only that
    module (meta/bugs/2026-10-03-on-build-single-file-build)."""

    def test_manifest_conforms_to_the_schema(self, project):
        cmd_build(project / "lib.lob", output_dir=project / "out",
                  skip_tests=True)
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        jsonschema.validate(_manifest(project), schema)

    def test_lists_only_that_module(self, project):
        cmd_build(project / "lib.lob", output_dir=project / "out",
                  skip_tests=True)
        m = _manifest(project)
        assert [Path(a).name for a in m["artifacts"]] == ["lib.py"]
        assert m["entry_points"] == []


_TOOL = (
    "#Tool\n\nA tool.\n\n    def go():\n        return 1\n\n"
    "---\n\n#Appendix Entry\n\n~run\n    print(go())\n"
)


class TestEntryPoints:
    """A module is an entry point when its tree holds a `~run`, wherever
    in it that is written."""

    def test_a_run_in_an_appendix_makes_an_entry_point(self, project):
        _write(project, "tool.lob", _TOOL)
        cmd_build(None, output_dir=project / "out", skip_tests=True)
        m = _manifest(project)
        assert sorted(Path(e).name for e in m["entry_points"]) == [
            "app.py", "tool.py"]

    def test_a_single_module_with_a_run_in_an_appendix(self, project):
        path = _write(project, "tool.lob", _TOOL)
        cmd_build(path, output_dir=project / "out", skip_tests=True)
        m = _manifest(project)
        assert [Path(e).name for e in m["entry_points"]] == ["tool.py"]

    def test_a_run_in_a_subheading_still_makes_one(self, project):
        _write(project, "sub.lob",
               "#Sub\n\n##Start\n\n    def go():\n        return 1\n\n"
               "~run on-load\n    go()\n")
        cmd_build(None, output_dir=project / "out", skip_tests=True)
        m = _manifest(project)
        assert "sub.py" in [Path(e).name for e in m["entry_points"]]


class TestOneGraphPerBuild:
    def test_a_project_build_makes_the_package_graph_once(
        self, project, monkeypatch,
    ):
        import notlob.commands as commands
        calls = []
        real = commands.build_package

        def counting(*args, **kwargs):
            calls.append(args[0])
            return real(*args, **kwargs)

        monkeypatch.setattr(commands, "build_package", counting)
        cmd_build(None, output_dir=project / "out", skip_tests=True)
        assert len(calls) == 1


_SHAPES = (
    "#Shapes\n\n    class Layout:\n        pass\n\n"
    "##Layout\n\nPlacing.\n\n    def place():\n        return Layout()\n"
)
_NOTES = "#Notes\n\n##Same\n\nOne.\n\n##Same\n\nTwo.\n\n    x = 1\n"


class TestACollision:
    """A module whose names collide is not built: it is reported, counted
    as a failure, and leaves no artifact."""

    def test_a_single_module(self, project, capsys):
        path = _write(project, "shapes.lob", _SHAPES)
        rc = cmd_build(path, output_dir=project / "out", skip_tests=True)
        assert rc == 1
        assert "<names>" in capsys.readouterr().err
        assert not (project / "out" / "shapes.py").exists()

    def test_a_single_module_with_a_restated_heading(self, project, capsys):
        path = _write(project, "notes.lob", _NOTES)
        rc = cmd_build(path, output_dir=project / "out", skip_tests=True)
        assert rc == 1
        assert "notes#Same" in capsys.readouterr().err
        assert not (project / "out" / "notes.py").exists()

    def test_a_single_module_with_no_project(self, tmp_path, capsys):
        path = _write(tmp_path, "shapes.lob", _SHAPES)
        rc = cmd_build(path, output_dir=tmp_path / "out", skip_tests=True)
        assert rc == 1
        assert "<names>" in capsys.readouterr().err
        assert not (tmp_path / "out" / "shapes.py").exists()

    def test_a_whole_project(self, project, capsys):
        _write(project, "shapes.lob", _SHAPES)
        rc = cmd_build(None, output_dir=project / "out", skip_tests=True)
        assert rc == 1
        assert "<names>" in capsys.readouterr().err
        assert not (project / "out" / "shapes.py").exists()

    def test_a_whole_project_after_its_tests(self, project, capsys):
        _write(project, "shapes.lob", _SHAPES)
        rc = cmd_build(None, output_dir=project / "out")
        assert rc == 1
        assert "<names>" in capsys.readouterr().err
        assert not (project / "out" / "shapes.py").exists()


class TestSchema:
    def test_schema_is_valid_json_schema(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        jsonschema.Draft7Validator.check_schema(schema)

    def test_schema_requires_a_version(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        assert "version" in schema["required"]

    def test_schema_rejects_a_missing_field(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"version": 1}, schema)
