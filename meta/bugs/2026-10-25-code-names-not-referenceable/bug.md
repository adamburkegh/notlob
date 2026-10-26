# A function cannot be referenced from prose

**Component:** the reference terminal `REF` in `notlob/grammar.lark`, and
`check_references` in `notlob/check.py`, which follows it.
**Found by:** the name-graph design discussion (D15/D16 in
`meta/features/2026-10-23-name-graph-as-parse-tree/design.md`),
2026-10-25. Adam: "not being able to reference a function from prose is
dumb. That leaked in."
**Status:** open. The fix is a language change and needs its own design
(D16).

## Summary

`DESIGN.md` says every named thing is first-class in prose: "`#NUMERALS`
in prose is a live cross-reference to the constant definition ... All
named things are first-class in prose." That holds for `NUMERALS` only
because it is upper case. The reference terminal requires a label to
start with a capital and to hold only letters, digits and `_`:

```
REF.5: /(?<![\w\/])##?[\p{Lu}\p{Lt}\p{Lo}][\p{L}\p{Nd}_]*(?:[ ][\p{Lu}\p{Lt}\p{Lo}][\p{L}\p{Nd}_]*)*/
```

So, in the Roman example and the three bindings' languages:

```
#to_roman     plain prose: lower-case start, not a reference
#foldl'       a reference to `foldl`, then the prose `'`   (Haskell)
#$el          plain prose                                   (TypeScript)
##Round-Trip  a reference to `Round`, then the prose `-Trip` (a heading)
```

`check_references` only considers symbols whose names start with an
upper-case letter (`_REFABLE = ^[A-Z][A-Za-z0-9_]*$`), which is the same
limit seen from the other side.

## How it leaked in

* `7fe2d0f` (2026-05-23), "Inline references in prose become first class
  objects": the first rule, in `parser.py`: "capital letter start,
  optional Title Case continuation". Its job was to tell a reference
  from an ordinary `#` in prose (`#5`, a hashtag) for headings, which
  are written in Title Case by convention.
* `82e5024` (2026-07-02), "Revisit grammar": the same rule moved into
  `grammar.lark` as `REF`, unchanged.
* `9fde779` (2026-08-11), "Unicode support in refs": the capital rule
  kept, applied only in scripts that have case.

Symbols became referenceable by the resolution order (symbol first, then
subheading, then module), but the terminal that decides what *is* a
reference was never revisited for them: a heading convention became a
limit on code names.

## Toward a fix (D16)

Code names follow the binding's identifier rules, which notlob should
not restate or narrow (D15, as narrowed). Some shapes, none decided:

* a quoted reference form for code names, such as ``#`to_roman` ``,
  whose inside the binding accepts or rejects;
* the binding supplying its identifier pattern to the lexer;
* relaxing `REF` itself, which would make `#5` and hashtags references
  again, the thing the Title Case rule was there to stop.

The hyphen case (`##Round-Trip`) is a document name, not a code name,
and belongs with D15's rules for document names.
