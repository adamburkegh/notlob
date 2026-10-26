"""The rules for `#References`, as properties over generated projects.

DESIGN.md, "Listing, citing and loading": a listing says a module is in
conversation with another; its code is loaded only when the listing
module's code uses a name the other defines (it *needs* it). Listings may
be circular; a cycle of need is an error.

Each generated project has N modules `M0..M{n-1}`. `Mi` defines `fi()`
returning `i`, and a module-level `Vi` computed from the `fj()` it uses,
so a dependency loaded after (or not at all) is an observable failure,
not a guess. `uses` is acyclic by construction (`Mi` uses only `Mj`,
j < i); `extra` is any other listing, so listings are free to be circular
while need is not.

meta/bugs/2026-10-22-mutual-references/bug.md
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings, strategies as st

from kitcalls import building, dependency_modules, in_project
from notlob import from_tree, parse_file
from notlob.bindings import Status
from notlob.bindings.python import build_python as _build_python, kit
from notlob.bindings.python.runner import run_examples as _run_examples

run_examples = in_project(_run_examples, kit, "EXAMPLE")
build_python = building(_build_python, kit)

_BINDING = "#B\n\n---\n\n#Binding\n    ~language python\n"


@st.composite
def projects(draw):
    n = draw(st.integers(min_value=2, max_value=5))
    uses = [set() if i == 0 else
            draw(st.sets(st.integers(min_value=0, max_value=i - 1)))
            for i in range(n)]
    extra = [
        draw(st.sets(st.integers(min_value=0, max_value=n - 1)
                     .filter(lambda j, i=i: j != i))) - uses[i]
        for i in range(n)
    ]
    return n, uses, extra


def _source(i: int, uses: set[int], extra: set[int]) -> str:
    cites = ", ".join(f"#M{j}" for j in sorted(extra))
    prose = f"Cites {cites}." if cites else "Cites nothing."
    expr = " + ".join(f"f{j}()" for j in sorted(uses)) or "0"
    listed = sorted(uses | extra)
    refs = "".join(f"    #M{j}\n" for j in listed)
    text = (
        f"#M{i}\n\n{prose}\n\n"
        f"    def f{i}() -> int:\n        return {i}\n\n"
        f"    V{i} = {expr}\n\n"
        f"~example\n    V{i} == {sum(uses)}\n"
    )
    if refs:
        text += f"\n---\n\n#References\n{refs}"
    return text


def _write(root: Path, n: int, uses, extra) -> None:
    (root / "binding.lob").write_text(_BINDING, encoding="utf-8")
    for i in range(n):
        (root / f"m{i}.lob").write_text(
            _source(i, uses[i], extra[i]), encoding="utf-8")


def _closure(i: int, uses) -> set[int]:
    """What `Mi` needs: its uses, and theirs, transitively."""
    seen: set[int] = set()
    todo = list(uses[i])
    while todo:
        j = todo.pop()
        if j not in seen:
            seen.add(j)
            todo += uses[j]
    return seen


def _loaded(root: Path, i: int) -> list[int]:
    module = from_tree(parse_file(root / f"m{i}.lob"))
    return [int(m.title[1:])
            for m in dependency_modules(module, root, kit)]


_cheap = settings(
    max_examples=60, deadline=None,
    suppress_health_check=list(HealthCheck),
)
_runs = settings(
    max_examples=12, deadline=None,
    suppress_health_check=list(HealthCheck),
)


class TestLoadingFollowsNeed:
    @_cheap
    @given(projects())
    def test_exactly_what_is_needed_is_loaded_once_and_in_order(
        self, project,
    ):
        """Properties 1, 2, 4, 7: whatever the listings are, the loaded
        set is exactly the transitive uses; each appears once; each comes
        after everything it uses."""
        n, uses, extra = project
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, n, uses, extra)
            for i in range(n):
                loaded = _loaded(root, i)
                assert len(loaded) == len(set(loaded))
                assert set(loaded) == _closure(i, uses)
                for position, j in enumerate(loaded):
                    assert all(
                        loaded.index(k) < position
                        for k in uses[j] if k in loaded
                    )

    @_cheap
    @given(projects())
    def test_a_citation_never_changes_what_is_loaded(self, project):
        """Property 3, metamorphic: the same project with every extra
        listing and citation removed loads exactly the same."""
        n, uses, extra = project
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, n, uses, extra)
            with_citations = [_loaded(root, i) for i in range(n)]
            _write(root, n, uses, [set() for _ in range(n)])
            assert [_loaded(root, i) for i in range(n)] == with_citations

    @_runs
    @given(projects())
    def test_every_module_runs_and_builds_with_what_it_needs(
        self, project,
    ):
        """Properties 1 and 11: running a module passes (so the code it
        needs was loaded, in order), and its built artifact has exactly
        the code that run had."""
        n, uses, extra = project
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, n, uses, extra)
            for i in range(n):
                path = root / f"m{i}.lob"
                module = from_tree(parse_file(path))
                results = run_examples(module, file_path=path)
                assert [r.status for r in results] == [Status.PASS], results
                built = build_python(module, path)
                for j in range(n):
                    present = f"def f{j}()" in built
                    assert present == (j == i or j in _closure(i, uses))
