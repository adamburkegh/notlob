"""notlob.bindings.python.runner — claim runner for the Python binding.

Assembles a module into executable Python, then evaluates each claim
in that namespace.  Results carry the claim's address, the source
line, and (for failures) the evaluated left- and right-hand sides of
the comparison.

One ClaimResult is produced per assertion line.  The ordinal in the
claim address counts ~example blocks within their containing node:

    roman/numerals#example#1     ← first ~example in module body
    roman/numerals#Decoding#example#2  ← second ~example in subheading

Binding declarations
--------------------
run_properties and run_tests accept an optional ``binding`` dict of
declarations parsed from binding.lob, e.g.::

    {"property-testing": "hypothesis", "unit-testing": "pytest"}

These drive namespace injection — see _build_property_ns and
_build_test_ns.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from typing import Any

# _HYPOTHESIS_NS is built lazily on first use; see _build_property_ns.
# Projects need not have hypothesis explicitly installed.

# Names injected into #Tests assertion namespaces when binding declares
# ~unit-testing pytest.  Probably anemic; likely to grow as usage
# patterns emerge.
try:
    import pytest as _pytest
    _PYTEST_NS: dict = {
        "pytest":  _pytest,
        "approx":  _pytest.approx,
        "raises":  _pytest.raises,
    }
except ImportError:
    _PYTEST_NS = {}

from notlob.bindings import ClaimResult, Status
from notlob.graph import (
    claim_address, module_address, property_address, subheading_address,
)
from notlob.model import (
    Claim, Module, NamedTest, Subheading, TestGroup, TestsSection,
)
from notlob.bindings.python.assemble import assemble
from notlob.project import module_lob_refs


def _build_property_ns() -> dict:
    """Return the hypothesis namespace injected into ~property claim contexts.

    Returns an empty dict if hypothesis is not
    installed so that a missing install surfaces as a NameError at claim
    time rather than an import error at startup.
    """
    try:
        import hypothesis as _hyp
        import hypothesis.strategies as _st
    except ImportError:
        return {}
    return {
        "given":       _hyp.given,
        "settings":    _hyp.settings,
        "assume":      _hyp.assume,
        "note":        _hyp.note,
        "target":      _hyp.target,
        "HealthCheck": _hyp.HealthCheck,
        "Phase":       _hyp.Phase,
        "Verbosity":   _hyp.Verbosity,
        "st":          _st,
        "strategies":  _st,
    }


def _build_test_ns() -> dict:
    """Return the pytest namespace injected into #Tests assertion contexts.

    pytest is part of the Python binding toolchain — always injected,
    no declaration needed.
    """
    return dict(_PYTEST_NS)


def run_examples(
    module: Module,
    file_path: Path | None = None,
    cache: Any = None,
    keep_dir: Path | None = None,
) -> list[ClaimResult]:
    """Run all ~example claims in a module and return results.

    *file_path*, when provided, is injected as ``__file__`` into the
    execution namespace so that modules can locate data files relative
    to themselves.

    *keep_dir*, when provided, causes the assembled module source to be
    written to ``<keep_dir>/_examples.py`` before execution.

    Assembly errors (syntax errors in code blocks, import failures,
    etc.) produce a single ERROR result with address equal to the
    module address and line '<assembly>'.
    """
    ns: dict = (
        {"__file__": str(file_path.resolve())} if file_path else {}
    )
    mod_addr = module_address(module.title)
    source = assemble(module)
    _write_kept_source(keep_dir, "_examples.py",
                       _build_examples_source(source, module, mod_addr))

    try:
        _load_deps(module, ns, cache)
        exec(source, ns)
    except Exception as exc:
        return [ClaimResult(
            address=mod_addr,
            line="<assembly>",
            status=Status.ERROR,
            error=exc,
        )]

    results: list[ClaimResult] = []

    _run_section(module.body, mod_addr, ns, results, file_path)

    for item in module.body:
        if isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            _run_section(item.body, sub_addr, ns, results, file_path)

    return results


def run_tests(
    module: Module,
    binding: dict | None = None,
    file_path: Path | None = None,
    cache: Any = None,
    keep_dir: Path | None = None,
) -> list[ClaimResult]:
    """Run all assertions in the #Tests section and return results.

    Assertions under a named ## group get an address of the form
    <module>#Tests#<group>.  Bare assertions outside any group use
    <module>#Tests.  A ``~test <name>`` block gets its own address
    (<module>#Tests#<group>#<name>), with every assertion line inside
    it sharing that one address -- matching how an unnamed ~example
    block's own lines already share one address, distinguished by
    source line rather than a per-line ordinal.  Prose commentary
    interspersed with assertions (at either level) is not evaluated.

    *binding* is a dict of declarations from binding.lob (e.g.
    ``{"unit-testing": "pytest"}``).  When present, the appropriate
    helpers are injected into the assertion namespace.

    *file_path*, when provided, is injected as ``__file__`` into the
    execution namespace.

    *keep_dir*, when provided, causes the assembled module source to be
    written to ``<keep_dir>/_tests.py`` before execution.

    Assembly errors produce a single ERROR result as with run_examples.
    """
    if module.post_text is None:
        return []

    tests_section = next(
        (s for s in module.post_text.sections
         if isinstance(s, TestsSection)),
        None,
    )
    if tests_section is None:
        return []

    ns: dict = (
        {"__file__": str(file_path.resolve())} if file_path else {}
    )
    mod_addr = module_address(module.title)
    source = assemble(module)
    _write_kept_source(keep_dir, "_tests.py",
                       _build_tests_source(source, tests_section, mod_addr))

    try:
        _load_deps(module, ns, cache)
        exec(source, ns)
    except Exception as exc:
        return [ClaimResult(
            address=mod_addr,
            line="<assembly>",
            status=Status.ERROR,
            error=exc,
        )]

    ns.update(_build_test_ns())

    fp = str(file_path) if file_path else None
    line_offsets = tests_section.line_offsets or {}
    results: list[ClaimResult] = []
    tests_addr = f"{mod_addr}#Tests"
    bare: list[str] = []
    bare_indices: list[int] = []

    def _flush_bare() -> None:
        if not bare:
            return
        first_line = line_offsets.get(bare_indices[0])
        for assertion, offset in _iter_assertions(bare):
            sl = (first_line + offset) if first_line else None
            results.append(_eval_line(
                tests_addr, assertion, ns,
                source_line=sl, file_path=fp,
            ))
        bare.clear()
        bare_indices.clear()

    for idx, item in enumerate(tests_section.items):
        if isinstance(item, str):
            bare.append(item)
            bare_indices.append(idx)
        elif isinstance(item, TestGroup):
            _flush_bare()
            group_addr = f"{tests_addr}#{item.title}"
            _eval_group_items(item, group_addr, ns, results, fp)
        # ProseBlock: commentary, not evaluated.

    _flush_bare()
    return results


def _eval_group_items(
    group: TestGroup,
    group_addr: str,
    ns: dict,
    results: list[ClaimResult],
    file_path: str | None,
) -> None:
    """Evaluate one TestGroup's own bare assertions and NamedTest blocks.

    Bare lines share group_addr (like #Tests's own top-level bare
    lines share tests_addr); each NamedTest gets its own address
    (group_addr#name), with all its assertion lines sharing that one
    address -- matching ~example's addressing exactly (see
    notlob.graph.property_address / claim_address).
    """
    line_offsets = group.line_offsets or {}
    bare: list[str] = []
    bare_indices: list[int] = []

    def _flush_bare() -> None:
        if not bare:
            return
        first_line = line_offsets.get(bare_indices[0])
        for assertion, offset in _iter_assertions(bare):
            sl = (first_line + offset) if first_line else None
            results.append(_eval_line(
                group_addr, assertion, ns,
                source_line=sl, file_path=file_path,
            ))
        bare.clear()
        bare_indices.clear()

    for idx, item in enumerate(group.items):
        if isinstance(item, str):
            bare.append(item)
            bare_indices.append(idx)
        elif isinstance(item, NamedTest):
            _flush_bare()
            addr = property_address(group_addr, item.name)
            base = (item.start_line + 1) if item.start_line else None
            for assertion, offset in _iter_assertions(item.lines):
                sl = (base + offset) if base else None
                results.append(_eval_line(
                    addr, assertion, ns,
                    source_line=sl, file_path=file_path,
                ))
        # ProseBlock: commentary, not evaluated.

    _flush_bare()


def run_properties(
    module: Module,
    binding: dict | None = None,
    file_path: Path | None = None,
    cache: Any = None,
    keep_dir: Path | None = None,
) -> list[ClaimResult]:
    """Run all ~property claims in a module and return results.

    Each claim block is exec'd into a fresh copy of the assembled
    module namespace, isolating the ephemeral witness function from
    the module's permanent state.  The property-testing library
    drives execution when the decorated function is called.

    *binding* is a dict of declarations from binding.lob (e.g.
    ``{"property-testing": "hypothesis"}``).  When present, the
    appropriate names are injected into each claim namespace.

    *file_path*, when provided, is injected as ``__file__`` into the
    execution namespace.

    *keep_dir*, when provided, causes each property's assembled source
    (module code + property block) to be written to
    ``<keep_dir>/_prop_<name>.py`` before execution.

    Named properties (`~property name`) use the sigil name as address.
    Unnamed properties use an ordinal: <containing>#property#n.

    Assembly errors produce a single ERROR result as with run_examples.
    """
    ns: dict = (
        {"__file__": str(file_path.resolve())} if file_path else {}
    )
    mod_addr = module_address(module.title)

    mod_source = assemble(module)

    try:
        _load_deps(module, ns, cache)
        exec(mod_source, ns)
    except Exception as exc:
        return [ClaimResult(
            address=mod_addr,
            line="<assembly>",
            status=Status.ERROR,
            error=exc,
        )]

    inject_ns = _build_property_ns()
    results: list[ClaimResult] = []

    _run_props_in(
        module.body, mod_addr, ns, results, inject_ns,
        mod_source=mod_source, keep_dir=keep_dir,
        file_path=file_path,
    )

    for item in module.body:
        if isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            _run_props_in(
                item.body, sub_addr, ns, results, inject_ns,
                mod_source=mod_source, keep_dir=keep_dir,
                file_path=file_path,
            )

    return results


# ── Keep-generated-src ───────────────────────────────────────

def _write_kept_source(
    keep_dir: Path | None,
    filename: str,
    source: str,
) -> None:
    """Write *source* to ``keep_dir / filename`` if *keep_dir* is set."""
    if keep_dir is None:
        return
    keep_dir.mkdir(parents=True, exist_ok=True)
    (keep_dir / filename).write_text(source, encoding="utf-8")


def _build_group_source(
    parts: list[str],
    group_items: list,
    group_addr: str,
) -> None:
    """Append a TestGroup's own bare assertions and NamedTest blocks.

    ProseBlock items are commentary -- skipped, same as in _add_tests.
    """
    bare: list[str] = []

    def _flush_bare() -> None:
        if not bare:
            return
        parts.append(f"\n# --- {group_addr} ---")
        for assertion, _ in _iter_assertions(list(bare)):
            parts.append(f"assert {assertion}")
        bare.clear()

    for item in group_items:
        if isinstance(item, str):
            bare.append(item)
        elif isinstance(item, NamedTest):
            _flush_bare()
            addr = property_address(group_addr, item.name)
            parts.append(f"\n# --- {addr} ---")
            for assertion, _ in _iter_assertions(item.lines):
                parts.append(f"assert {assertion}")
        # ProseBlock: commentary, not evaluated.

    _flush_bare()


def _build_tests_source(
    module_source: str,
    tests_section: TestsSection,
    mod_addr: str,
) -> str:
    """Build an executable source string: module code + #Tests assertions."""
    parts = [module_source.rstrip("\n")]
    tests_addr = f"{mod_addr}#Tests"
    bare: list[str] = []

    def _flush_bare() -> None:
        if not bare:
            return
        parts.append(f"\n# --- {tests_addr} ---")
        for assertion, _ in _iter_assertions(list(bare)):
            parts.append(f"assert {assertion}")
        bare.clear()

    for item in tests_section.items:
        if isinstance(item, str):
            bare.append(item)
        elif isinstance(item, TestGroup):
            _flush_bare()
            group_addr = f"{tests_addr}#{item.title}"
            parts.append(f"\n# --- {group_addr} ---")
            _build_group_source(parts, item.items, group_addr)
        # ProseBlock: commentary, not evaluated.

    _flush_bare()
    return "\n".join(parts) + "\n"


def _build_examples_source(
    module_source: str,
    module: Module,
    mod_addr: str,
) -> str:
    """Build an executable source string: module code + ~example assertions."""
    parts = [module_source.rstrip("\n")]

    def _append_section(body: list, containing_addr: str) -> None:
        example_n = 0
        for item in body:
            if not (isinstance(item, Claim) and item.sigil == "~example"):
                continue
            example_n += 1
            addr = claim_address(containing_addr, "example", example_n)
            parts.append(f"\n# --- {addr} ---")
            for assertion, _ in _iter_assertions(item.lines):
                parts.append(f"assert {assertion}")

    _append_section(module.body, mod_addr)
    for item in module.body:
        if isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            _append_section(item.body, sub_addr)

    return "\n".join(parts) + "\n"


# ── Dependency loading ────────────────────────────────────────

def _load_deps(
    module: Module,
    ns:     dict,
    cache:  Any,        # ModuleCache | None  (avoids circular import)
) -> None:
    """Merge dependency namespaces into *ns* using *cache*.

    A no-op when *cache* is None — callers that have no project root
    (e.g. single-file tests) are unaffected.
    """
    if cache is None:
        return
    for dep_addr in module_lob_refs(module):
        ns.update(cache.load(dep_addr))


def _load_dep_modules(
    module: Module,
    file_path: Path | None,
) -> list[Module]:
    """Return the lob-ref dependency modules of *module* in declaration order.

    Used by ``build_python`` to inline dependency code into a build
    artifact (unlike ``_load_deps``, which merges already-exec'd
    *namespaces* via a ``ModuleCache`` for ``notlob test``/``notlob run``
    — a build artifact has no loader around it at execution time, so its
    dependencies' source has to be inlined instead). Mirrors
    ``notlob.bindings.haskell.runner._load_dep_modules`` exactly.

    Resolves each ``#Title`` lob-ref in *module*'s ``#References``
    section to its ``.lob`` file under the project root, parses it, and
    returns the resulting Module objects. Dependencies that cannot be
    found or parsed are silently skipped — the resulting NameError at
    execution time surfaces the missing symbol, same as a real import
    error would.

    Returns an empty list when *file_path* is ``None`` (no project
    context available) or when no project root is found.
    """
    if file_path is None:
        return []

    from notlob.project import (           # noqa: PLC0415
        find_project_root, resolve_module_path,
    )
    from notlob.parser import parse_file   # noqa: PLC0415
    from notlob.model import from_tree     # noqa: PLC0415

    root = find_project_root(file_path)
    if root is None:
        return []

    result: list[Module] = []
    for dep_addr in module_lob_refs(module):
        try:
            dep_path = resolve_module_path(dep_addr, root)
            result.append(from_tree(parse_file(dep_path)))
        except Exception:
            pass  # missing dep — will surface as a NameError at exec time

    return result


# ── Internals ─────────────────────────────────────────────────

def _run_section(
    body:           list,
    containing_addr: str,
    ns:             dict,
    results:        list[ClaimResult],
    file_path:      Path | None = None,
) -> None:
    """Evaluate ~example claims found directly in body."""
    example_n = 0
    fp = str(file_path) if file_path else None
    for item in body:
        if not (isinstance(item, Claim) and item.sigil == "~example"):
            continue
        example_n += 1
        addr = claim_address(containing_addr, "example", example_n)
        base = (item.start_line + 1) if item.start_line else None
        for assertion, offset in _iter_assertions(item.lines):
            sl = (base + offset) if base else None
            results.append(_eval_line(
                addr, assertion, ns, source_line=sl, file_path=fp,
            ))


def _eval_line(
    addr: str,
    line: str,
    ns: dict,
    source_line: int | None = None,
    file_path: str | None = None,
) -> ClaimResult:
    """Evaluate one assertion line and return a ClaimResult."""
    try:
        exec(f"assert {line}", ns)
        return ClaimResult(
            address=addr, line=line, status=Status.PASS,
            source_line=source_line, file_path=file_path,
        )
    except AssertionError:
        left, right = _extract_sides(line, ns)
        return ClaimResult(
            address=addr, line=line, status=Status.FAIL,
            left=left, right=right,
            source_line=source_line, file_path=file_path,
        )
    except Exception as exc:
        return ClaimResult(
            address=addr, line=line,
            status=Status.ERROR, error=exc,
            source_line=source_line, file_path=file_path,
        )


def _iter_assertions(lines: list[str]):
    """Yield ``(expression, line_offset)`` from raw claim lines."""
    from notlob.bindings import iter_assertions
    yield from iter_assertions(lines, is_complete=_is_complete)


def _is_complete(text: str) -> bool:
    """Return True if text is a syntactically complete expression.

    An unclosed delimiter ("was never closed") means more lines are
    needed.  Any other SyntaxError is treated as complete — the error
    will be reported when the assertion is actually executed.
    """
    try:
        compile(f"assert {text}", "<claim>", "exec")
        return True
    except SyntaxError as exc:
        return "was never closed" not in (exc.msg or "")


def _run_props_in(
    body:           list,
    containing_addr: str,
    module_ns:      dict,
    results:        list[ClaimResult],
    inject_ns:      dict,
    mod_source:     str = "",
    keep_dir:       Path | None = None,
    file_path:      Path | None = None,
) -> None:
    """Evaluate ~property claims found directly in body."""
    fp = str(file_path) if file_path else None
    prop_n = 0
    for item in body:
        if not (isinstance(item, Claim)
                and item.sigil.startswith("~property")):
            continue
        prop_n += 1

        parts = item.sigil.split(None, 1)
        if len(parts) > 1:
            prop_name = parts[1].strip()
            addr = property_address(containing_addr, prop_name)
        else:
            prop_name = f"property_{prop_n}"
            addr = claim_address(containing_addr, "property", prop_n)

        sl = item.start_line

        prop_block = textwrap.dedent("\n".join(item.lines))
        if keep_dir is not None:
            kept = (
                f"# {addr}\n"
                f"{mod_source}\n\n"
                f"# ~property\n"
                f"{prop_block}\n"
            )
            _write_kept_source(keep_dir, f"_prop_{prop_name}.py", kept)

        claim_ns = dict(module_ns)
        claim_ns.update(inject_ns)
        try:
            exec(prop_block, claim_ns)
        except Exception as exc:
            results.append(ClaimResult(
                address=addr,
                line="<property-exec>",
                status=Status.ERROR,
                error=exc,
                source_line=sl, file_path=fp,
            ))
            continue

        callable_ = _find_property_callable(claim_ns, module_ns, inject_ns)
        if callable_ is None:
            results.append(ClaimResult(
                address=addr,
                line=item.sigil,
                status=Status.ERROR,
                error=ValueError("no callable found in ~property block"),
                source_line=sl, file_path=fp,
            ))
            continue

        try:
            callable_()
            results.append(ClaimResult(
                address=addr, line=item.sigil, status=Status.PASS,
                source_line=sl, file_path=fp,
            ))
        except Exception as exc:
            results.append(ClaimResult(
                address=addr, line=item.sigil,
                status=Status.FAIL, error=exc,
                source_line=sl, file_path=fp,
            ))


def _find_property_callable(
    claim_ns:  dict,
    module_ns: dict,
    inject_ns: dict,
) -> Any:
    """Return the property callable from claim_ns, or None.

    Prefers '_' (the anonymous-witness convention); otherwise returns
    the first new callable not present in module_ns or inject_ns
    (binding-injected names are excluded from consideration).
    """
    baseline = set(module_ns) | set(inject_ns)
    new = {
        k: v for k, v in claim_ns.items()
        if k not in baseline
        and callable(v)
        and not k.startswith('__')
    }
    if not new:
        return None
    return new.get('_') or next(iter(new.values()))


def _extract_sides(
    line: str,
    ns:   dict,
) -> tuple[Any, Any]:
    """Try to evaluate left and right sides of a comparison.

    Returns (None, None) if the line is not a simple equality
    comparison or if evaluation itself raises.
    """
    try:
        tree = ast.parse(line, mode="eval")
        expr = tree.body
        if (
            isinstance(expr, ast.Compare)
            and len(expr.ops) == 1
            and isinstance(expr.ops[0], ast.Eq)
        ):
            left  = eval(ast.unparse(expr.left),           ns)
            right = eval(ast.unparse(expr.comparators[0]), ns)
            return left, right
    except Exception:
        pass
    return None, None
