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
