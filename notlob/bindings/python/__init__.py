"""notlob.bindings.python — Python binding kit.

Assembles the Python BindingKit from its component submodules and
exposes `kit` as the canonical Python binding instance.

Usage::

    from notlob.bindings.python import kit, extract_symbols
    enrich(graph, module, kit.extract_symbols)
"""

from notlob.bindings import BindingKit
from notlob.bindings.python.symbols import extract_symbols

#: The assembled Python binding kit.
kit = BindingKit(extract_symbols=extract_symbols)

__all__ = ["kit", "extract_symbols"]
