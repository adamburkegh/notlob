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

from pathlib import Path

from notlob.bindings import BindingKit, collect_run_bodies
from notlob.bindings.haskell.assemble import assemble, assemble_with_deps
from notlob.bindings.haskell.lint import lint_haskell
from notlob.bindings.haskell.runner import (
    _load_dep_modules, run_examples, run_tests, run_properties,
)
from notlob.bindings.haskell.symbols import extract_calls, extract_symbols
from notlob.model import Module


def build_haskell(
    module: Module,
    file_path: Path | None = None,
) -> str:
    """Assemble *module* with inlined deps for the build command.

    Loads lob-ref dependencies from the project tree rooted at
    *file_path*, inlines their code before the module's own code, then
    appends the target module's own ``~run`` claim bodies so the
    artifact has an entry point when compiled/executed.

    ``~run`` (bare) and ``~run on-invocation`` are equivalent here and
    need no guard code: Haskell's ``import`` never executes ``IO``
    actions merely by loading a module (only ``main``, invoked by the
    compiled binary when it's actually run, ever does), so the
    language itself already guarantees on-invocation semantics for
    anything appended here.

    ``~run on-load`` has no meaningful translation to Haskell's
    execution model — there is no way to make code fire merely by
    being imported — so it raises rather than silently behaving like
    ``on-invocation`` (which would misrepresent what the author asked
    for) or silently doing nothing (which would misrepresent that the
    build succeeded with the requested behaviour intact).
    """
    dep_modules = _load_dep_modules(module, file_path)
    source = assemble_with_deps(module, dep_modules)

    on_load, on_invocation = collect_run_bodies(module)
    if on_load:
        raise ValueError(
            "~run on-load is not supported by the Haskell binding -- "
            "Haskell's `import` never executes IO actions merely by "
            "loading a module (only `main`, invoked by the compiled "
            "binary, ever runs), so \"run on load\" has no meaningful "
            "translation here. Use bare `~run` or `~run on-invocation` "
            "instead -- they're equivalent for this binding."
        )
    if on_invocation:
        source = source + "\n\n" + "\n\n".join(on_invocation)
    return source


#: The assembled Haskell binding kit.
kit = BindingKit(
    extract_symbols=extract_symbols,
    extract_calls=extract_calls,
    assemble=assemble,
    run_examples=run_examples,
    run_properties=run_properties,
    run_tests=run_tests,
    lint=lint_haskell,
    extension="hs",
    comment_prefix="--",
    build=build_haskell,
)

__all__ = [
    "kit", "extract_symbols", "assemble",
    "run_examples", "run_tests", "run_properties", "lint_haskell",
]
