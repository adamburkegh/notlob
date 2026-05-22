"""notlob.bindings.python — Python binding kit.

Assembles the Python BindingKit from its component submodules and
exposes `kit` as the canonical Python binding instance.

Usage::

    from notlob.bindings.python import kit
    enrich(graph, module, kit.extract_symbols)
    source = kit.assemble(module)
    results = kit.run_examples(module, file_path=path)
"""

from notlob.bindings import BindingKit
from notlob.bindings.python.assemble import assemble
from notlob.bindings.python.runner import (
    ClaimResult, Status, run_examples, run_tests, run_properties,
)
from notlob.bindings.python.symbols import extract_symbols

#: The assembled Python binding kit.
kit = BindingKit(
    extract_symbols=extract_symbols,
    assemble=assemble,
    run_examples=run_examples,
    run_properties=run_properties,
    run_tests=run_tests,
)

__all__ = [
    "kit", "extract_symbols", "assemble",
    "run_examples", "run_tests", "run_properties", "ClaimResult", "Status",
]
