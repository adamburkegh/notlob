"""Tests for notlob.bindings.python.loader — ModuleCache."""

from pathlib import Path

import pytest

from notlob.bindings.python.loader import CircularImportError, ModuleCache


# ── Fixtures ──────────────────────────────────────────────────

_BINDING = """\
#Test Project

---

#Binding
    ~language python
"""


def _write(tmp_path: Path, name: str, content: str) -> Path:
    """Write a .lob file under tmp_path and return its path."""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _setup(tmp_path: Path) -> ModuleCache:
    """Write a binding.lob and return a ModuleCache rooted at tmp_path."""
    _write(tmp_path, "binding.lob", _BINDING)
    return ModuleCache(tmp_path)


# ── Basic load ────────────────────────────────────────────────

class TestBasicLoad:
    def test_load_returns_namespace(self, tmp_path):
        _write(tmp_path, "greet.lob", (
            "#Greet\n"
            "\n"
            "    def hello():\n"
            "        return 'hi'\n"
        ))
        cache = _setup(tmp_path)
        ns = cache.load("greet")
        assert "hello" in ns
        assert ns["hello"]() == "hi"

    def test_references_available_in_namespace(self, tmp_path):
        _write(tmp_path, "nums.lob", (
            "#Nums\n"
            "\n"
            "    VALUE = Decimal('42')\n"
            "\n"
            "---\n"
            "\n"
            "#References\n"
            "    from decimal import Decimal\n"
        ))
        cache = _setup(tmp_path)
        ns = cache.load("nums")
        from decimal import Decimal
        assert ns["VALUE"] == Decimal("42")

    def test_file_not_found_raises(self, tmp_path):
        cache = _setup(tmp_path)
        with pytest.raises(FileNotFoundError):
            cache.load("nonexistent/module")


# ── Caching ───────────────────────────────────────────────────

class TestCaching:
    def test_second_load_returns_same_object(self, tmp_path):
        _write(tmp_path, "simple.lob", "#Simple\n\n    x = 1\n")
        cache = _setup(tmp_path)
        ns1 = cache.load("simple")
        ns2 = cache.load("simple")
        assert ns1 is ns2

    def test_module_code_runs_only_once(self, tmp_path):
        # A module with a side-effecting counter; if loaded twice the
        # count would be 2.  Cache means it stays at 1.
        _write(tmp_path, "counter.lob", (
            "#Counter\n"
            "\n"
            "    _calls = _calls + 1 if '_calls' in dir() else 1\n"
            "    CALLS = _calls\n"
        ))
        cache = _setup(tmp_path)
        ns = cache.load("counter")
        cache.load("counter")          # second call — should hit cache
        assert ns["CALLS"] == 1


# ── Dependency loading ────────────────────────────────────────

class TestDependencyLoad:
    def test_importing_module_sees_dep_names(self, tmp_path):
        # "#Math Utils" → address "math/utils" → math/utils.lob
        _write(tmp_path, "math/utils.lob", (
            "#Math Utils\n"
            "\n"
            "    def double(n):\n"
            "        return n * 2\n"
        ))
        _write(tmp_path, "app.lob", (
            "#App\n"
            "\n"
            "    RESULT = double(21)\n"
            "\n"
            "---\n"
            "\n"
            "#References\n"
            "    #Math Utils\n"
        ))
        cache = _setup(tmp_path)
        ns = cache.load("app")
        assert ns["RESULT"] == 42

    def test_dep_is_cached_after_transitive_load(self, tmp_path):
        _write(tmp_path, "base.lob", "#Base\n\n    BASE = 1\n")
        _write(tmp_path, "mid.lob", (
            "#Mid\n"
            "\n"
            "    MID = BASE + 1\n"
            "\n"
            "---\n"
            "\n"
            "#References\n"
            "    #Base\n"
        ))
        _write(tmp_path, "top.lob", (
            "#Top\n"
            "\n"
            "    TOP = MID + 1\n"
            "\n"
            "---\n"
            "\n"
            "#References\n"
            "    #Mid\n"
        ))
        cache = _setup(tmp_path)
        ns = cache.load("top")
        assert ns["TOP"] == 3
        # Base and Mid should now be cached
        assert "base" in cache._cache
        assert "mid" in cache._cache

    def test_shared_dep_loaded_once(self, tmp_path):
        """Z imported by both X and Y runs only once."""
        _write(tmp_path, "shared.lob", (
            "#Shared\n"
            "\n"
            "    SHARED = 99\n"
        ))
        _write(tmp_path, "left.lob", (
            "#Left\n"
            "\n"
            "    LEFT = SHARED + 1\n"
            "\n"
            "---\n"
            "\n"
            "#References\n"
            "    #Shared\n"
        ))
        _write(tmp_path, "right.lob", (
            "#Right\n"
            "\n"
            "    RIGHT = SHARED + 2\n"
            "\n"
            "---\n"
            "\n"
            "#References\n"
            "    #Shared\n"
        ))
        cache = _setup(tmp_path)
        left_ns  = cache.load("left")
        right_ns = cache.load("right")
        # Shared module's namespace is the same object in both
        assert cache._cache["shared"] is cache._cache["shared"]
        assert left_ns["LEFT"]  == 100
        assert right_ns["RIGHT"] == 101


# ── Circular import detection ─────────────────────────────────

class TestCircularDetection:
    def test_direct_cycle_raises(self, tmp_path):
        _write(tmp_path, "a.lob", (
            "#A\n"
            "\n"
            "    A = 1\n"
            "\n"
            "---\n"
            "\n"
            "#References\n"
            "    #B\n"
        ))
        _write(tmp_path, "b.lob", (
            "#B\n"
            "\n"
            "    B = 2\n"
            "\n"
            "---\n"
            "\n"
            "#References\n"
            "    #A\n"
        ))
        cache = _setup(tmp_path)
        with pytest.raises(CircularImportError):
            cache.load("a")

    def test_indirect_cycle_raises(self, tmp_path):
        _write(tmp_path, "x.lob", (
            "#X\n\n    X = 1\n\n---\n\n#References\n    #Y\n"
        ))
        _write(tmp_path, "y.lob", (
            "#Y\n\n    Y = 2\n\n---\n\n#References\n    #Z\n"
        ))
        _write(tmp_path, "z.lob", (
            "#Z\n\n    Z = 3\n\n---\n\n#References\n    #X\n"
        ))
        cache = _setup(tmp_path)
        with pytest.raises(CircularImportError):
            cache.load("x")

    def test_building_set_cleared_after_error(self, tmp_path):
        """_building should be clean after a failed load."""
        _write(tmp_path, "bad.lob", (
            "#Bad\n\n---\n\n#References\n    #nonexistent\n"
        ))
        cache = _setup(tmp_path)
        with pytest.raises(FileNotFoundError):
            cache.load("bad")
        assert "bad" not in cache._building
