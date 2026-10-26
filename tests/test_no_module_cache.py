"""notlob loads no modules in a cache of its own.

notlob works out which modules a module's code needs from the package
graph (`project.load_order`) and hands them to a binding as `deps`. The
in-process `ModuleCache` loaded nothing anyone used, and the runners'
`cache=` keyword existed for it: a runner takes the project `root`
instead, as `lint` does.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import notlob
from notlob.bindings import BindingKit
from notlob.bindings.haskell import kit as haskell_kit
from notlob.bindings.python import kit as python_kit
from notlob.bindings.typescript import kit as typescript_kit

PACKAGE = Path(notlob.__file__).parent


def _sources():
    return sorted(PACKAGE.rglob("*.py"))


class TestTheCacheIsGone:
    def test_the_loader_module_is_gone(self):
        assert not (PACKAGE / "bindings" / "python" / "loader.py").exists()

    @pytest.mark.parametrize("path", _sources(), ids=lambda p: p.name)
    def test_no_module_mentions_it(self, path):
        text = path.read_text(encoding="utf-8")
        assert "ModuleCache" not in text
        assert "CircularImportError" not in text
        assert "cache=" not in text
        assert "python.loader" not in text


@pytest.mark.parametrize("kit", [python_kit, haskell_kit, typescript_kit],
                         ids=["python", "haskell", "typescript"])
class TestARunnerTakesTheRoot:
    def test_each_takes_keyword_root_and_no_cache(self, kit):
        for function in (kit.run_examples, kit.run_tests,
                         kit.run_properties):
            parameters = inspect.signature(function).parameters
            assert "cache" not in parameters
            root = parameters["root"]
            assert root.default is None
            assert root.kind == inspect.Parameter.KEYWORD_ONLY


def test_the_kit_documents_root_beside_claims_and_deps():
    assert "``root``" in BindingKit.__doc__
