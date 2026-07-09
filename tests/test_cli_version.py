"""Tests for notlob's top-level --version flag.

Previously unsupported -- `notlob --version` failed with "unrecognized
arguments" because no top-level flag was wired into the argparse
parser, even though notlob.__version__ already existed.
"""

import sys

import pytest

from notlob import __version__
from notlob.cli import main


def _run(args, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["notlob"] + args)
    main()


class TestVersionFlag:
    def test_version_prints_and_exits_zero(self, monkeypatch, capsys):
        with pytest.raises(SystemExit) as exc:
            _run(["--version"], monkeypatch)
        assert exc.value.code == 0

    def test_version_output_contains_version_string(self, monkeypatch, capsys):
        with pytest.raises(SystemExit):
            _run(["--version"], monkeypatch)
        out = capsys.readouterr().out
        assert __version__ in out

    def test_version_output_contains_prog_name(self, monkeypatch, capsys):
        with pytest.raises(SystemExit):
            _run(["--version"], monkeypatch)
        out = capsys.readouterr().out
        assert out.startswith("notlob ")

    def test_help_lists_version_flag(self, monkeypatch, capsys):
        with pytest.raises(SystemExit):
            _run(["--help"], monkeypatch)
        out = capsys.readouterr().out
        assert "--version" in out
