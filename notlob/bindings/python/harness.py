"""notlob.bindings.python.harness — self-contained subprocess harness
scripts for the Python claim runner.

Each ``build_*_harness`` function returns a complete, standalone Python
source string with no dependency on notlob itself being importable in
the interpreter that runs it -- it is written to a temp file and
executed with whatever interpreter ``_resolve_python_interpreter``
(see runner.py) finds on the caller's ``PATH``, not notlob's own
interpreter. That's the whole point: notlob may be installed in its
own isolated environment (pipx, uvx, a separate tool venv) while the
module under test imports third-party libraries that only exist in the
*target* project's environment. This is why the FAIL-side extraction
logic and the CLAIM/PASS/FAIL/ERROR protocol emitter are emitted as
literal source text here rather than imported from
``notlob.bindings.python.runner`` -- the target interpreter may not
have notlob installed at all.

Output protocol
----------------
One CLAIM line per assertion, immediately followed by its result::

    CLAIM\\t<addr>\\t<source_line_or_empty>\\t<expr_repr>
    PASS

    CLAIM\\t<addr>\\t<source_line_or_empty>\\t<expr_repr>
    FAIL\\t<lhs_repr>\\t<rhs_repr>

    CLAIM\\t<addr>\\t<source_line_or_empty>\\t<expr_repr>
    ERROR\\t<exc_type>\\t<exc_message_repr>

*expr_repr* is deliberately the last field on the CLAIM line: the
parser splits with a fixed ``maxsplit``, so it safely absorbs anything
after the third tab as-is. Every ``_repr`` field is ``repr()`` of the
underlying string (not the raw text) and must be decoded with
``ast.literal_eval`` on the receiving end -- both *expr* (a multi-line
assertion, once dedented and rejoined, legitimately contains embedded
newlines) and an exception's message can contain a raw newline or tab,
which would otherwise split one logical CLAIM/result line into several
and corrupt the one-record-per-line protocol. Mirrors
``notlob.bindings.haskell.runner``'s own ``CLAIM\\t<addr>\\t<expr>``
line for the *last-field-absorbs-tabs* trick, but goes one step further
by also handling embedded newlines, which Haskell's runner does not
need to since it documents multi-line assertions as unsupported ("v1"
limitation) -- notlob's Python assertions can genuinely span multiple
source lines (see ``_is_complete`` in runner.py), so this harness has
to handle it correctly, not just assume single-line input.

If the module code raises while loading, the harness prints a single
ERROR record with no preceding CLAIM line -- the caller (``runner.py``)
detects this by an empty/CLAIM-less stdout and reports it as the
``<assembly>`` error, matching the previous in-process behaviour.
"""

from __future__ import annotations

# ── Shared preamble: emitted into every harness ─────────────────
#
# Names are deliberately `_notlob_`-prefixed so they don't collide with
# anything the module under test defines -- mirrors the Haskell
# runner's `_notlobCheck` naming.

_CHECK_HELPER = '''\
import ast as _notlob_ast


def _notlob_extract_sides(_notlob_expr, _notlob_ns):
    try:
        _notlob_tree = _notlob_ast.parse(_notlob_expr, mode="eval")
        _notlob_node = _notlob_tree.body
        if (
            isinstance(_notlob_node, _notlob_ast.Compare)
            and len(_notlob_node.ops) == 1
            and isinstance(_notlob_node.ops[0], _notlob_ast.Eq)
        ):
            _notlob_l = eval(_notlob_ast.unparse(_notlob_node.left), _notlob_ns)
            _notlob_r = eval(
                _notlob_ast.unparse(_notlob_node.comparators[0]), _notlob_ns
            )
            return _notlob_l, _notlob_r
    except Exception:
        pass
    return None, None


def _notlob_check(_notlob_addr, _notlob_sl, _notlob_expr, _notlob_ns=None):
    # _notlob_expr and any exception message are repr()'d before
    # printing -- both can legitimately contain embedded newlines (a
    # multi-line assertion; a multi-line exception message), and a raw
    # newline in a print() argument would split one CLAIM/result line
    # into several, corrupting the one-line-per-record protocol. The
    # parser reverses this with ast.literal_eval, same trick as the
    # FAIL line's lhs/rhs already used.
    if _notlob_ns is None:
        _notlob_ns = globals()
    _notlob_sl_text = "" if _notlob_sl is None else str(_notlob_sl)
    print(
        "CLAIM\\t" + _notlob_addr + "\\t" + _notlob_sl_text
        + "\\t" + repr(_notlob_expr)
    )
    try:
        exec("assert " + _notlob_expr, _notlob_ns)
        print("PASS")
    except AssertionError:
        _notlob_l, _notlob_r = _notlob_extract_sides(_notlob_expr, _notlob_ns)
        print("FAIL\\t" + repr(_notlob_l) + "\\t" + repr(_notlob_r))
    except Exception as _notlob_exc:
        print(
            "ERROR\\t" + type(_notlob_exc).__name__
            + "\\t" + repr(str(_notlob_exc))
        )
'''


def _check_calls(assertions: list[tuple[str, str, int | None]]) -> str:
    """Return the literal ``_notlob_check(...)`` call sequence for
    *assertions* (a list of ``(addr, expr, source_line)`` triples)."""
    return "\n".join(
        f"_notlob_check({addr!r}, {sl!r}, {expr!r})"
        for addr, expr, sl in assertions
    )


def _fallback_path_snippet(site_packages: str) -> str:
    """Return a snippet appending *site_packages* to ``sys.path`` as a
    last-resort fallback for ``pytest``/``hypothesis``.

    Appended, not prepended: Python always searches the target
    interpreter's own locations first, so a project with its own
    pinned ``pytest``/``hypothesis`` keeps using it unchanged, and this
    only matters when the target has neither at all -- see
    ``notlob.bindings.python.runner._notlob_site_packages``.
    """
    return (
        "import sys as _notlob_sys\n"
        f"_notlob_sys.path.append({site_packages!r})"
    )


def build_examples_harness(
    module_source: str,
    assertions: list[tuple[str, str, int | None]],
) -> str:
    """Return a standalone script: module code, then one CLAIM per
    ``~example``/``#Tests`` assertion in *assertions* (module scope,
    no injected namespace -- ``~example`` claims never needed one)."""
    parts = [_CHECK_HELPER, module_source, _check_calls(assertions)]
    return "\n\n".join(p for p in parts if p) + "\n"


def build_tests_harness(
    module_source: str,
    assertions: list[tuple[str, str, int | None]],
    notlob_site_packages: str | None = None,
) -> str:
    """Return a standalone script for ``#Tests`` assertions.

    ``pytest`` is imported and its ``approx``/``raises`` helpers bound
    *after* the module's own code, matching the previous in-process
    behaviour where namespace injection happened after ``exec``: if the
    module itself defines a name called ``approx`` or ``raises``, the
    injected pytest helper wins, same as before.

    *notlob_site_packages*, when given, is appended to ``sys.path``
    before anything else runs, so ``import pytest`` succeeds even if
    the target interpreter has no ``pytest`` of its own -- see
    ``_fallback_path_snippet``.
    """
    pytest_import = (
        "import pytest as _notlob_pytest\n"
        "pytest = _notlob_pytest\n"
        "approx = _notlob_pytest.approx\n"
        "raises = _notlob_pytest.raises"
    )
    parts = [_CHECK_HELPER]
    if notlob_site_packages is not None:
        parts.append(_fallback_path_snippet(notlob_site_packages))
    parts += [module_source, pytest_import, _check_calls(assertions)]
    return "\n\n".join(p for p in parts if p) + "\n"


# ── Properties ───────────────────────────────────────────────────

_PROPERTY_HELPER = '''\
def _notlob_find_property_callable(_notlob_claim_ns, _notlob_baseline):
    _notlob_new = {
        k: v for k, v in _notlob_claim_ns.items()
        if k not in _notlob_baseline
        and callable(v)
        and not k.startswith("__")
    }
    if not _notlob_new:
        return None
    return _notlob_new.get("_") or next(iter(_notlob_new.values()))


def _notlob_run_property(_notlob_sigil, _notlob_claim_ns, _notlob_baseline):
    _notlob_callable = _notlob_find_property_callable(_notlob_claim_ns, _notlob_baseline)
    if _notlob_callable is None:
        print("ERROR\\tValueError\\t" + repr("no callable found in ~property block"))
        return
    try:
        _notlob_callable()
        print("PASS")
    except Exception as _notlob_exc:
        print(
            "FAIL\\t" + type(_notlob_exc).__name__
            + "\\t" + repr(str(_notlob_exc))
        )
'''

_HYPOTHESIS_IMPORT = (
    "import hypothesis as _notlob_hyp\n"
    "import hypothesis.strategies as _notlob_st\n"
    "given = _notlob_hyp.given\n"
    "settings = _notlob_hyp.settings\n"
    "assume = _notlob_hyp.assume\n"
    "note = _notlob_hyp.note\n"
    "target = _notlob_hyp.target\n"
    "HealthCheck = _notlob_hyp.HealthCheck\n"
    "Phase = _notlob_hyp.Phase\n"
    "Verbosity = _notlob_hyp.Verbosity\n"
    "st = _notlob_st\n"
    "strategies = _notlob_st"
)


def build_properties_harness(
    module_source: str,
    properties: list[tuple[str, str, int | None, str]],
    notlob_site_packages: str | None = None,
) -> str:
    """Return a standalone script for ``~property`` claims.

    *properties* is a list of ``(addr, sigil, source_line,
    prop_block_source)`` tuples -- *sigil* fills the CLAIM protocol's
    *expr* field, matching the Haskell runner's own convention of using
    the sigil text as a property claim's "expression". Each property
    block execs into its own fresh copy of the post-module,
    post-hypothesis-injection namespace -- isolating the ephemeral
    witness function from the module's permanent state and from any
    other property's witness, matching the previous in-process
    ``dict(module_ns)`` copy-per-claim behaviour. A FAIL line here
    carries ``(exc_type, exc_message)``, not ``(lhs_repr, rhs_repr)`` --
    a property has no natural left/right sides -- so it must be parsed
    differently from an ``~example``/``#Tests`` FAIL line.

    *notlob_site_packages*, when given, is appended to ``sys.path``
    before anything else runs, so ``import hypothesis`` succeeds even
    if the target interpreter has no ``hypothesis`` of its own -- see
    ``_fallback_path_snippet``.
    """
    baseline_capture = "_notlob_baseline = set(globals())"
    parts = [_CHECK_HELPER, _PROPERTY_HELPER]
    if notlob_site_packages is not None:
        parts.append(_fallback_path_snippet(notlob_site_packages))
    parts += [module_source, _HYPOTHESIS_IMPORT, baseline_capture]

    for addr, sigil, sl, prop_source in properties:
        sl_text = "" if sl is None else str(sl)
        block = (
            f'print("CLAIM\\t" + {addr!r} + "\\t" + {sl_text!r} + "\\t" + {sigil!r})\n'
            f"_notlob_claim_ns = dict(globals())\n"
            f"try:\n"
            f"    exec({prop_source!r}, _notlob_claim_ns)\n"
            f"except Exception as _notlob_exc:\n"
            f'    print("ERROR\\t" + type(_notlob_exc).__name__'
            f' + "\\t" + repr(str(_notlob_exc)))\n'
            f"else:\n"
            f"    _notlob_run_property({sigil!r}, _notlob_claim_ns, _notlob_baseline)"
        )
        parts.append(block)

    return "\n\n".join(p for p in parts if p) + "\n"
