Both confirmed from the packaged MRE directory itself.

**Deliverables:**
- MRE project: [`notlob-i001-mre/`](notlob-i001-mre/) (`binding.lob`, `example.lob` —
  triggers the bug, `example2.lob` — the workaround, `README.md`)

Summary of what I verified (deviating slightly from the original description, which turned out to be self-referential in one spot):

- The failure is real and isolated: a single, correctly-formed `import math` in `#References`, module body starting with a top-level `def`, triggers `I001` even with only one lint finding and nothing else wrong.
- Root cause confirmed via `--keep-generated-src`: the assembler puts exactly **one** blank line between the `#References` import block and the following `# modname` comment / `def`, where ruff/isort require two.
- The documented workaround (move the import into the body) only works if you *also* remember to put two blank lines before the `def` yourself — I initially got the same false failure there too, then fixed it, which itself demonstrates the bug is purely about assembler-controlled spacing, not import content.
- One side note not in your original description: writing `#References` in a module's own prose (even just mentioning the section name) gets parsed as a live cross-reference and fails with "unresolved reference #References" — unrelated to this bug, so I avoided that phrasing in the MRE prose.

Let me know if you'd like this filed to a specific tracker rather than left as local files.

---

**Resolved:** 2026-08-12, commit `b3ccabf` — the assembler now puts two
blank lines at every assembler-inserted chunk boundary instead of one,
matching PEP8/isort's convention for top-level definitions.

A follow-up regression surfaced 2026-09-30 (a module opening with a
plain top-level statement rather than a `def`/`class`, e.g. a constant
assignment, was flagged `I001` the *opposite* way — the fix above
always inserted two blank lines, but isort wants only one there unless
what follows is a definition) and was fixed same-day in commit
`8928f37`: the gap right after `#References` is now dynamic, matching
isort's own rule; every other assembler-inserted boundary is
unaffected and stays at two blank lines unconditionally.
