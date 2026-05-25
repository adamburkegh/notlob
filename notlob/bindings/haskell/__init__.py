"""notlob.bindings.haskell — Haskell language binding kit.

Assembles the Haskell ``BindingKit`` from its submodules and exposes
``kit`` as the canonical Haskell binding instance.

Usage::

    from notlob.bindings.haskell import kit
    results = kit.run_examples(module, file_path=path)

Runner availability
-------------------
The runner requires ``runghc`` on PATH or the Stack build tool
(``stack`` on PATH).  When neither is available, ``run_examples``,
``run_tests``, and ``run_properties`` return a single ERROR result
rather than raising.
"""

from notlob.bindings import BindingKit
from notlob.bindings.haskell.assemble import assemble
from notlob.bindings.haskell.runner import run_examples, run_tests, run_properties
from notlob.bindings.haskell.symbols import extract_symbols

#: The assembled Haskell binding kit.
kit = BindingKit(
    extract_symbols=extract_symbols,
    assemble=assemble,
    run_examples=run_examples,
    run_properties=run_properties,
    run_tests=run_tests,
)

__all__ = [
    "kit", "extract_symbols", "assemble",
    "run_examples", "run_tests", "run_properties",
]
