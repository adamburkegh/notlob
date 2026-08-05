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

import re
import textwrap
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Generator, Sequence

from ..model import Claim, CodeBlock, Module, Subheading


# ── Claim result types ────────────────────────────────────────
#
# Shared by all language runners so that commands.py can handle
# results uniformly regardless of which binding produced them.

class Status(Enum):
    PASS  = auto()
    FAIL  = auto()
    ERROR = auto()
    SKIP  = auto()   # claim type not supported by this binding


class LintToolUnavailable(Exception):
    """Raised when a binding declares a linter but its tool is absent.

    A binding may legitimately have no linter (``BindingKit.lint`` is
    ``None``) — that is not an error.  But when ``lint`` *is* set, the
    underlying tool (ruff, hlint, tsc, ...) is part of the test
    contract: if it cannot be found, ``notlob test`` fails loudly rather
    than silently skipping type/style checks and reporting a false pass.
    Mirrors how the claim runner errors when its runtime is missing.
    """


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
    source_line: int | None   = None
    file_path: str | None     = None


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

#: Callable that returns statically visible symbol references from source text.
#: Takes dedented source text (a single definition or whole block); returns
#: (name, source_line) pairs where source_line is 1-indexed within the text.
#: Builtins and stdlib names should be excluded where detectable.
#: Returns an empty list when static analysis is not possible.
CallExtractor = Callable[[str], list[tuple[str, int]]]

#: Callable that assembles a Module into one executable string.
Assembler = Callable[[Module], str]


# ── Binding kit ───────────────────────────────────────────────

@dataclass
class BindingKit:
    """The extension contract for a notlob language binding.

    A binding is a Python package (or module) that exposes a ``kit``
    instance of this class and an ``extract_symbols`` callable.  It is
    registered under the ``"notlob.bindings"`` entry-point group, keyed
    by the language identifier that appears in ``~language`` declarations:

        [project.entry-points."notlob.bindings"]
        rust = "my_notlob_rust_binding"

    The three built-in bindings (``python``, ``haskell``,
    ``typescript``) are registered the same way in notlob's own
    ``pyproject.toml``.

    Fields
    ------
    extract_symbols  Symbol extraction: code lines → names.
    extract_calls    Call extraction: source text → referenced names.
                     Returns statically visible references only; dynamic
                     calls (eval, getattr, method dispatch) are invisible
                     by design.  ``None`` when the binding does not
                     implement static call analysis.
    assemble         Code assembly: Module → executable string.
    run_examples     (module, *, file_path=None) -> list[ClaimResult]
    run_properties   (module, *, file_path=None) -> list[ClaimResult]
    run_tests        (module, *, file_path=None) -> list[ClaimResult]
    lint             (module, *, root=None) -> list[LintResult], or None
                     when the binding does not support static analysis.
    extension        File extension for build artifacts (e.g. ``"py"``,
                     ``"hs"``, ``"ts"``).
    comment_prefix   Location-comment prefix used in assembled/build
                     output (e.g. ``"#"``, ``"--"``, ``"//"``).
    build            (module, file_path=None) -> str, the assembly used
                     by ``notlob build``, or None when the binding
                     doesn't support it.

    Runner and lint callables are typed as Callable[..., list] to avoid
    a circular import; element types are ClaimResult and LintResult
    respectively.
    """
    extract_symbols: Extractor
    assemble:        Assembler
    run_examples:    Callable[..., list]
    run_properties:  Callable[..., list]
    run_tests:       Callable[..., list]
    lint:            Callable[..., list] | None = None
    extract_calls:   CallExtractor       | None = None
    extension:       str                        = "py"
    comment_prefix:  str                        = "#"
    build:           Callable[..., str]  | None = None


# ── Lint result type ──────────────────────────────────────────

@dataclass(frozen=True)
class LintResult:
    """A lint diagnostic from a static analysis tool.

    address  Section address, e.g. 'roman/numerals#Decoding'
    code     Rule code, e.g. 'E501' or 'F401'
    message  Human-readable diagnostic message
    col      Column number (1-based)
    """
    address: str
    code:    str
    message: str
    col:     int = 1


# ── Shared assembler utilities ───────────────────────────────

def collect_blocks(body: list) -> list[str]:
    """Return dedented, stripped text for each CodeBlock in *body*."""
    result = []
    for item in body:
        if isinstance(item, CodeBlock):
            text = textwrap.dedent("\n".join(item.lines)).strip()
            if text:
                result.append(text)
    return result


def assemble_section(comment: str, blocks: list[str]) -> str:
    """Join a location comment and its code blocks.

    The comment is glued to the first block (no blank line between
    them); subsequent blocks are separated by blank lines.
    """
    first, *rest = blocks
    head = f"{comment}\n{first}"
    if rest:
        return head + "\n\n" + "\n\n".join(rest)
    return head


# ── Shared ~run collection ───────────────────────────────────

def collect_run_bodies(module: Module) -> tuple[list[str], list[str]]:
    """Return ``(on_load_bodies, on_invocation_bodies)`` -- dedented,
    stripped text for each ``~run`` claim in *module* (module body and
    subheadings), grouped by declared mode and preserving document
    order within each group.

    Bare ``~run`` defaults to ``on-invocation`` -- the notlob
    equivalent of ``if __name__ == "__main__":`` (see DESIGN.md).
    ``~run on-load`` fires unconditionally whenever the built artifact
    is loaded at all, not just when it's the entry point. What each
    binding's ``build()`` does with that distinction -- or whether it
    supports ``on-load`` at all -- is entirely up to that binding.
    """
    on_load: list[str] = []
    on_invocation: list[str] = []

    def _mode(sigil: str) -> str:
        parts = sigil.split(None, 1)
        return parts[1] if len(parts) > 1 else "on-invocation"

    def _collect(body: list) -> None:
        for item in body:
            if isinstance(item, Claim) and item.sigil.startswith("~run"):
                text = textwrap.dedent("\n".join(item.lines)).strip()
                if not text:
                    continue
                target = (
                    on_load if _mode(item.sigil) == "on-load"
                    else on_invocation
                )
                target.append(text)
            elif isinstance(item, Subheading):
                _collect(item.body)

    _collect(module.body)
    return on_load, on_invocation


def iter_assertions(
    lines: list[str],
    is_complete: Callable[[str], bool] | None = None,
) -> Generator[tuple[str, int], None, None]:
    """Yield ``(expression, line_offset)`` from raw claim lines.

    *line_offset* is the 0-based index within *lines* where the
    assertion starts.

    When *is_complete* is provided, multi-line expressions (unclosed
    brackets spanning several lines) are buffered and joined before
    yielding.  When ``None``, each non-blank line is a separate
    assertion (suitable for languages without multi-line expressions).
    """
    if is_complete is None:
        for i, raw in enumerate(lines):
            stripped = raw.strip()
            if stripped:
                yield stripped, i
        return

    buffer: list[str] = []
    start_offset = 0
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped:
            continue
        if not buffer:
            start_offset = i
        buffer.append(stripped)
        joined = "\n".join(buffer)
        if is_complete(joined):
            yield joined, start_offset
            buffer = []
    if buffer:
        yield "\n".join(buffer), start_offset


def parse_source_map(
    assembled_src: str,
    comment_prefix: str = "#",
) -> dict[int, str]:
    """Map 1-based line numbers to section addresses.

    Scans *assembled_src* for location comments of the form
    ``<comment_prefix> <address>`` and returns a dict mapping each
    executable line to its containing section address.

    Lines before the first address marker are assigned to the first
    address seen, so import-level diagnostics are attributed to
    the module section.
    """
    pat = re.compile(
        r'^' + re.escape(comment_prefix)
        + r' ([a-z][a-z0-9/_-]*(?:#[^\n]*)?)$'
    )
    lines = assembled_src.splitlines()
    result: dict[int, str] = {}
    current: str | None = None
    pending: list[int] = []

    for lineno, line in enumerate(lines, 1):
        m = pat.match(line)
        if m:
            addr = m.group(1)
            if current is None:
                for pending_lineno in pending:
                    result[pending_lineno] = addr
                pending = []
            current = addr
        else:
            if current is not None:
                result[lineno] = current
            else:
                pending.append(lineno)

    return result
