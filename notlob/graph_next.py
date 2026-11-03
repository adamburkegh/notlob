"""The graph of a project as the target writes it, until ``notlob graph``
does: ``python -c "from notlob.graph_next import main; main()" ROOT FORMAT
LEVEL``. It builds the project's graph as ``notlob graph`` does, takes the
view of the named level and writes it, in ``json``, ``turtle`` or ``text``.

The swap deletes this module, and ``notlob graph`` writes the same.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .commands import _find_binding, _get_binding_kit
from .project import build_package
from .view import level_view
from .writers import write_json, write_text, write_turtle

WRITERS = {"json": write_json, "turtle": write_turtle, "text": write_text}


def main(argv: list[str] | None = None) -> None:
    """Write the view of the project at ROOT in FORMAT at LEVEL to stdout,
    as UTF-8."""
    root, fmt, level = (sys.argv[1:] if argv is None else argv)
    root = Path(root)
    kit, extract_symbols = _get_binding_kit(
        _find_binding(root / "binding.lob").get("language"))
    graph = build_package(
        root, extract_symbols, call_extractor=kit.extract_calls,
        split_imports=kit.split_imports)
    text = WRITERS[fmt](level_view(graph, level))
    sys.stdout.buffer.write(text.encode("utf-8"))
    if not text.endswith("\n"):
        sys.stdout.buffer.write(b"\n")
