# A subheading/symbol name collision crashes instead of reporting an error

**Component:** name-graph construction (`notlob/graph.py` `add_node`, reached
via `enrich` → `_add_symbols`).
**Found by:** notlob-vids (`src/graph.lob`, where the colliding subheading
was renamed `##Assembly` as a workaround), reported via Adam.
**Status:** fixed, 2026-10-02.

## Summary

The rule being enforced is right: a module has one namespace, so a
`##Layout` subheading and a `class Layout` symbol can't share the address
`shapes#Layout`. But the violation comes out as an uncaught `ValueError`
with a full Python traceback, and the command dies, instead of a normal
reported error.

`NameGraph.add_node` (`graph.py:203-212`) raises a bare `ValueError` on a
kind mismatch at the same address:

```python
def add_node(self, node: Node) -> None:
    existing = self._nodes.get(node.address)
    if existing is not None and existing.kind != node.kind:
        raise ValueError(
            f"Address collision: {node.address!r} already "
            f"registered as {existing.kind.name}, "
            f"cannot add as {node.kind.name}. "
            f"All named things share one namespace per module."
        )
    self._nodes[node.address] = node
```

Nothing calling `enrich()`/`build_package()` catches this, so it propagates
all the way to the CLI as an unhandled traceback.

## Reproduction

binding.lob
```
#Collision Repro

---

#Binding
    ~language python
```

shapes.lob
```
#Shapes

A subheading and a class share the name Layout.

    class Layout:
        pass

##Layout

Placing shapes.

    def place():
        return Layout()

~example
    isinstance(place(), Layout)
```

Confirmed independently (fresh repro in a scratchpad, not notlob-vids'
actual project):

```
$ notlob test shapes.lob
Traceback (most recent call last):
  ...
  File ".../notlob/commands.py", line 429, in _test_module
    _build_ref_graph(module, root, extract_symbols), module
  File ".../notlob/commands.py", line 217, in _build_ref_graph
    enrich(graph, module, extract_symbols)
  File ".../notlob/graph.py", line 724, in enrich
    _add_symbols(graph, item, mod_addr, mod_addr, extractor)
  File ".../notlob/graph.py", line 886, in _add_symbols
    graph.add_node(Node(...))
  File ".../notlob/graph.py", line 206, in add_node
    raise ValueError(...)
ValueError: Address collision: 'shapes#Layout' already registered as
SUBHEADING, cannot add as SYMBOL. All named things share one namespace
per module.
```

`notlob graph shapes.lob` crashes with the identical traceback (same
`enrich()` call, via `build_package`). `notlob build --skip-tests
shapes.lob` succeeds, because building doesn't construct a full
name-graph at all — inconsistent with `test`/`graph`, which both do.

## Expected

A reported error rather than a crash:

```
ERROR  <names>  shapes: 'Layout' names both a subheading (shapes.lob:8)
and a symbol (shapes.lob:5) -- all named things share one namespace per
module
```

with exit code 1, no traceback. Presumably `build` should report it too,
since the module's addresses are ambiguous regardless of whether tests
run.

## Resolution

Added `AddressCollisionError` (`notlob/graph.py`) — a `ValueError`
subclass with structured fields (`address`, `existing_kind`, `new_kind`,
`existing_line`, `new_line`) — and made `NameGraph.add_node` raise it
instead of a bare `ValueError`. The message text was already good (per
the original report); the new version keeps it and adds line numbers
for both colliding nodes, since `Node.start_line` was already being
populated for both subheadings and symbols, just never surfaced:

```
Address collision: 'shapes#Layout' names both a subheading (line 8)
and a symbol (line 5) -- all named things share one namespace per
module.
```

A narrow, dedicated exception type (rather than reusing bare
`ValueError`) matters here specifically because every call site needs
to catch *this* condition without also swallowing an unrelated
`ValueError` from somewhere else in the same call chain.

Caught and reported (`ERROR  <names>  ...`, exit 1, no traceback) at
every place that builds a graph and could hit this: `_require_graph`
(covers `cmd_check` and the `cmd_query_*` commands), `_run_check_advisory`
(covers `cmd_test`'s and `cmd_build`'s advisory-check paths),
`cmd_test`'s per-file `_build_ref_graph` call (the exact repro's own
path) and its project-mode `--json` path, and `cmd_graph`'s single-file
and project-mode `build_package` calls. `build`'s own behaviour
(succeeding today, since it doesn't construct a full name-graph) is
left as-is — a separate question from this crash, not addressed here.

Tests in `tests/test_address_collision.py`: the exception's own fields
and message; `cmd_test` on the exact repro shape (single file, and
confirming a sibling module's claims still run in project mode);
`cmd_test --json`'s `check_findings` output; `cmd_graph` (single-file
and project-mode); `cmd_check`. Sabotage-verified: removing the
`_build_ref_graph` catch reproduces the original crash exactly (an
uncaught `AddressCollisionError` propagating through the same call
chain as the original report's traceback).
