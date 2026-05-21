"""notlob.bindings.python.runner — ~example claim runner.

Assembles a module into executable Python, then evaluates each
~example claim assertion in that namespace.  Results carry the
claim's address, the source line, and (for failures) the evaluated
left- and right-hand sides of the comparison.

One ClaimResult is produced per assertion line.  The ordinal in the
claim address counts ~example blocks within their containing node:

    roman/numerals#example#1     ← first ~example in module body
    roman/numerals#Decoding#example#2  ← second ~example in subheading
"""

from __future__ import annotations

import ast
import textwrap
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

import hypothesis
import hypothesis.strategies as _st

# Names injected into every ~property claim namespace.
# Authors who declare ~property-testing hypothesis do not need to
# import these; the binding provides them.
_HYPOTHESIS_NS: dict = {
    "given":       hypothesis.given,
    "settings":    hypothesis.settings,
    "assume":      hypothesis.assume,
    "note":        hypothesis.note,
    "target":      hypothesis.target,
    "HealthCheck": hypothesis.HealthCheck,
    "Phase":       hypothesis.Phase,
    "Verbosity":   hypothesis.Verbosity,
    "st":          _st,
    "strategies":  _st,
}

from notlob.graph import (
    claim_address, module_address, property_address, subheading_address,
)
from notlob.model import Claim, Module, Subheading, TestsSection, TestGroup
from notlob.bindings.python.assemble import assemble


class Status(Enum):
    PASS  = auto()
    FAIL  = auto()
    ERROR = auto()


@dataclass(frozen=True)
class ClaimResult:
    """The outcome of evaluating one assertion line.

    address  Claim address: containing_addr#example#n
    line     The source assertion text (without leading 'assert ')
    status   PASS, FAIL, or ERROR
    left     Evaluated left-hand side  (FAIL only; None otherwise)
    right    Evaluated right-hand side (FAIL only; None otherwise)
    error    Exception raised          (ERROR only; None otherwise)
    """
    address: str
    line:    str
    status:  Status
    left:    Any           = None
    right:   Any           = None
    error:   Exception | None = None


def run_examples(module: Module) -> list[ClaimResult]:
    """Run all ~example claims in a module and return results.

    Assembly errors (syntax errors in code blocks, import failures,
    etc.) produce a single ERROR result with address equal to the
    module address and line '<assembly>'.
    """
    ns: dict = {}
    mod_addr = module_address(module.title)

    try:
        exec(assemble(module), ns)
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


def run_tests(module: Module) -> list[ClaimResult]:
    """Run all assertions in the #Tests section and return results.

    Assertions under a named ## group get an address of the form
    <module>#Tests#<group>.  Bare assertions outside any group use
    <module>#Tests.

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

    ns: dict = {}
    mod_addr = module_address(module.title)

    try:
        exec(assemble(module), ns)
    except Exception as exc:
        return [ClaimResult(
            address=mod_addr,
            line="<assembly>",
            status=Status.ERROR,
            error=exc,
        )]

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


def run_properties(module: Module) -> list[ClaimResult]:
    """Run all ~property claims in a module and return results.

    Each claim block is exec'd into a fresh copy of the assembled
    module namespace, isolating the ephemeral witness function from
    the module's permanent state.  The property-testing library
    (Hypothesis) drives execution when the decorated function is called.

    Named properties (`~property name`) use the sigil name as address.
    Unnamed properties use an ordinal: <containing>#property#n.

    Assembly errors produce a single ERROR result as with run_examples.
    """
    ns: dict = {}
    mod_addr = module_address(module.title)

    try:
        exec(assemble(module), ns)
    except Exception as exc:
        return [ClaimResult(
            address=mod_addr,
            line="<assembly>",
            status=Status.ERROR,
            error=exc,
        )]

    results: list[ClaimResult] = []

    _run_props_in(module.body, mod_addr, ns, results)

    for item in module.body:
        if isinstance(item, Subheading):
            sub_addr = subheading_address(mod_addr, item.title)
            _run_props_in(item.body, sub_addr, ns, results)

    return results


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
            addr = property_address(containing_addr, parts[1].strip())
        else:
            addr = claim_address(containing_addr, "property", prop_n)

        claim_ns = dict(module_ns)
        claim_ns.update(_HYPOTHESIS_NS)
        try:
            exec(textwrap.dedent("\n".join(item.lines)), claim_ns)
        except Exception as exc:
            results.append(ClaimResult(
                address=addr,
                line="<property-exec>",
                status=Status.ERROR,
                error=exc,
            ))
            continue

        callable_ = _find_property_callable(claim_ns, module_ns)
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
) -> Any:
    """Return the property callable from claim_ns, or None.

    Prefers '_' (the anonymous-witness convention); otherwise returns
    the first new callable not present in module_ns or _HYPOTHESIS_NS
    (the binding-injected names are excluded from consideration).
    """
    baseline = set(module_ns) | set(_HYPOTHESIS_NS)
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
