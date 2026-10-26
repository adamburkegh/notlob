# Slice 2b brief: `check.py` reads the graph through accessors

**For:** an implementing session. **Written by:** the design session,
2026-10-24. **Design:** `design.md` in this directory, sections 1 and 2,
and slice 2b in section 9.

## Goal

Slice 2c will change how the name-graph holds a document: prose and code
become nodes of their own, `DEFINES` goes, and a module's `CONTAINS`
children will include its paragraphs and claims, not only its
subheadings. `notlob/check.py` reads today's representation directly, so
it would break. Put a small set of `NameGraph` methods between them now,
implemented over **today's** representation, and move `check.py` onto
them. In 2c only the methods' insides change.

No output changes: every check finds exactly what it finds today.

## Rules

* **Touch only `notlob/graph.py`, `notlob/check.py` and
  `tests/test_graph.py`**, plus one new test (below) wherever it fits
  best among the existing check tests. Not `commands.py`, the MCP server,
  the schemas or the export: they change in 2c.
* **Add methods; do not change the representation.** `build`, `enrich`,
  the content dicts, the edges and the export stay as they are.
* **No existing test changes.** The check tests
  (`tests/test_check.py`, `tests/test_cli_check_json.py`) are the proof
  that behaviour did not change.
* **Failing test first** for the new methods; say in your report that
  you did.
* **Do not commit or stage.** 80-character lines. No phase or slice
  wording in code or docstrings.
* If a check needs something the methods below do not give, stop and
  report rather than adding a method of your own design.

## Where `check.py` reads the representation today

```
check.py:90, 92    node.address.split("#")[0]          module of a node
check.py:121, 325  node.address.split("#", 1)[0]       module of a node
check.py:338-344   mod_node.content["prose"], and child.content["prose"]
                   for graph.children(mod_node.address) of kind SUBHEADING
check.py:375       (node.content or {}).get("bullet_block_count", 0)
check.py:488       (node.content or {}).get("prose")
check.py:493       graph.children(node.address, EdgeKind.DEFINES),
                   filtered to EXAMPLE and PROPERTY
check.py:530-538   mod_root + "#" prefixes, e.source.startswith(...),
                   and graph._edges (private)
```

## The methods

All on `NameGraph`, each with a short docstring saying what it returns,
not how. Today's implementation in brackets.

| Method | Returns | Today |
|---|---|---|
| `module_of(address) -> str \| None` | the address of the module a node belongs to; `None` for an `EXTERNAL` node or an unknown address | the part of the address before the first `#` |
| `edges(kind=None) -> Iterator[Edge]` | every edge, or every edge of *kind*, in insertion order | `self._edges` |
| `sections(module_address) -> list[Node]` | the module's sections, in document order | its `CONTAINS` children of kind `SUBHEADING` |
| `prose(address) -> str` | the prose written directly in the module or section (paragraphs and bullet items, references with their sigils; not its subsections'); `""` if none | `content["prose"]` |
| `bullet_list_count(address) -> int` | the number of bullet lists directly in it | `content["bullet_block_count"]` |
| `claims(address) -> list[Node]` | the claims (`EXAMPLE`, `PROPERTY`, `RUN`) written directly in it, in document order | its `DEFINES` children of those kinds |

`sections` returns subheadings only, because that is what the graph has
today; when 2c gives the `#Appendix` a node it will return those too, and
`check_references` will start reading Appendix prose. That is intended,
and is 2c's change to report, not this slice's.

## `check.py` afterwards

```python
# coverage_summary, check_typos, check_references
mod = graph.module_of(node.address)

# check_references
prose_parts = [graph.prose(mod_node.address)]
prose_parts += [graph.prose(s.address)
                for s in graph.sections(mod_node.address)]
prose = " ".join(p for p in prose_parts if p)

# check_style
n = graph.bullet_list_count(node.address)

# check_quantifier
prose = graph.prose(node.address)
has_claim = any(c.kind in (NodeKind.EXAMPLE, NodeKind.PROPERTY)
                for c in graph.claims(node.address))

# check_imports
used = any(graph.module_of(e.source) == mod_root
           and graph.module_of(e.target) == dep_root
           for e in graph.edges()
           if e.kind in (EdgeKind.USES, EdgeKind.REFERENCES))
```

Keep each check's logic and messages exactly as they are; only the reads
change. `check_typos`'s `mod.rsplit("/", 1)` (sibling packages, from the
module address) is about packages, not nodes, and stays.

## The tests

1. **The methods**, in `tests/test_graph.py`: each on a small module
   built with `build` and `enrich` (the file has `graph_of` and
   `_enriched` helpers), including the empty cases (`""`, `0`, `[]`,
   `None` for an `EXTERNAL` node or an unknown address), a section with
   two bullet lists, a module with prose both at its top and in a
   subheading (`prose` of the module must not include the subheading's),
   and claims in document order across `~example`, `~property` and
   `~run`.
2. **A guard**, so the next change to the representation cannot be read
   around: a test that reads the source of `notlob.check` (for example
   with `inspect.getsource`) and fails if it contains `.content`,
   `EdgeKind.DEFINES`, `EdgeKind.CONTAINS`, `._edges`, `split("#"` or
   `+ "#"`. Name it for what it protects: the checks read the graph only
   through its public methods.

## When you are done

Stop and report, without committing:

1. The methods added, as signatures with their one-line docstrings.
2. That the new tests failed first, and why; then the full suite result
   (`notlobenv/Scripts/pytest`, through Bash).
3. A line-length check on the files you changed.
4. Anything you stopped on, and anything outside these files you think
   needs changing.

The design session reviews the diff against this brief before it goes to
Adam.
