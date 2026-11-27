# Examples

There are two kinds of example project listed here, small local ones and larger ones with their
own repository.



## In this repository

| Example | Binding | What it shows |
|---|---|---|
| [roman](roman) | Python | Roman numerals in a single module. The smallest place to start. |
| [haskell-roman](haskell-roman) | Haskell | Roman numerals with an executable entry point. The extended version of the example in the top-level README. |
| [retail](retail) | Python | Discount strategies for pricing. |
| [gutenberg](gutenberg) | Python | Word and speaker statistics for Hamlet, on a shared module for Project Gutenberg texts. |
| [ts-media](ts-media) | TypeScript | A browser visualisation, with analysis and DOM rendering in separate modules. |

The test suite finds each example by its `binding.lob`, so any folder added
here with a `binding.lob` will be run as part of the normal notlob build.

## Larger projects

These live in their own repositories and follow their own release cycles.
The test suite here doesn't run them, so the last column records which notlob
version each was last checked against, and how.

| Project | Binding | Size | What it shows | Last checked |
|---|---|---|---|---|
| [pn-chomper](https://github.com/adamburkegh/pn-chomper) | TypeScript | 12 modules; 19 examples, 16 properties, 2 runs | A browser puzzle game played on Petri nets, intended as casual fun and a learning aid. The largest set of properties, and a build hook that bundles the assembled code for the browser. | 0.6.0 |
| [pleiades](https://github.com/adamburkegh/pleiades) | Python | 3 modules; 8 examples, 2 properties | A published astronomical dating of Sappho's "Midnight Poem", reimplemented as a literate essay with alternative parameters. The closest to a paper that runs. | 0.6.0 |
| [notlob-vids](https://github.com/adamburkegh/notlob-vids) | Python | 10 modules; 50 examples, 3 properties, 2 runs, 1 test | Short animations about notlob, rendered with manim. Imports notlob as a library, and reads or runs real notlob projects (pn-chomper) at render time. | 0.6.0 |

Sizes are counted by `notlob graph` at each project's current main branch.

