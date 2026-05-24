"""notlob.bindings — Language binding kit infrastructure.

A binding kit composes the language-specific callables needed by the
name-graph and claim runner.  Language is the primary axis; tool
components (property testing, test runner) are submodules within each
language package.

Usage::

    from notlob.bindings.python import kit
    enrich(graph, module, kit.extract_symbols)
    source = kit.assemble(module)
    results = kit.run_examples(module, file_path=path)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from ..model import Module


@dataclass
class SymbolInfo:
    """A symbol extracted from a code block.

    name    The top-level defined name (function, class, variable).
    source  The dedented source text for that definition, or None
            when the extractor cannot supply a precise slice.
    """
    name:   str
    source: str | None = None


#: Callable that maps indented code lines to SymbolInfo objects.
Extractor = Callable[[Sequence[str]], list[SymbolInfo]]

#: Callable that assembles a Module into one executable string.
Assembler = Callable[[Module], str]


@dataclass
class BindingKit:
    """A composed set of language-specific tooling callables.

    extract_symbols  Symbol extraction: code lines → names.
    assemble         Code assembly: Module → executable string.
    run_examples     (module, *, file_path=None) -> list[ClaimResult]
    run_properties   (module, *, binding=None, file_path=None) -> list[ClaimResult]
    run_tests        (module, *, binding=None, file_path=None) -> list[ClaimResult]

    The runner fields return list[ClaimResult] (notlob.bindings.python.runner).
    They are typed as Callable[..., list] here to avoid a cross-layer
    import; the concrete element type is documented above.
    """
    extract_symbols: Extractor
    assemble:        Assembler
    run_examples:    Callable[..., list]
    run_properties:  Callable[..., list]
    run_tests:       Callable[..., list]
