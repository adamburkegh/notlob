"""End-to-end proof that Python claims resolve names from the right
place: the target project's own environment for its own third-party
imports, and notlob's own install for pytest/hypothesis specifically
-- even when the target environment has neither.

This is the actual bug report the subprocess rewrite exists to fix
(a module importing a library only installed in the target project's
venv failed with ModuleNotFoundError, because claims used to exec()
inside notlob's own process) verified against a real, freshly created
venv rather than just reasoned about -- these tests are slower than
the rest of the suite (each spawns `python -m venv`) but the whole
point is that this needs to be true against a real second interpreter,
not just against notlob's own.
"""

from __future__ import annotations

import subprocess
import sys
import venv
from pathlib import Path

import pytest

from notlob import from_tree, parse_file


def _bin_dir(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts" if sys.platform == "win32" else "bin")


@pytest.fixture(scope="module")
def target_venv(tmp_path_factory) -> Path:
    """A real, isolated venv with a fake third-party package installed
    and neither pytest nor hypothesis -- module-scoped since creating
    a venv is the slow part and none of these tests mutate it."""
    venv_dir = tmp_path_factory.mktemp("target_venv_root") / "venv"
    venv.create(venv_dir, with_pip=False)
    site_packages = next(_bin_dir(venv_dir).parent.glob("Lib/site-packages")) \
        if sys.platform == "win32" \
        else next((venv_dir).glob("lib/python*/site-packages"))
    (site_packages / "fake_third_party.py").write_text(
        'GREETING = "hello from target venv"\n', encoding="utf-8",
    )
    return venv_dir


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "binding.lob").write_text(
        "#Scratch\n\n---\n\n#Binding\n    ~language python\n",
        encoding="utf-8",
    )
    (tmp_path / "thing.lob").write_text(
        "#Thing\n\n"
        "    import fake_third_party\n\n"
        "    def double(n):\n"
        "        return n * 2\n\n"
        "~example\n"
        '    fake_third_party.GREETING == "hello from target venv"\n\n'
        "~property\n"
        "    @given(n=st.integers())\n"
        "    def _(n):\n"
        "        assert double(n) == n + n\n\n"
        "---\n\n"
        "#Tests\n"
        '    fake_third_party.GREETING == "hello from target venv"\n'
        "    double(3) == approx(6.0)\n",
        encoding="utf-8",
    )
    return tmp_path / "thing.lob"


def _run_with_target_venv_on_path(target_venv: Path, func, *args, **kwargs):
    """Run *func* with only *target_venv*'s bin/Scripts directory
    prepended to PATH -- notlob's own interpreter is never on PATH
    here, simulating notlob installed as an isolated external tool
    (pipx) pointed at a project it shares no environment with."""
    import os
    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = str(_bin_dir(target_venv)) + os.pathsep + old_path
    try:
        return func(*args, **kwargs)
    finally:
        os.environ["PATH"] = old_path


class TestThirdPartyAndNotlobToolingBothResolve:
    def test_example_resolves_target_third_party_import(
        self, target_venv, project,
    ):
        from notlob.bindings.python.runner import Status, run_examples
        module = from_tree(parse_file(project))
        results = _run_with_target_venv_on_path(
            target_venv, run_examples, module, file_path=project,
        )
        assert len(results) == 1
        assert results[0].status == Status.PASS

    def test_property_resolves_hypothesis_from_notlob(
        self, target_venv, project,
    ):
        from notlob.bindings.python.runner import Status, run_properties
        module = from_tree(parse_file(project))
        results = _run_with_target_venv_on_path(
            target_venv, run_properties, module, file_path=project,
        )
        assert len(results) == 1
        assert results[0].status == Status.PASS

    def test_tests_section_resolves_both_simultaneously(
        self, target_venv, project,
    ):
        from notlob.bindings.python.runner import Status, run_tests
        module = from_tree(parse_file(project))
        results = _run_with_target_venv_on_path(
            target_venv, run_tests, module, file_path=project,
        )
        assert len(results) == 2
        assert all(r.status == Status.PASS for r in results), results

    def test_target_venv_genuinely_lacks_pytest_and_hypothesis(
        self, target_venv,
    ):
        # Sanity check on the fixture itself -- if this ever starts
        # failing, the other tests in this class would be proving
        # nothing.
        python = _bin_dir(target_venv) / (
            "python.exe" if sys.platform == "win32" else "python"
        )
        for pkg in ("pytest", "hypothesis"):
            proc = subprocess.run(
                [str(python), "-c", f"import {pkg}"],
                capture_output=True, text=True,
            )
            assert proc.returncode != 0, (
                f"expected target venv to lack {pkg}, but it imported "
                f"successfully -- fixture no longer proves what it claims to"
            )
