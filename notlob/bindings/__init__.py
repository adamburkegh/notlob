"""notlob.bindings — Language binding kit infrastructure.

A binding kit composes the language-specific callables needed by the
name-graph and claim runner.  Language is the primary axis; tool
components (property testing, test runner) are submodules within each
language package.

Usage::

    from notlob.bindings.python import kit
    enrich(graph, module, kit.extract_symbols)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence


#: Callable that maps a list of indented code lines to defined names.
Extractor = Callable[[Sequence[str]], list[str]]


@dataclass
class BindingKit:
    """A composed set of language-specific tooling callables.

    extract_symbols  Stage-2 name extraction: code lines → names.

    Future fields will add: assemble (tangling), run_examples,
    run_properties.
    """
    extract_symbols: Extractor
