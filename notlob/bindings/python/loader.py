"""notlob.bindings.python.loader — Module cache for cross-file imports.

When a ``.lob`` module declares lob references in its ``#References``
section (e.g. ``#Roman Numerals``), the claim runner needs those
modules' code to be available in the execution namespace before the
importing module is exec'd.

``ModuleCache`` handles this: given a project root it resolves module
addresses to ``.lob`` files, assembles and exec's them in dependency
order, and caches each result so a shared dependency (imported by two
or more modules) runs exactly once.

Usage::

    from pathlib import Path
    from notlob.project import find_project_root
    from notlob.bindings.python.loader import ModuleCache

    root = find_project_root(path)
    cache = ModuleCache(root)
    ns = cache.load("roman/numerals")
    assert "to_roman" in ns
"""

from __future__ import annotations

from pathlib import Path

from notlob import from_tree, parse_file
from notlob.bindings.python.assemble import assemble
from notlob.project import module_lob_refs, resolve_module_path


class CircularImportError(Exception):
    """Raised when a circular lob module import is detected.

    e.g. module A references B, which references A.
    """


class ModuleCache:
    """Exec-chain module loader with shared-namespace caching.

    Each module address is loaded at most once per cache instance.
    Dependencies are loaded and merged into the namespace before the
    importing module's own code runs — so a module can use names from
    its lob imports without qualification.

    Parameters
    ----------
    root:
        The project root directory (parent of ``binding.lob``).
    """

    def __init__(self, root: Path) -> None:
        self._root    = root
        self.root     = root   # public alias for language bindings
        self._cache:    dict[str, dict] = {}
        self._building: set[str]        = set()

    def load(self, address: str) -> dict:
        """Return the exec'd namespace for *address*, loading if needed.

        Raises
        ------
        CircularImportError
            If *address* is already being loaded (cycle detected).
        FileNotFoundError
            If the resolved ``.lob`` path does not exist.
        Exception
            Any error raised during assembly or exec propagates as-is.
        """
        if address in self._cache:
            return self._cache[address]

        if address in self._building:
            raise CircularImportError(
                f"Circular import detected: {address!r} is already "
                f"being loaded. Import chain: "
                f"{' -> '.join(sorted(self._building))} -> {address}"
            )

        self._building.add(address)
        try:
            path   = resolve_module_path(address, self._root)
            module = from_tree(parse_file(path))

            ns: dict = {"__file__": str(path.resolve())}

            # ── Exec-chain: dependencies run before this module ──
            for dep_addr in module_lob_refs(module):
                dep_ns = self.load(dep_addr)
                ns.update(dep_ns)

            exec(assemble(module), ns)

            self._cache[address] = ns
            return ns

        finally:
            self._building.discard(address)


