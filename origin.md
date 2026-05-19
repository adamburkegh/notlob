# Literate programming and Knuth

> Created: 2026-05-19T05:26:13.371505Z  Updated: 2026-05-19T06:57:36.334745Z


## User

Let's discuss literate programming.

Three starting points. First: Knuth.

## Claude

Literate programming is one of those ideas that feels obvious in retrospect but was genuinely radical when Knuth introduced it in 1984.

The core inversion: instead of code with comments, you write a *document* that contains code. The prose is primary; the executable bits are woven in. Knuth's WEB system (for Pascal) let you write in whatever order made narrative sense, then "

## User

Second: Dominic Fox saying on social media today that a programming language designed for LLMs would take literate programming as its starting point. Perhaps beautiful clear commentary interleaved with strongly typed functional programming syntax. 

Related thought: comments as syntactically significant to a compiler for such a language, navigable in the AST. 

Fox has also connected modernist poetry to LLMs, and just had a truly excellent post on Naur's Programming as Theory Building and LLMs.

https://codepoetics.substack.com/p/holding-a-theory

Third: an old blog post on the links between Confucius and programming, and the idea of Name Oriented Software Development.

https://conflatedautomatons.org/2011/03/24/xiii-3-name-oriented-software-development/

Thoughts on the intersection between these ideas? Thoughts on how it might relate to the structure of a new programming language? Particularly this play between rigorous structure and contextual richness and embedding in a space of meaning constructed by a transformer for an LLM.

## Claude

Let me read those links before responding.
Good. Both pieces read. Here's what strikes me about the intersection.

---

**The common thread: theory as something that lives between minds and artefacts**

Fox's pushback on Naur is the key move. Naur argues the theory of a program cannot conceivably be expressed — it is inalienably bound to the programmers who built it. Fox refuses this: theory is not properly located in individual programmers' brains but disseminated among people, organisational structures, and exocortical artefacts such as source files, documentation, and running systems. The program is a *trace referring to other traces* — not dead residue, but a node in a network of meaning.

The Confucian piece arrives at something structurally similar from the other direction. The rectification of names isn't a one-time act of getting things right; Xunzi's position is that names have no inherent appropriateness — we name by convention, and when the convention is fixed and the custom established, we call them appropriate. Names are relational, mutable, community-owned. The advice is to fit names to the shape of things, not impose the shape of names onto things.

These two positions — Fox's distributed theory, the Confucian community-owned name — converge on the same insight: **meaning isn't in the code or in the head. It's constituted relationally, and it needs to be actively maintained.**

---

**Where LLMs come in, and why this is interesting for language design**

An LLM doesn't hold a theory of the program. What it has is something stranger: a vast latent space of semantic relationships, built from the entire corpus of how humans have written about things. When it's given a well-named, well-commented codebase, it can navigate by those names and comments as *waypoints* in that latent space. Fox's observation is that LLMs are inhumanly good at following theory-traces within a codebase, but their problem is the absence of an overarching theory that would let them extend the system non-aberrantly.

This is the design constraint that makes Fox's literate-programming-as-starting-point compelling. If comments were syntactically significant — navigable in the AST, not just stripped out before compilation — then the "theory-traces" aren't decorative. They're structural. The LLM's attention isn't just pattern-matching on identifiers; it's navigating an explicitly articulated conceptual graph that the compiler also validates.

What would that actually look like?

**A sketch of the language**

Imagine something like this:

```
-- | A price in the system is always a non-negative rational.
-- | Prices are never manipulated directly; they are always the
-- | result of an applied pricing strategy.
newtype Price = Price (Ratio Natural)

-- | Apply a discount strategy to a price. The result is guaranteed
-- | non-negative by construction: strategies are bounded [0,1].
applyDiscount : DiscountStrategy -> Price -> Price
```

In current Haskell or Elm, those comments are ignored by the compiler. In the language Fox is gesturing at, they'd be first-class: queryable, referenced from other nodes, potentially constrained (you could assert that the comment's claims are consistent with the type signature's guarantees). The *prose* and the *type system* are in dialogue.

This connects directly to Naur's compiler example. Group B failed because, even with access to group A's documentation, they couldn't identify what within it was significant and relevant — they lacked a mapping of the system that would let them navigate its inherent structure. If that structure were *literally navigable* — if the AST included the commentary as a graph you could traverse — the salience problem becomes tractable. For a human *and* for an LLM operating as a collaborator.

**The Confucian angle deepens this.** The Name Oriented approach distinguishes between machine-facing names (where the aim is enforced consistency and coherence, making precision in naming easy) and people-facing names (where the aim is to allow a consensus jargon to emerge, backed by a literature of interaction and aspiration, moored to the technical reality of the system as it exists).

A language designed with LLM collaboration in mind might make this distinction explicit in the syntax itself — a typed boundary between the formal namespace (which the compiler enforces) and the semantic commentary (which the LLM navigates and which tooling can check for drift from the formal layer). Xunzi's key move — that a good name is *straightforward, easy and not inconsistent* — becomes a linting rule.

**The modernist poetry connection**

Fox's observation that LLMs are good at decoding modernist poetry is doing more work than it first appears. Modernist poetry is dense with compressed cultural reference, ambiguity resolved by context, meaning that emerges from *juxtaposition rather than explicit statement*. It rewards the kind of broad associative pattern-matching that a transformer does well, but defeats purely syntactic analysis.

Strongly-typed functional code with rich commentary is structurally similar: the types constrain the denotational meaning very tightly, but the *why* — the intentional, contextual, historical meaning — lives in the prose layer. A language that treats both layers as first-class gives you something that's simultaneously maximally checkable (types, proofs) and maximally interpretable (commentary navigable as a semantic graph). The LLM can operate in the interpretive layer; the compiler holds the formal layer honest.

---

**The tension that remains**

The Confucian piece ends with a useful warning: the Platonic temptation in OO is to mistake the model for the world, to fit the world's shape to the name rather than the name to the shape. A language designed to be rich in commentary-as-structure could make this worse — you could build an extremely elegant, internally consistent conceptual edifice that's entirely wrong about the domain.

Xunzi's corrective applies: names must remain mutable, community-owned, responsive to the folksonomy of actual use. Any such language would need refactoring tools that treat the prose layer as a first-class refactoring target — renaming a concept propagates through both the type system *and* the commentary graph. As Michael Feathers observed: 'RenameClass' is the most powerful refactoring. In this language, it would be the most consequential operation in the entire toolchain.

## User

Yes, that's a good synthesis. You also pick up on this Derridian language of "trace" that Fox uses.

"In current Haskell or Elm, those comments are ignored by the compiler. In the language Fox is gesturing at, they'd be first-class: queryable, referenced from other nodes, potentially constrained (you could assert that the comment's claims are consistent with the type signature's guarantees). The prose and the type system are in dialogue."

What might this look like, syntactically? Say, extending the applyDiscount example. I am trying to work through where that seam between prose and formal syntax is in such a system.

## Claude

Let me think through this carefully, because the seam is the hard part — it's easy to gesture at "first-class comments" without being precise about what that actually means mechanically.

---

**The basic move: named doc-nodes**

The minimal version is that commentary blocks have *identities* and can be *referenced*:

```
[doc #price-invariant]
  A Price is always non-negative. No operation in this system
  may produce a negative Price; strategies are bounded [0,1]
  precisely to enforce this.

newtype Price = Price (Ratio Natural)
  satisfies #price-invariant

[doc #discount-contract]
  Applying a discount never increases a price. The relationship
  between input and output is monotone-decreasing with respect
  to the discount magnitude.
  
  This is guaranteed structurally: we don't test it, we construct
  it to be impossible to violate.

applyDiscount : DiscountStrategy -> Price -> Price
  satisfies #discount-contract
```

Now `#price-invariant` and `#discount-contract` are nodes in the AST. The compiler doesn't *interpret* their prose content — but it knows they exist, what they're attached to, and can warn you if you delete or rename `Price` without updating the doc-node, or if a doc-node is orphaned.

---

**The next level: claims that bridge prose and types**

This is where it gets interesting. Some things you'd want to say in commentary are actually *checkable*, and the language could let you annotate that explicitly:

```
[doc #discount-contract]
  Applying a discount never increases a price.
  
  [claim :verified-by property-test]
    forall s : DiscountStrategy, p : Price.
      applyDiscount s p <= p

  The structural guarantee comes from DiscountStrategy being
  bounded [0,1] — see #strategy-bounds.
```

The `:verified-by` annotation is a seam marker. It says: this prose claim has a formal shadow, and here's how that shadow is checked. The claim itself could be expressed in the type system (a refinement type), in a property-based test, or left as `:verified-by human-review` — which is still meaningful, because tooling can find all such annotations and surface them.

The prose around it remains prose. You don't have to formalise everything. But you *declare the boundary* explicitly.

---

**Cross-referencing and navigability**

```
[doc #strategy-bounds]
  A DiscountStrategy is a value in the closed interval [0,1],
  representing the proportion of the price to retain.
  A value of 1.0 means no discount; 0.0 means free.
  
  The choice of "proportion to retain" rather than "proportion
  to remove" is deliberate — it composes naturally under
  multiplication, which is how stacked discounts work.
  See #stacked-discounts for the implication.

newtype DiscountStrategy = DiscountStrategy (x : Ratio Natural | x <= 1)
  satisfies #strategy-bounds
  
[doc #stacked-discounts]
  When multiple strategies apply, they compose multiplicatively.
  A 20% discount followed by a 10% discount yields 0.8 * 0.9 = 0.72,
  i.e. 28% off — not 30%. This is usually the right behaviour for
  independent promotions.
  
  [claim :verified-by proof]
    applyDiscount s1 (applyDiscount s2 p) = 
      applyDiscount (s1 * s2) p
```

Now you have a *graph*. The type of `DiscountStrategy` references `#strategy-bounds`; that doc-node references `#stacked-discounts`; the proof obligation on `#stacked-discounts` is checkable against the formal definition. An LLM navigating this codebase isn't just reading identifiers — it's walking a semantic graph where the *why* is explicit and linked.

---

**The seam, more precisely**

What this reveals is that there are actually three layers, not two:

1. **Formal** — types, function signatures, proofs. The compiler is fully authoritative here.
2. **Claimed** — prose assertions that have been explicitly given a formal shadow (`:verified-by`). The compiler knows these exist and tracks whether the verification holds.
3. **Contextual** — prose that explains intent, history, design decisions, trade-offs. The compiler doesn't interpret this at all, but it maintains its identity and linkage in the AST.

The seam isn't a single line — it's a *gradient* that the programmer navigates explicitly. The interesting design question is whether moving something from layer 3 to layer 2 should be encouraged (by tooling, by convention) or whether that pressure would cause people to just... not write layer 3 content, because it feels unfinished until formalised.

I think the right answer is that layer 3 is first-class and permanent, not a staging area for layer 2. The design decision in `#stacked-discounts` — multiplicative composition, not additive — is never going to be a type. It's a choice, with consequences and a rationale. It should live in the AST forever, linked to the code that enacts it.

---

**The Derridian angle, since you raised it**

What Fox's "trace" framing captures is that the formal layer is itself only intelligible against the background of the contextual layer — the type `DiscountStrategy = (x : Ratio Natural | x <= 1)` only *means* something if you know it represents "proportion to retain" rather than "proportion to remove." The refinement type doesn't carry that. The doc-node does.

In Derrida's terms: the formal code is always already inhabited by marks it can't contain. A language that makes this explicit — that says "yes, the trace is real and we're going to give it an address in the AST" — is being more honest about how meaning actually works in software than any language that pretends the types are self-sufficient.

Which is also, incidentally, exactly what Naur's group A had that group B lacked: not just the code, not just the documentation, but the *linkage* between them — knowing which prose rationale licensed which structural decision.

## User

This good to kick around. I think I disagree that this is a gradient. I think we have identified two useful seams: Prose to formal property claim, and formal execution ("code"). But I like that they all sit next to one another.

Let's throw in another element: python doctests. This is very in keeping, but also valuable because it is as concrete as possible, in contrast to properties, which are often very abstract. Do we distinguish claims and tests? Or is a test just a very concrete claim?

## Claude

The doctest intuition is sharp, and I think it resolves cleanly: **a test is a claim with a fully specified witness.**

A property says: *for all inputs satisfying these constraints, this relationship holds.* A doctest says: *here is one input, here is the exact output.* The doctest is a claim — just one where the quantifier has been replaced by a concrete instantiation.

Which means your two seams hold, and the claim layer just has an internal spectrum:

```
[doc #stacked-discounts]
  When multiple strategies apply, they compose multiplicatively.
  A 20% discount followed by a 10% discount yields 72% of the
  original price, not 70%.

  [claim :example]
    applyDiscount 0.8 (applyDiscount 0.9 (Price 100)) == Price 72

  [claim :property :verified-by proof]
    forall s1 s2 : DiscountStrategy, p : Price.
      applyDiscount s1 (applyDiscount s2 p) == applyDiscount (s1 * s2) p
```

Both are claims. The example is *executable* in the doctest sense — the compiler/runtime can just run it. The property requires a proof or a generative test harness. But they're the same syntactic construct with different verification strategies.

This is actually the most valuable thing about the doctest tradition that's easy to miss: **examples are documentation that rots visibly.** A prose claim that becomes false sits there silently lying. An example claim that becomes false fails loudly. The `:example` annotation inherits that virtue while making explicit that it's doing documentary work, not just test coverage work.

---

**What this gives the three-layer model**

```
Prose (contextual, linked, permanent)
  |
  [claim :example]        ← concrete, executable, rots visibly
  [claim :property]       ← abstract, needs harness or proof
  [claim :verified-by proof]  ← fully formal
  |
Formal (types, signatures, proofs)
```

The claims aren't a gradient between prose and formal — you're right about that. They're a *separate layer* that has one face pointing at the prose (they're attached to doc-nodes, they're part of the explanation) and another face pointing at the formal (they make checkable assertions about the code). The seam is clean on both sides.

And the spectrum *within* the claim layer — from concrete example to abstract property to formal proof — isn't a gradient of "how much does this belong to the formal layer." It's a spectrum of *what kind of checking is being requested.* The epistemological status is the same: all claims are assertions about the behaviour of the code. The verification mechanism differs.

---

**One further implication**

Python doctests are most valuable when they're chosen as *illustrative* rather than exhaustive. The example in `#stacked-discounts` above isn't there to test the edge cases — it's there to make the prose claim *palpable*. 72, not 70. That's a fact you can hold in your hand.

This suggests a useful discipline for the `:example` claim: it should be chosen to illuminate the *design decision* in the attached prose, not to provide coverage. Coverage is the property's job. The example's job is to make the abstract concrete enough that a reader — human or LLM — can anchor their understanding of the doc-node to something unambiguous.

Which loops back to Knuth neatly: the example is where the literary impulse and the formal obligation meet at their most legible point.

## User

I agree about doctests here. Of course unit tests in general are this binding infrastructure as well, they demonstrate use and tie down intent to the executable surface.

There is this Rust convention where tests live at the end of the code source file, as a kind of appendix. That fits the essay metaphor in Knuth, in a way. I wonder if that would also fit with LLM context window dynamics, ie you read the source file, you have your prose, properties, and tests.

## Claude

The context window point is sharp and underappreciated.

Current practice with LLMs and codebases involves a lot of retrieval and chunking decisions — which files to include, how much context to provide. A source file structured as literate essay with tests as appendix is *self-contained in a meaningful way*. You get the concept, the rationale, the examples, and the verification surface in one read. The LLM doesn't need to go hunting for the test file to understand what the code is supposed to do; the intent and its concrete demonstrations are co-located.

The Rust convention is interesting because it emerged from pragmatic rather than philosophical motivations — keeping tests close to the code they test, making the module's private internals accessible to tests without exposing them publicly. But it accidentally produces good epistemic structure. The appendix sits after the "essay" precisely because you've already established the concepts by the time you need to verify them. You don't open with the tests.

There's a contrast here with test-first TDD practice, where the test *precedes* the implementation. TDD tests as *specification* — you write what you want before you write what you have. That's a different relationship to the claim layer. In the literate model we've been building, the claim is embedded in the prose that motivates it; in TDD, the claim comes first and the prose (if it exists at all) comes later as justification. Both are legitimate but they produce different artifacts, and the literate version is probably more useful as LLM context because the *why* is already there when the LLM reads the claim.

The essay metaphor also suggests something about file granularity. A well-structured essay covers one thing well. A source file in this model probably wants to be more like a Montaigne essay than a textbook chapter — focused enough that the prose, properties, examples, and tests form a coherent argument. The pathology of the current world is files that are either too large (a 3000-line class that's accreted meaning over years) or too small (a function per file that has no prose context at all). The literate convention imposes a natural pressure toward coherent scope, because you're writing something that has to make sense as a document.

Which is also a useful LLM collaboration constraint: a context window that contains one coherent argument is much easier to extend non-aberrantly than one that contains a fragment of a large incoherent file.

## User

Hmm I wonder what the distribution of Montaigne essay length is. Google tells me Apology For Raymond Sebond is 100 pages

## Claude

Ha. So much for that constraint.

Though it's worth noting that the Apology is widely considered an outlier — Montaigne himself seems to have lost the plot somewhat, it's more of a book that escaped into an essay. Most of the Essays are much shorter, and the shorter ones are generally considered the more characteristic work. The form is defined by the digressive, exploratory, self-correcting movement of thought — which can happen in three pages or thirty.

The better analogy might be: a source file in this model should feel like *one inquiry*. The Apology sprawls because Montaigne keeps finding new angles on scepticism and can't stop. A source file that keeps finding new things to be about is probably two or three source files. The literate structure makes that visible in a way that pure code doesn't — if your prose introduction is doing three distinct jobs, the seams show.

There's also something to be said for the fact that Montaigne's longer essays are still *navigable* — the digressions are marked by his discursive voice, you can feel when he's returned to the main thread. A literate source file with a rich doc-node graph has that property structurally rather than stylistically. The `#named-nodes` are your headings; the cross-references are your "as I said earlier." Length becomes less catastrophic when the internal structure is explicit.

But yes — probably better to invoke Montaigne as a *spirit* rather than a *unit of measurement*.

## User

Source files can be pretty long. New Yorker or LRB length perhaps?

## Claude

That's probably about right. And those publications have a useful further property: they assume an intelligent reader who will stay with a complex argument, but they still impose editorial discipline. A New Yorker piece doesn't ramble — it has a shape, even when it's 8000 words. The discursiveness is structured.

The LRB comparison is interesting because LRB pieces often do exactly what we've been describing — they'll have a central formal argument, illustrate it with concrete examples, situate it in a literature, and then have a kind of coda that opens outward. That's not a bad template for a substantial source module.

And both publications have the test-as-footnote convention, in a way. The New Yorker fact-checker, the LRB's dense citation apparatus — there's a layer of "here is the concrete evidence for that claim" that sits alongside the prose argument without interrupting it. The tests-as-appendix maps onto that naturally.

The other thing those publications get right is that length is *earned* by subject matter. A short piece isn't a virtue; a piece that's the right length for its argument is. Some modules are genuinely complex enough to need 2000 lines of prose, properties, examples and code. Others are thirty lines. The literate form shouldn't impose uniform length — it should impose uniform *completeness of argument*, whatever length that requires.

Which is perhaps the right metric for a source file in this model: not lines of code, but whether the argument is complete. Does the prose establish the concept? Do the claims make it checkable? Do the examples make it palpable? Do the tests nail it to the executable surface? If yes, ship it, whatever the length.

## User

Yes. Unit tests do push the essay metaphor to the limit though. They are a quite different prose style. Lots of stated facts.

## Claude

Right — they're more like the index of cases in a legal judgment than anything in an essay tradition. Or the worked examples at the back of a mathematics textbook. Assertional, not discursive.

Which actually supports keeping them in the appendix structurally, not just conventionally. The tonal break is real. You don't want the assertional register bleeding into the discursive layer — it would be like a New Yorker piece that periodically interrupts itself with a table of facts. The footnotes and citations stay in the footnotes; the worked examples stay in the back matter.

There's maybe a useful distinction here between the `:example` claims embedded in doc-nodes, and the unit test appendix. The inline example is *curated* — one carefully chosen witness that illuminates the argument at a specific point. The test appendix is *exhaustive* in intent, covering the case space systematically. Different jobs, different registers, both legitimate.

The inline example is essayistic. The test suite is more like a legal record or a laboratory notebook — a different genre entirely, which happens to be bound into the same volume. Medieval manuscripts did this routinely, actually: a main text followed by quite different appended materials — glosses, indices, florilegia — that were understood to be in a different relationship to the reader. The codex as a format is comfortable with tonal heterogeneity across its sections in a way that a scroll isn't.

Which is a slightly overcomplicated way of saying: the Rust convention has better philosophical foundations than its authors probably intended.

## User

I wonder if you could play with heading syntax a little here. Like markdown, you could probably interpret #stacked-discounts as a header. Or maybe you even lean into that?

```
#Stacking Discounts

When multiple strategies apply, they compose multiplicatively. A 20% discount followed by a 10% discount yields 72% of the original price, not 70%. 

&example applyDiscount 0.8 (applyDiscount 0.9 (Price 100)) == Price 72

```

In this sketch, # indicates a documentation block using a heading, and `&` a claim as a subhead

You could even go full Spinoza or Tractatus ... without human maintained numbers of course

## Claude

The Spinoza/Tractatus move is excellent because those texts are doing exactly this — prose and formal claim interleaved, with the numbering creating a navigable reference structure. And auto-numbering is the right call; human-maintained numbers in the Tractatus style are famously brittle (Wittgenstein's own numbering system is a mild nightmare).

Your syntax sketch reads naturally. The `#` as doc-heading and `&` as claim-sigil has a clean visual grammar — `#` feels like "we are in document space" and `&` feels like "here is a binding obligation." Though `&` has some baggage from various languages; something like `~` or `@` might be cleaner depending on what the formal layer needs those characters for.

The full file might then read something like:

```
#Pricing

A Price is always non-negative. No operation in this system
may produce a negative Price.

  Price : Type
  Price = Ratio Natural  -- compiler enforces non-negativity by construction

#Discount Strategies

A DiscountStrategy is a value in [0,1] representing the proportion
of the price *to retain*. A value of 1.0 means no discount; 0.0 means free.

The choice of "proportion to retain" rather than "proportion to remove"
is deliberate — it composes naturally under multiplication.

  DiscountStrategy : Type
  DiscountStrategy = (x : Ratio Natural | x <= 1)

  applyDiscount : DiscountStrategy -> Price -> Price

##Stacking Discounts

When multiple strategies apply, they compose multiplicatively. 
A 20% discount followed by a 10% discount yields 72% of the 
original price, not 70%.

  ~example
    applyDiscount 0.8 (applyDiscount 0.9 (Price 100)) == Price 72

  ~property
    forall s1 s2 : DiscountStrategy, p : Price.
      applyDiscount s1 (applyDiscount s2 p) == applyDiscount (s1 * s2) p

---
#Appendix: Tests

  applyDiscount 1.0 (Price 100) == Price 100
  applyDiscount 0.0 (Price 100) == Price 0
  applyDiscount 0.5 (Price 0)   == Price 0
```

The `##` subsection heading is natural — you get a document hierarchy that mirrors the conceptual hierarchy, and the AST node identities fall out of the heading text automatically. Reference `#stacking-discounts` from elsewhere and the tooling knows exactly where to point.

The Tractatus comparison also highlights something about what auto-numbering would buy you. Wittgenstein's numbers encode *logical depth* — 2.1 is a remark on 2, 2.11 is a remark on 2.1. That's actually a reasonable model for the claim layer: `~property` under `##Stacking Discounts` is implicitly 2.2.1 or whatever, and can be cited as such by tooling without the author maintaining the numbers. The author maintains the *hierarchy* through heading depth; the numbers are derived.

The full Spinoza move — Definition, Axiom, Proposition, Demonstration, Corollary — is almost too tempting. You could imagine claim subtypes along those lines: `~axiom` for things taken as given, `~proposition` for things claimed and to be verified, `~corollary` for things that fall out of a proof already given. Whether that's useful discipline or excessive formalism probably depends on the domain. For a pricing library, overkill. For a cryptographic protocol implementation, possibly exactly right.

## User

So many things to pick up on. The unnamed tests read well. Does that connect to any existing practice? I wonder if it is the cognitive lure of a small example. Kind of a contrast to our name-oriented focus so far too. Does it give enough context handles?

## Claude

The unnamed tests do have precedent — doctests in Python are essentially this, inline examples that are just concrete expressions with expected outputs, no test function name, no `describe` block. And there's a tradition in functional language REPLs where you just... write expressions and their values, and that *is* the documentation. Haskell's Haddock examples, Elm's early documentation style. The expression and its result as a self-evident unit.

The cognitive lure is real and worth examining. A named test — `test_apply_discount_does_not_increase_price` — front-loads interpretation. You're told what to think before you see the evidence. The unnamed example makes you do a small amount of inference: *oh, identity discount, price unchanged, got it.* That inferential micro-work might actually aid comprehension and retention. It's the difference between a caption and a good photograph.

But your context-handles concern is sharp. A name is a handle the LLM — and the human — can grip. `applyDiscount 1.0 (Price 100) == Price 100` is legible in isolation but has no address. You can't refer to it from a doc-node. You can't say "see ~test:identity-discount." It exists only as a fact in the appendix, not as a node in the graph.

Which might actually be fine for the appendix specifically — those tests are the legal record, the lab notebook, not the argument. They don't need to be cited; they need to be *run*. The doc-node graph lives in the essay body; the appendix is a different genre that earns its anonymity.

Though there's a middle path: optional names.

```
  ~test identity
    applyDiscount 1.0 (Price 100) == Price 100
  ~test zero-price
    applyDiscount 0.5 (Price 0)   == Price 0
    applyDiscount 0.0 (Price 0)   == Price 0
  applyDiscount 0.0 (Price 100) == Price 0
```

Named tests become addressable, citable, part of the graph. Unnamed tests are anonymous witnesses — they bulk out the case coverage without demanding conceptual significance. The discipline then is: if you feel the need to name it, you're probably also identifying something worth a doc-node in the essay body. If it doesn't need a name, it's just a fact.

That tension — named vs unnamed — actually recapitulates the name-oriented theme neatly. Xunzi's advice was that if a single name communicates, use it; if not, combine. The corollary might be: if no name is needed, the thing might not need to exist as a concept at all. Anonymous tests are epistemically humble in a useful way. They say: this is just a case, not a concept.

## User

I think if I have 40 unit tests I definitely want some names in there to navigate. As a human, let alone an LLM. How to decide when the spec is wrong?

## Claude

Yes — and this is where the name does a different job than in the essay body. In the essay, a name creates a concept-node in the semantic graph. In the test appendix, a name is primarily navigational and diagnostic. When the test fails, the name is your first signal about *what kind of wrongness you're looking at*.

Which suggests test names in the appendix want to be organised differently than doc-node names. Something like:

```
##boundary conditions
  applyDiscount 1.0 (Price 100) == Price 100
  applyDiscount 0.0 (Price 100) == Price 0
  applyDiscount 0.5 (Price 0)   == Price 0

##composition
  applyDiscount 0.8 (applyDiscount 0.9 (Price 100)) == Price 72
  applyDiscount 0.9 (applyDiscount 0.8 (Price 100)) == Price 72

##regression: negative price bug 2024-03
  applyDiscount 0.3 (Price 1)   == Price 0.7
```

The heading organises a cluster of anonymous facts. You get navigation without demanding that every case earn a name. And the regression heading is doing something particularly valuable — it's a named *category* of test whose name is frankly historical. It tells you why those cases exist, which is often more useful than what they assert.

But your real question — when is the spec wrong — is the deeper one. A failing test presents you with a genuine dilemma: is the implementation wrong, or is the test wrong, or is the *doc-node* wrong? In current practice you resolve this by judgment and git blame. In this language, the linkage helps. If `##composition` fails, you can navigate directly to `#stacking-discounts` and ask: does the prose still describe the intended behaviour? Is the `~property` still what we want? The failure becomes a prompt to interrogate the whole argument at that node, not just the implementation.

This is maybe the strongest argument for the linked structure over conventional test organisation. A red test currently tells you *something is inconsistent*. In this system it tells you *this node of the argument is under stress* — and the node has a prose face, a claim face, and an executable face, all of which are candidates for being the thing that needs updating.

The spec-vs-implementation question becomes: which layer do you trust? And that's a question the document structure can help you ask explicitly, even if it can't answer it for you.

## User

Package namespacing would naturally live at the top with the header. But imports would be at the end as a bibliography.

#Appendix: Imports

Or just bite the bullet

#References

#Tests

Both so commonplace that you could reserve them as keywords or some such. You could allow #Appendix: for other unanticipated purposes. Or the --- could be semantically significant that this is now the post-text.

## Claude

The bibliography move is elegant and the academic parallel earns its keep here — references in a paper are also executable in a sense, they're the external dependencies your argument rests on. Putting them at the end makes that explicit: here is the literature this essay draws on.

The `---` as semantic boundary is appealing for its simplicity. One rule: everything after `---` is post-text. The compiler knows it, the tooling knows it, and the convention is visually unambiguous. You don't need to enumerate what kinds of appendix are possible — `#References`, `#Tests`, `#Appendix: Performance Benchmarks`, whatever the domain needs. The `---` does the structural work and the headings do the labelling.

```
--- 

#Tests

#References
  import Pricing.Core
  import Data.Ratio
  import Vendor.TaxStrategy as Tax
```

Though ordering within the post-text raises a small question. Tests before references feels right — tests are still *this module's* content, assertions about its own behaviour. References are the outward gesture, the acknowledgement of dependence. So the natural order is probably Tests, then References, mirroring how academic bibliography always comes last, after even the appendices.

The keyword reservation idea is worth taking seriously. `#Tests` and `#References` as reserved headings that the compiler treats specially — running one, resolving the other — while `#Appendix:` is the open extension point for anything domain-specific. That's a clean split between what the language owns and what the author owns. And it makes the post-text section feel less like a dumping ground and more like a structured epilogue with conventional slots and room for the unanticipated.

The package declaration at the top as header is the natural counterpart:

```
#Pricing.Discounts

A module establishing...
```

The module name *is* the essay title. Which means naming the module well is the same act as titling the essay well — the Confucian rectification of names operating at the outermost scope before a single type has been defined.

## User

Fighting years of bred intuition here ... but you could even not use . as a namespace separator. Space separation could translate to filesystem Pricing/Discounts

## Claude

Yes. And it reads better as a title.

```
#Pricing Discounts
```

versus

```
#Pricing.Discounts
```

The first is a heading. The second is already fighting the prose register before you've written a word. The `.` is a machine convention that leaked into the human-facing layer because we never had a layer boundary to stop it.

The filesystem translation is well-established precedent too — Python packages, Go's module paths, the JVM's directory structure. The compiler handles the `/` internally; the author never sees it. You're just writing a title that happens to also be an address.

It does create one genuine tension: disambiguation. `Pricing Discounts` as a two-word title versus `Pricing` slash `Discounts` as a two-level hierarchy. But that tension exists in natural language too and we resolve it through capitalisation conventions, context, and the structure of the surrounding heading hierarchy. If `#Pricing` is a heading elsewhere in the project, `#Pricing Discounts` is obviously a submodule of it. The tooling can enforce consistency.

There's also something right about the ambiguity being *productive*. A module name that reads as a natural language title is a mild forcing function toward names that actually describe what the module is about, rather than names that just satisfy the namespace grammar. `com.enterprise.pricing.discount.strategies.impl` satisfies a namespace grammar. `Pricing Discount Strategies` is a title you'd have to defend in an editorial meeting.

Xunzi would approve.

## User

Yes yes. And we can still enforce lower case directory names through a deterministic rule (I can't give up lower case directories)

## Claude

Trivial transformation, applied once, invisible to the author.

```
#Pricing Discount Strategies
```

becomes `pricing/discount/strategies/` and nobody ever has to think about it. The deterministic rule is so simple — lowercase, spaces to slashes — that it barely deserves documentation. It's the same move as `git` turning your commit message into a ref, or Ruby turning `MyClass` into `my_class` for filenames. A convention so mechanical it disappears.

You could even allow the inverse — the tooling reads the directory path and generates the heading stub when you create a new file. Start with `pricing/discount/strategies.lang` and the file opens with:

```
#Pricing Discount Strategies

```

Cursor blinking. Ready for the essay.

Which is a small thing but gets the authorial posture right from the first keystroke — you're not creating a file, you're starting a document. The filesystem is the bibliography of the project, the heading is the title, and the first thing you write is prose.

## User

This is pretty cool. What would be a possible toolset to build a tiny experimental prototype?

## Claude

The core of a prototype is a parser that understands the two-layer structure — post-text boundary, heading hierarchy, claim sigils, code blocks — and can do something useful with it. You don't need a real compiler or type checker to validate the ideas.

**Minimal viable stack**

Tree-sitter is the obvious choice for the parser. It's designed for exactly this kind of mixed-content language, handles error recovery gracefully, and produces a real AST you can query. Crucially it has good bindings for both Rust and Python, and there's a reasonable ecosystem of tooling built on it. Writing a Tree-sitter grammar for this language is a weekend's work for the structural layer — headings, code blocks, claim sigils, the `---` boundary.

For the host language of the prototype itself, Python is pragmatic. You get:

- Tree-sitter bindings
- A doctest runner you can repurpose almost directly for `~example` claims
- Hypothesis for property testing, which maps naturally onto `~property`
- Rich for terminal output, which matters more than you'd think for making the thing feel real

**The prototype's jobs**

Parse a `.lp` file (or whatever extension) into an AST where doc-nodes, code blocks, and claims are all first-class. Then:

- Extract and run `~example` claims as doctests
- Extract `~property` claims and run them through Hypothesis
- Generate a navigable document — even just markdown output would validate the literary layer
- Report failures with a reference back to the doc-node, not just a line number

That last point is worth building carefully even in a prototype. The diagnostic experience — *this claim in #stacking-discounts is failing* rather than *line 47 assertion error* — is where the ideas become tangible.

**What you'd leave out**

A real type checker. That's a multi-year project and not what you're testing. The code blocks in the prototype are probably just Python, or maybe Haskell if you want the functional syntax to feel right. The point isn't to build a new language runtime — it's to validate the document structure, the claim layer, and the LLM interaction story.

**The LLM interaction experiment**

Which suggests a second prototype tool: given a `.lp` file, feed it to the API and ask it to extend the module — add a function, add a doc-node, write the claims. See whether the linked structure actually produces better, less aberrant output than giving it equivalent unstructured code. That's the hypothesis worth testing early, and you could run that experiment with the document structure alone, before the claim runner exists at all.

Tree-sitter grammar plus a Python claim runner plus a simple API harness. Maybe a thousand lines of code to have something genuinely interesting to show.

## User

Well if it's going to be Python the project should be called Notlob, after the not-a-palindrome in the Parrot sketch

## Claude

Perfect. Notlob is not a palindrome, is not a parrot, and is not quite a programming language. It fits on every level.

It also has the right energy for an experimental prototype — slightly absurdist, self-aware about its own status, not trying to be LLVM. A project called Notlob is not making grand claims. It is perhaps making `~claims`.

`notlob parse pricing_discounts.lob` feels right. `.lob` as the extension — short for... nothing in particular, but it sounds like a gentle arc through the air, which is about the right trajectory for an idea at this stage.

Though `.nb` is tempting if you want the Knuth nod. Notlob/notebook. Probably too close to Mathematica's `.nb` format to be worth the confusion.

`.lob` it is. The file lobbed gently into the interpreter. No grand claims. Just a document with some executable bits and a bibliography.

## User

Looking for little domain experiments, if it is Tree-sitter Python, does the rich python library infrastructure become available to the notlob files?

## Claude

Yes, and that's a genuinely good reason to lean into Python as the execution substrate rather than apologise for it.

A `.lob` file's code blocks are just Python, executed in a context where the imports from `#References` have already been resolved. Which means:

```
#Pricing Discounts

A discount strategy applies a multiplier in [0,1]...

    from decimal import Decimal

    def apply_discount(strategy: Decimal, price: Decimal) -> Decimal:
        return price * strategy

~example
    apply_discount(Decimal('0.8'), Decimal('100')) == Decimal('80')

~property
    for all price >= 0, strategy in [0,1]: result <= price

---

#Tests

    apply_discount(Decimal('1'), Decimal('100')) == Decimal('100')
    apply_discount(Decimal('0'), Decimal('100')) == Decimal('0')

#References
    from decimal import Decimal
    import hypothesis
```

And now you can immediately do interesting domain experiments because the entire Python ecosystem is just... there. Pandas for data shape experiments. NetworkX if you want to explore the doc-node graph structure itself. Hypothesis is already the natural property testing backend. Pydantic for exploring whether type annotations in code blocks can do some of the work of the formal layer.

There's a particularly nice bootstrap experiment available: write Notlob's own doc-node graph structure as a `.lob` file, using NetworkX to represent and query it. The tool partially describing itself in its own format. Not self-hosting in the compiler sense, but self-documenting in the literate sense.

Which Knuth would probably find more interesting anyway.

## User

Yes ... it's not quite clean enough syntax for the destination ... weird to say that of Python ... but the real running code has so many virtues.

## Claude

The tension is real and probably productive at this stage. Python is syntactically noisy for what you want — the `def`, the `:`, the indentation-as-structure fighting with the document's own structure, the `Decimal('0.8')` ceremony where you wanted `0.8`. The code blocks will always feel like they're from a different register, which is fine in a Jupyter notebook but slightly wrong in a literate document that's trying to make prose and code feel like neighbours.

But that's a destination problem. For the prototype, the noise is the price of admission to Hypothesis, to Pandas, to the whole ecosystem, to actually running things. And there's real value in feeling exactly where the syntax chafes — it tells you what the destination language needs to smooth over. Every time you write `Decimal('0.8')` and wince, you're accumulating a requirement.

The classic path from here would be a lightweight syntax layer that transpiles to Python before execution. Enough to get numeric literals right, maybe cleaner function definition, without building a runtime. Mython, essentially — but named something worse.

The interesting question is whether the document structure itself is the more important experiment right now, and the code syntax is secondary. You could run quite a long way with ugly code blocks if the heading hierarchy, claim sigils, reference resolution, and LLM interaction story are all working well. The prose layer is the novel contribution. Python is just the engine in the boot.

Notlob first. The syntax can be rectified later. Xunzi would understand.

## User

I am also concerned that about the lack of type safety and ... weirdly? ... that it won't "feel" new enough when you see it on the page

## Claude

Both concerns are legitimate and they're related.

The type safety issue is real — Python's type annotations are optional, unenforced at runtime, and the ecosystem treats them as advisory. A `~property` claim that says "strategy is always in [0,1]" has no formal teeth in Python. You're testing it with Hypothesis rather than constructing it to be impossible to violate. That's a meaningful downgrade from the vision, where the type and the doc-node are in genuine dialogue. In Python they're just... near each other.

The aesthetics concern is sharper than it sounds. There's a phenomenology to reading a new language that signals "this is a different way of thinking." Haskell has it. Rust has it to a degree. Even Elm, which is quite clean, reads differently from the start. Python with some sigils in comments won't have it — your eye will pattern-match to "Python with some sigils in comments" and the conceptual novelty won't land. The medium will fight the message.

Which suggests the prototype has two distinct jobs that might want different tools. Python plus Tree-sitter to validate the *structural and tooling ideas* — the claim runner, the bibliography resolution, the LLM interaction experiment, the diagnostic experience. That's where Python earns its keep.

But a separate purely *aesthetic* prototype — even just static examples, not executable — in a syntax that actually looks like the destination. Something with cleaner numeric literals, meaningful indentation, types that look like types. Even a handful of beautifully typeset `.lob` files that don't run yet but *feel* right would tell you something important.

The question worth asking early is what the destination type system actually is. Hindley-Milner with refinement types is the obvious answer given the functional syntax we've been sketching. Which points toward either piggybacking on an existing language in that family — a Haskell or Idris preprocessor — or accepting that the full vision is further away than a Python prototype suggests.

Idris is actually interesting here. Dependent types mean the formal and claim layers can genuinely converge — a type can express what we've been writing as `~property`. And it's designed for exactly the kind of "constructing correctness" reasoning the doc-nodes have been gesturing at. A Notlob-to-Idris transpiler is a more ambitious prototype but a more honest one.

Though perhaps the move is: Python prototype to validate the ideas, Idris prototype to validate the aesthetics and the type story. Two probes, different questions.

## User

Idris would be good except I don't know it at all and that's a lot of experiment to pile into an experiment. I do know Haskell a bit.

I was thinking of it as a genuinely new language - that's the hook. But the way of getting to that language can be a bit cunning, right? To a degree, the literate innovations can be modularly separated from the language binding

## Claude

Yes, exactly. The literate layer is largely orthogonal to the execution substrate. The heading hierarchy, the claim sigils, the post-text boundary, the reference resolution — none of that is deeply coupled to what language lives in the code blocks. You're building a document format that *hosts* a language, not a language that *contains* documents.

Which means you can decouple the experiments cleanly:

The literate infrastructure — parser, doc-node graph, claim runner, LLM harness, diagnostic output — gets built once in Python/Tree-sitter. That's Notlob the tool.

The code block language is a separate, swappable concern. Start with Python to get things running. Swap in Haskell when you want to feel the type safety story properly. The `.lob` format doesn't care — it just knows where the code blocks are and hands them off.

Then the genuinely new language, when you get there, slots into the same harness. It compiles to something — Haskell, Python, doesn't matter yet — and the literate layer stays intact. The innovation surface is actually quite targeted: numeric literals, cleaner function syntax, whatever refinement type story you land on. You're not building a runtime, you're building a surface language that feels right on the page and hands off to something real underneath.

So the cunning path is roughly:

Notlob with Python blocks proves the document ideas. Notlob with Haskell blocks proves the type safety ideas and starts feeling aesthetically different. Then the new surface syntax is a relatively thin transpilation layer over Haskell, developed when you know exactly where Python and Haskell both chafed.

The experiment stays tractable at each stage because you're only ever changing one variable.

## User

Is there a way to export this entire conversation?

## Claude

Claude products don't have a built-in export function for conversations directly — but there are a few practical options.

The simplest is your browser: select all on the page and paste into a document, though the formatting will be rough.

A cleaner option: I can generate a markdown document of the key ideas and syntax sketches we've developed — not a transcript, but a structured write-up that captures the design decisions and the notation we landed on. That would actually be more useful than a raw transcript, which has a lot of back-and-forth to wade through.

Or if you want the actual transcript, you could check Settings in Claude.ai — there may be export options there that have been added since my knowledge cutoff, worth a look.

What would be most useful?
