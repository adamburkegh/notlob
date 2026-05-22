"""notlob.project — Project-level utilities.

A notlob project is rooted at the directory containing ``binding.lob``.
This module provides the tools for locating the project root, resolving
module addresses to filesystem paths, and parsing the two kinds of line
that can appear in a ``#References`` section: lob module references and
Python import statements.

Lob module references use the ``#Title`` syntax — the same ``#``
dereference operator used in prose::

    #References
        #Roman Numerals
        from decimal import Decimal

Lines whose stripped content starts with ``#`` are lob module references;
all other non-blank lines are Python imports.
"""

from __future__ import annotations

from pathlib import Path

from .graph import module_address
from .model import Module, ReferencesSection


def find_project_root(path: Path) -> Path | None:
    """Walk up from *path* to find the nearest ``binding.lob``.

    If *path* is a directory it is checked first, then its ancestors.
    If *path* is a file, the search starts from its parent directory.

    Returns the directory containing ``binding.lob``, or ``None`` if no
    ``binding.lob`` is found before the filesystem root.
    """
    resolved = path.resolve()
    candidates = (
        [resolved, *resolved.parents]
        if resolved.is_dir()
        else resolved.parents
    )
    for d in candidates:
        if (d / "binding.lob").exists():
            return d
    return None


def resolve_module_path(address: str, root: Path) -> Path:
    """Translate a module address to a ``.lob`` filesystem path.

    ``"roman/numerals"`` under *root* → ``root/roman/numerals.lob``.
    """
    return root / Path(address).with_suffix(".lob")


def parse_lob_refs(lines: list[str]) -> list[str]:
    """Return module addresses declared in a ``#References`` line list.

    A lob reference line is one whose stripped content starts with ``#``,
    e.g. ``    #Roman Numerals``.  The label after ``#`` is converted to
    a module address via :func:`notlob.graph.module_address`.

    Lines that are blank or start with anything other than ``#`` are
    ignored (they are Python imports, handled by
    :func:`parse_python_imports`).
    """
    refs = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            label = stripped[1:].strip()
            if label:
                refs.append(module_address(label))
    return refs


def parse_python_imports(lines: list[str]) -> list[str]:
    """Return the Python import lines from a ``#References`` line list.

    This is the complement of :func:`parse_lob_refs`: every line whose
    stripped content does *not* start with ``#``.  Blank lines are
    preserved so that dedent/strip in the assembler works as before.
    """
    return [line for line in lines if not line.strip().startswith("#")]


def module_lob_refs(module: Module) -> list[str]:
    """Return lob module addresses declared in *module*'s ``#References``.

    Convenience wrapper around :func:`parse_lob_refs` that locates the
    ``ReferencesSection`` in the module's post-text.  Returns an empty
    list if the module has no post-text or no ``#References`` section.
    """
    if module.post_text is None:
        return []
    for section in module.post_text.sections:
        if isinstance(section, ReferencesSection):
            return parse_lob_refs(section.lines)
    return []
