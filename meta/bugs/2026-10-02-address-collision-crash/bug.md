# A subheading/symbol name collision crashes instead of reporting an error

**Component:** name-graph construction (`notlob/graph.py` `add_node`, reached
via `enrich` → `_add_symbols`).
**Found by:** notlob-vids (`src/graph.lob`, where the colliding subheading
was renamed `##Assembly` as a workaround), reported via Adam.
**Status:** open, not fixed. Root cause confirmed and reproduced
independently; call-site survey started but not completed.

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

## Investigation so far

The message text in the `ValueError` is already good — the bug is purely
in the delivery (uncaught exception, no source lines, no exit-code
discipline). Call sites that would all need to catch this consistently
(found by searching `enrich(`/`build_package(` across the codebase, same
survey technique used earlier for an unrelated `~ignore` feature
discussion): `commands.py:217` (`_build_ref_graph`, used by `cmd_test`),
`project.py:234` (`build_package`, used by `cmd_graph`, `cmd_check`, and
the advisory-check paths inside `cmd_test`/`cmd_build`), and
`commands.py:1039` (`cmd_graph`'s single-file path). Not yet decided:
whether to catch at each call site individually, or give `NameGraph` a
non-raising variant / have `enrich`/`build_package` wrap the call once
and translate to a structured error type that every caller already knows
how to print (mirroring the existing `ERROR  <parse>`/`ERROR  <address>`
conventions elsewhere in `commands.py`). Not started: the actual fix.
