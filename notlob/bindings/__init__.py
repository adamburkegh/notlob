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
    claims = claims_to_run(graph, module_address(module.title))
    examples = [c for c in claims if c.kind == "EXAMPLE"]
    results = kit.run_examples(module, examples, file_path=path, deps=deps)
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Generator, Sequence

from ..model import CodeBlock, ImportLine, Module


# ── What a binding is handed to run ──────────────────────────
#
# notlob works out which claims and tests a module has, from its graph;
# a binding runs what it is handed and keeps everything about its
# language: assembling, splitting assertions, running, reporting.

@dataclass(frozen=True)
class ClaimToRun:
    """A claim or test of a module, as notlob found it, for a binding to
    run.

    address     The address its results are reported at: its own for an
                ``~example``, a ``~property``, a ``~run`` and a ``~test``,
                and for a run of bare assertions the address of the
                ``##group`` or ``#Tests`` it is written in.
    kind        ``"EXAMPLE"``, ``"PROPERTY"``, ``"RUN"`` or ``"TEST"``
                (a ``NodeKind`` name, as ``notlob.graph`` imports this
                module).
    lines       Its lines, one for each line of the file; blank ones are
                kept. A claim's are dedented.
    first_line  The line of the file that ``lines[0]`` is on, or ``None``
                when it is not known.
    sigil_line  The line of its ``~sigil``; ``None`` for a run of bare
                assertions, which has none.
    name        The name of a named ``~property`` or ``~test``.
    mode        When a ``~run`` runs: ``"on-load"`` or ``"on-invocation"``
                (what a bare ``~run`` means).
    """
    address:    str
    kind:       str
    lines:      list[str]
    first_line: int | None
    sigil_line: int | None
    name:       str | None = None
    mode:       str | None = None


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

    name        The top-level defined name (function, class, variable).
    source      The dedented source text for that definition, or None
                when the extractor cannot supply a precise slice.
    first_line  The first line of the definition, 1-based within the
                lines the extractor was given; None when not supplied.
    last_line   Its last non-blank line, in the same terms.

    A binding that leaves the lines unset still works: the graph keeps
    *source* on the symbol's node, as it has no lines to read it by.
    """
    name:       str
    source:     str | None = None
    first_line: int | None = None
    last_line:  int | None = None


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

#: Callable that splits the import lines of ``#References`` (the lines that
#: list no module, blank ones included) into statements: where one ends is
#: the bound language's rule. Gives each statement's text, dedented, and
#: the line of the file its first line is on.
ImportSplitter = Callable[
    [Sequence[ImportLine]], list[tuple[str, int | None]]]


def default_split_imports(
    lines: Sequence[ImportLine],
) -> list[tuple[str, int | None]]:
    """One statement for each non-blank line: what a binding that does not
    say where a statement ends gets."""
    return [(line.text.strip(), line.line) for line in lines
            if line.text.strip()]


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

    A binding documents itself in a ``BINDING.md`` in its package
    directory; ``notlob docs`` writes it out as ``BINDING-<language>.md``.
    This is optional and not part of the kit's fields.

    Fields
    ------
    extract_symbols  Symbol extraction: code lines → names.
    extract_calls    Call extraction: source text → referenced names.
                     Returns statically visible references only; dynamic
                     calls (eval, getattr, method dispatch) are invisible
                     by design.  ``None`` when the binding does not
                     implement static call analysis.
    assemble         Code assembly: Module → executable string.
    run_examples     (module, claims, *, file_path=None, root=None,
                     deps=()) -> list[ClaimResult]
    run_properties   (module, claims, *, file_path=None, root=None,
                     deps=()) -> list[ClaimResult]
    run_tests        (module, claims, *, file_path=None, root=None,
                     deps=()) -> list[ClaimResult]
    lint             (module, claims, *, root=None) -> list[LintResult],
                     or None when the binding does not support static
                     analysis.
    extension        File extension for build artifacts (e.g. ``"py"``,
                     ``"hs"``, ``"ts"``).
    comment_prefix   Location-comment prefix used in assembled/build
                     output (e.g. ``"#"``, ``"--"``, ``"//"``).
    build            (module, claims, file_path=None, *, deps=())
                     -> str, the assembly used by ``notlob build``, or
                     None when the binding doesn't support it.
    complete_references
                     True when ``extract_calls`` reports every name the
                     code refers to (not only calls), outside strings and
                     comments.  Loading follows use only for a binding
                     that sets this: a listed module whose names the
                     code does not refer to is then a citation and is not
                     loaded.  False (the default) means use cannot be
                     determined, and every listing except one of a
                     descendant module is loaded.
    split_imports    (lines) -> list[(text, first_line)]: the import
                     statements in the lines of ``#References`` that list
                     no module (see :data:`ImportSplitter`), by the
                     language's own rule for where a statement ends. The
                     default is one statement for each non-blank line, so
                     a binding that does not say keeps working.

    ``claims`` is a list of :class:`ClaimToRun`: the claims and tests of
    *module* that notlob found, which the binding runs. notlob collects
    them from the module's graph, wherever they are written (the body,
    subheadings, an ``#Appendix``, ``#Tests``), and gives each callable
    only the kinds it runs: ``"EXAMPLE"`` claims to ``run_examples``,
    ``"PROPERTY"`` to ``run_properties``, ``"TEST"`` to ``run_tests``,
    ``"RUN"`` to ``build``, and all of them to ``lint``. *module* stays
    for assembly. A binding keeps everything about its language:
    assembling code, splitting a claim into assertions, running,
    reporting.

    ``root`` is the project root (a ``Path``), or ``None`` without a
    project, given to ``run_examples``, ``run_properties`` and
    ``run_tests`` as ``lint`` has it: a binding that finds its toolchain
    in the project reads it (TypeScript's ``node_modules``), and the
    others accept it.

    ``deps`` is a sequence of :class:`~notlob.model.Module`: the modules
    whose code *module*'s code needs, and what those need, dependencies
    first, each once. notlob works that out from the package graph
    (``notlob.project.load_order``) and parses them; ``run_examples``,
    ``run_properties``, ``run_tests`` and ``build`` inline them before
    the module's own code and load nothing themselves. It is empty when
    there is no project to load from.

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
    complete_references: bool                   = False
    split_imports:   ImportSplitter             = default_split_imports


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


def assemble_section(
    comment: str, blocks: list[str], blank_lines: int = 1,
) -> str:
    """Join a location comment and its code blocks.

    The comment is glued to the first block (no blank line between
    them); subsequent blocks are separated by *blank_lines* blank
    lines (default 1). Python's assembler passes 2 to match PEP8/
    isort's "two blank lines between top-level definitions"
    convention; Haskell and TypeScript have no equivalent convention
    and use the default.
    """
    first, *rest = blocks
    head = f"{comment}\n{first}"
    if rest:
        sep = "\n" * (blank_lines + 1)
        return head + sep + sep.join(rest)
    return head


# ── Shared ~run collection ───────────────────────────────────

def run_bodies(claims: Sequence[ClaimToRun]) -> tuple[list[str], list[str]]:
    """Return ``(on_load_bodies, on_invocation_bodies)`` -- dedented,
    stripped text for each ``~run`` in *claims*, grouped by its mode and
    preserving document order within each group.

    A bare ``~run`` is ``on-invocation`` -- the notlob equivalent of
    ``if __name__ == "__main__":`` (see DESIGN.md). ``~run on-load``
    fires unconditionally whenever the built artifact is loaded at all,
    not just when it's the entry point. What each binding's ``build()``
    does with that distinction -- or whether it supports ``on-load`` at
    all -- is entirely up to that binding.
    """
    on_load: list[str] = []
    on_invocation: list[str] = []
    for claim in claims:
        if claim.kind != "RUN":
            continue
        text = textwrap.dedent("\n".join(claim.lines)).strip()
        if not text:
            continue
        (on_load if claim.mode == "on-load" else on_invocation).append(text)
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
