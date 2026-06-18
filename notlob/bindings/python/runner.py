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
# Keeping the import out of module scope means projects that do not
# declare ~property-testing hypothesis need not have hypothesis installed.

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
from notlob.model import Claim, Module, Subheading, TestsSection, TestGroup
from notlob.bindings.python.assemble import assemble
from notlob.project import module_lob_refs


def _build_property_ns(binding: dict | None) -> dict:
    """Return the namespace to inject into ~property claim contexts.

    Driven by the ``property-testing`` key in *binding*.  Currently
    only ``hypothesis`` is supported.

    hypothesis is imported lazily here so that projects which do not
    declare ``~property-testing hypothesis`` need not have hypothesis
    installed.
    """
    if binding is None:
        return {}
    if binding.get("property-testing") == "hypothesis":
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
    return {}


def _build_test_ns(binding: dict | None) -> dict:
    """Return the namespace to inject into #Tests assertion contexts.

    Driven by the ``unit-testing`` key in *binding*.  Currently only
    ``pytest`` is supported.
    """
    if binding is None:
        return {}
    if binding.get("unit-testing") == "pytest":
        return dict(_PYTEST_NS)
    return {}


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

    _run_section(module.body, mod_addr, ns, results)

    for item in module.body:
        if isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            _run_section(item.body, sub_addr, ns, results)

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
    <module>#Tests.

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

    ns.update(_build_test_ns(binding))

    results: list[ClaimResult] = []
    tests_addr = f"{mod_addr}#Tests"
    bare: list[str] = []

    for item in tests_section.items:
        if isinstance(item, str):
            bare.append(item)
        else:
            if bare:
                for assertion in _iter_assertions(bare):
                    results.append(_eval_line(tests_addr, assertion, ns))
                bare = []
            group_addr = f"{tests_addr}#{item.title}"
            for assertion in _iter_assertions(item.lines):
                results.append(_eval_line(group_addr, assertion, ns))

    for assertion in _iter_assertions(bare):
        results.append(_eval_line(tests_addr, assertion, ns))

    return results


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

    inject_ns = _build_property_ns(binding)
    results: list[ClaimResult] = []

    _run_props_in(
        module.body, mod_addr, ns, results, inject_ns,
        mod_source=mod_source, keep_dir=keep_dir,
    )

    for item in module.body:
        if isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            _run_props_in(
                item.body, sub_addr, ns, results, inject_ns,
                mod_source=mod_source, keep_dir=keep_dir,
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
        for assertion in _iter_assertions(list(bare)):
            parts.append(f"assert {assertion}")
        bare.clear()

    for item in tests_section.items:
        if isinstance(item, str):
            bare.append(item)
        else:
            _flush_bare()
            group_addr = f"{tests_addr}#{item.title}"
            parts.append(f"\n# --- {group_addr} ---")
            for assertion in _iter_assertions(item.lines):
                parts.append(f"assert {assertion}")

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
            for assertion in _iter_assertions(item.lines):
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


# ── Internals ─────────────────────────────────────────────────

def _run_section(
    body:           list,
    containing_addr: str,
    ns:             dict,
    results:        list[ClaimResult],
) -> None:
    """Evaluate ~example claims found directly in body."""
    example_n = 0
    for item in body:
        if not (isinstance(item, Claim) and item.sigil == "~example"):
            continue
        example_n += 1
        addr = claim_address(containing_addr, "example", example_n)
        for assertion in _iter_assertions(item.lines):
            results.append(_eval_line(addr, assertion, ns))


def _eval_line(addr: str, line: str, ns: dict) -> ClaimResult:
    """Evaluate one assertion line and return a ClaimResult."""
    try:
        exec(f"assert {line}", ns)
        return ClaimResult(address=addr, line=line, status=Status.PASS)
    except AssertionError:
        left, right = _extract_sides(line, ns)
        return ClaimResult(
            address=addr, line=line, status=Status.FAIL,
            left=left, right=right,
        )
    except Exception as exc:
        return ClaimResult(
            address=addr, line=line,
            status=Status.ERROR, error=exc,
        )


def _iter_assertions(lines: list[str]):
    """Yield complete assertion expressions from raw claim lines.

    Multi-line expressions (unclosed parentheses/brackets spanning
    several lines) are joined before yielding so the runner sees one
    complete expression per assertion.
    """
    buffer: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        buffer.append(stripped)
        if _is_complete("\n".join(buffer)):
            yield "\n".join(buffer)
            buffer = []
    if buffer:
        yield "\n".join(buffer)   # incomplete — will surface as ERROR


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
) -> None:
    """Evaluate ~property claims found directly in body."""
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
            ))
            continue

        callable_ = _find_property_callable(claim_ns, module_ns, inject_ns)
        if callable_ is None:
            results.append(ClaimResult(
                address=addr,
                line=item.sigil,
                status=Status.ERROR,
                error=ValueError("no callable found in ~property block"),
            ))
            continue

        try:
            callable_()
            results.append(ClaimResult(
                address=addr, line=item.sigil, status=Status.PASS,
            ))
        except Exception as exc:
            results.append(ClaimResult(
                address=addr, line=item.sigil,
                status=Status.FAIL, error=exc,
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
