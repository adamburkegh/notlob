"""notlob.bindings — Language binding kit infrastructure.

A binding kit composes the language-specific callables needed by the
name-graph and claim runner.  Language is the primary axis; tool
components (property testing, test runner) are submodules within each
language package.

``ClaimResult`` and ``Status`` live here — not inside any language
binding — so that all runners share a common result type.

Usage::

    from notlob.bindings.python import kit
    enrich(graph, module, kit.extract_symbols)
    source = kit.assemble(module)
    results = kit.run_examples(module, file_path=path)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Sequence

from ..model import Module


# ── Claim result types ────────────────────────────────────────
#
# Shared by all language runners so that commands.py can handle
# results uniformly regardless of which binding produced them.

class Status(Enum):
    PASS  = auto()
    FAIL  = auto()
    ERROR = auto()
    SKIP  = auto()   # claim type not supported by this binding


@dataclass(frozen=True)
class ClaimResult:
    """The outcome of evaluating one assertion line.

    address  Claim address: containing_addr#example#n
    line     The source assertion text (without leading 'assert ')
    status   PASS, FAIL, ERROR, or SKIP
    left     Evaluated left-hand side  (FAIL only; None otherwise)
    right    Evaluated right-hand side (FAIL only; None otherwise)
    error    Exception raised or message (ERROR/FAIL only; None
             otherwise)
    """
    address: str
    line:    str
    status:  Status
    left:    Any              = None
    right:   Any              = None
    error:   Exception | None = None


# ── Symbol info ───────────────────────────────────────────────

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


# ── Binding kit ───────────────────────────────────────────────

@dataclass
class BindingKit:
    """A composed set of language-specific tooling callables.

    extract_symbols  Symbol extraction: code lines → names.
    assemble         Code assembly: Module → executable string.
    run_examples     (module, *, file_path=None) -> list[ClaimResult]
    run_properties   (module, *, binding=None, file_path=None) -> list[ClaimResult]
    run_tests        (module, *, binding=None, file_path=None) -> list[ClaimResult]

    Runner callables are typed as Callable[..., list] to avoid a
    circular import; the element type is always ClaimResult.
    """
    extract_symbols: Extractor
    assemble:        Assembler
    run_examples:    Callable[..., list]
    run_properties:  Callable[..., list]
    run_tests:       Callable[..., list]
