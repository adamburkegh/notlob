"""Build the release artifact: ``dist/notlob-<version>.pyz``.

    python build.py                  # build HEAD
    python build.py --ref v0.6.0     # build a tag (or any commit)

The same ref gives the same artifact. It is built from ``git archive <ref>``,
not from the working tree, so stale ``build/`` directories, ``notlobenv/``,
uncommitted edits and untracked files cannot get in (and a file the package
needs but git does not track fails here, not in a user's install). Entries are
timestamped with the commit time (``SOURCE_DATE_EPOCH``), so the bytes do not
depend on when it was built.

It refuses to build a version that has no dated section in ``CHANGELOG.md``,
or a ref other than the one ``v<version>`` is tagged at, and smoke-tests the
artifact it made (version, the documentation and schemas it ships, a real
``notlob test`` with a ``~example`` and a ``~property``), because each of
those has been wrong in a published install before.

It does not tag, push or publish. It prints the checksum and the commands.

Needs ``shiv``, which is in the ``dev`` extra (``pip install -e ".[dev]"``),
in the interpreter that runs this, and ``git`` on PATH. Standard library
otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# `## [0.6.0] - 2026-10-22` (a released section), not `## [Unreleased]`.
_RELEASED = re.compile(
    r"^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)


def released_versions(changelog: str) -> list[str]:
    """The versions that have a dated section in *changelog*, newest first.

    >>> released_versions("## [Unreleased]\\n\\n## [0.6.0] - 2026-10-22\\n"
    ...                   "## [0.5.4] - 2026-08-27\\n")
    ['0.6.0', '0.5.4']
    >>> released_versions("## [Unreleased]\\n\\n## [0.6.0]\\n")
    []
    """
    return [m.group(1) for m in _RELEASED.finditer(changelog)]


def release_problems(
    version: str, changelog: str, ref_sha: str, tag_sha: str | None,
) -> list[str]:
    """Reasons *version* must not be built from the commit *ref_sha*.

    *tag_sha* is the commit ``v<version>`` points at, or None if there is no
    such tag yet (which is fine: the tag is made after building).

    >>> release_problems("0.6.1", "## [0.6.0] - 2026-10-22\\n", "a", None)
    ['CHANGELOG.md has no dated section for 0.6.1 (latest: 0.6.0); is this a development version?']
    >>> release_problems("0.6.0", "## [0.6.0] - 2026-10-22\\n", "a", "b")
    ['tag v0.6.0 points at b, not at the ref being built (a)']
    >>> release_problems("0.6.0", "## [0.6.0] - 2026-10-22\\n", "a", "a")
    []
    """
    problems: list[str] = []
    released = released_versions(changelog)
    if version not in released:
        latest = released[0] if released else "none"
        problems.append(
            f"CHANGELOG.md has no dated section for {version} "
            f"(latest: {latest}); is this a development version?")
    if tag_sha is not None and tag_sha != ref_sha:
        problems.append(
            f"tag v{version} points at {tag_sha}, "
            f"not at the ref being built ({ref_sha})")
    return problems


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True,
        capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip()


def _tag_commit(version: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet",
         f"refs/tags/v{version}^{{commit}}"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _export(ref: str, into: Path) -> None:
    """Write the tracked files of *ref* into *into* (``git archive``)."""
    archive = into.parent / "source.zip"
    subprocess.run(
        ["git", "archive", "--format=zip", "-o", str(archive), ref],
        cwd=ROOT, check=True)
    with zipfile.ZipFile(archive) as z:
        z.extractall(into)
    archive.unlink()


def _shiv(source: Path, out: Path, epoch: str) -> None:
    """Bundle *source* and its dependencies into the zipapp *out*.

    ``-p`` fixes the shebang: shiv's default is the path of the interpreter
    running this script, which means nothing on another machine.
    """
    try:
        import shiv  # noqa: F401
    except ImportError:
        sys.exit("shiv is not installed in this interpreter; it is in the "
                 'dev extra: pip install -e ".[dev]"')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    subprocess.run(
        [sys.executable, "-m", "shiv",
         "-e", "notlob.cli:main",
         "-p", "/usr/bin/env python3",
         "-o", str(out),
         str(source)],
        check=True,
        env={**os.environ, "SOURCE_DATE_EPOCH": epoch},
    )


# ── Smoke tests of the artifact ───────────────────────────────

_EXPECTED_DOCS = (
    "LANGUAGE.md", "DESIGN.md", "USER-AGENTS.md", "grammar.lark",
    "BINDING-python.md", "BINDING-haskell.md", "BINDING-typescript.md",
    "schema/test_result.json", "schema/check_result.json",
    "schema/name_graph.json", "schema/notlob.ttl",
)

_PROJECT = {
    "binding.lob": "#Smoke\n\n---\n\n#Binding\n    ~language python\n",
    "double.lob": (
        "#Double\n\nDoubles a number.\n\n"
        "    def double(n: int) -> int:\n        return n * 2\n\n"
        "~example\n    double(2) == 4\n\n"
        "~property\n"
        "    @given(n=st.integers(min_value=-5, max_value=5))\n"
        "    def _(n):\n        assert double(n) == n + n\n"
    ),
}


def _run(pyz: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(pyz), *args], cwd=cwd,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def smoke_test(pyz: Path, version: str) -> list[str]:
    """Run the artifact; return what is wrong with it (empty if nothing)."""
    pyz = pyz.resolve()        # it is run from temporary directories
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)

        shown = _run(pyz, work, "--version")
        if shown.stdout.strip() != f"notlob {version}":
            problems.append(
                f"--version says {shown.stdout.strip()!r}, "
                f"expected 'notlob {version}'")

        docs = _run(pyz, work, "docs", "--full")
        if docs.returncode != 0:
            problems.append(f"`docs --full` failed: {docs.stderr.strip()}")
        for name in _EXPECTED_DOCS:
            if not (work / "notlob-docs" / name).is_file():
                problems.append(f"`docs --full` did not write {name}")

        project = work / "smoke"
        project.mkdir()
        for name, text in _PROJECT.items():
            (project / name).write_text(text, encoding="utf-8")
        tested = _run(pyz, project, "test")
        if tested.returncode != 0 or "2 passed" not in tested.stdout:
            problems.append(
                "`test` on a project with an ~example and a ~property "
                f"failed:\n{tested.stdout}{tested.stderr}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build dist/notlob-<version>.pyz from a git ref.")
    parser.add_argument("--ref", default="HEAD",
                        help="commit, tag or branch to build (default HEAD)")
    parser.add_argument("--out", type=Path, default=ROOT / "dist",
                        help="output directory (default ./dist)")
    parser.add_argument("--no-smoke", action="store_true",
                        help="skip the tests of the finished artifact")
    args = parser.parse_args(argv)

    ref_sha = _git("rev-parse", "--verify", f"{args.ref}^{{commit}}")
    epoch = _git("log", "-1", "--format=%ct", ref_sha)
    if _git("status", "--porcelain"):
        print(f"NOTE     the working tree has uncommitted changes; they are "
              f"not in this build, which is {args.ref} ({ref_sha[:9]}).",
              file=sys.stderr)

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source"
        source.mkdir()
        _export(ref_sha, source)

        version = tomllib.loads(
            (source / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]["version"]
        changelog = (source / "CHANGELOG.md").read_text(encoding="utf-8")
        problems = release_problems(
            version, changelog, ref_sha, _tag_commit(version))
        if problems:
            print(f"REFUSED  {args.ref} ({ref_sha[:9]}), version {version}:",
                  file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 1

        out = args.out / f"notlob-{version}.pyz"
        _shiv(source, out, epoch)

    if not args.no_smoke:
        problems = smoke_test(out, version)
        if problems:
            print(f"SMOKE FAILED  {out}", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 1

    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"BUILT   {out}  ({out.stat().st_size:,} bytes)")
    print(f"SHA256  {digest}")
    print(f"COMMIT  {ref_sha}")
    if _tag_commit(version) is None:
        print(f"\nNot tagged yet. When you are happy with it:\n"
              f"  git tag v{version} {ref_sha[:9]}\n  git push origin "
              f"v{version}")
    print(f"\nPublish (not done here): attach {out.name} to the "
          f"v{version} release on GitHub.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
