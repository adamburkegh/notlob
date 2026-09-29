# MRE: spurious ruff I001 from `#References` imports

See `notlob-i001-references-blank-line-bug.md` (in the parent scratch
directory) for the full write-up. Quick reproduction:

```
notlob test example.lob
```

Fails with `LINT example I001: Import block is un-sorted or un-formatted`
even though the single import is trivially well-formed. This is caused
by the assembler inserting only one blank line between the
`#References`-declared imports and the module body's leading `def`,
where ruff/isort require two.

`example2.lob` is the same module with the import moved into the body
instead, where the author can supply the second blank line manually —
it passes cleanly, demonstrating the workaround (and that this isn't
a real code quality issue, just an assembler spacing bug).

Verify the assembled source directly:

```
notlob test example.lob --keep-generated-src gensrc
```

then inspect the tail of `gensrc/_examples.py`.
