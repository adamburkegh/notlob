"""The release build script (`build.py` at the repository root).

Building the artifact needs shiv and the network, so it is not run here;
what is tested is the logic that decides whether a ref may be built, and
that the repository's own version and changelog are consistent, which is
the state a missed version bump breaks.
"""

from __future__ import annotations

import doctest
import importlib.util
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def build_script():
    spec = importlib.util.spec_from_file_location(
        "notlob_build_script", ROOT / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _as_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


class TestReleasedVersions:
    def test_the_doctests_hold(self, build_script):
        assert doctest.testmod(build_script).failed == 0

    def test_an_undated_heading_is_not_a_release(self, build_script):
        text = "## [Unreleased]\n\n## [0.7.0]\n\n## [0.6.0] - 2026-10-22\n"
        assert build_script.released_versions(text) == ["0.6.0"]


class TestReleaseProblems:
    CHANGELOG = "## [Unreleased]\n\n## [0.6.0] - 2026-10-22\n"

    def test_a_released_untagged_version_is_buildable(self, build_script):
        assert build_script.release_problems(
            "0.6.0", self.CHANGELOG, "abc", None) == []

    def test_a_development_version_is_refused(self, build_script):
        problems = build_script.release_problems(
            "0.6.1", self.CHANGELOG, "abc", None)
        assert len(problems) == 1 and "no dated section for 0.6.1" in problems[0]

    def test_a_tag_elsewhere_is_refused(self, build_script):
        problems = build_script.release_problems(
            "0.6.0", self.CHANGELOG, "abc", "def")
        assert len(problems) == 1 and "v0.6.0 points at def" in problems[0]

    def test_both_problems_are_reported(self, build_script):
        assert len(build_script.release_problems(
            "0.6.1", self.CHANGELOG, "abc", "def")) == 2


class TestTheRepositoryItself:
    def _version(self) -> str:
        return tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]["version"]

    def _released(self, build_script) -> list[str]:
        return build_script.released_versions(
            (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))

    def test_released_versions_are_unique_and_newest_first(
        self, build_script,
    ):
        released = self._released(build_script)
        assert released
        keys = [_as_tuple(v) for v in released]
        assert keys == sorted(set(keys), reverse=True)

    def test_the_version_is_not_behind_the_latest_release(
        self, build_script,
    ):
        """A version older than a released one is a version that was
        never bumped forward after that release."""
        latest = self._released(build_script)[0]
        assert _as_tuple(self._version()) >= _as_tuple(latest)
