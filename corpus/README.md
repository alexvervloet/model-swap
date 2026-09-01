# The corpus

Meridian Ferries is a regional passenger ferry operator. It does not exist.

## Why an invented company

The system under test ships with four documents of one sentence each. They exist
to prove that one tenant cannot retrieve another tenant's answer, which they do
well. They cannot support a measurement: every question over a one-sentence
document is either a lookup that any model passes or a question that no model
can answer, and neither separates a strong candidate from a weak one.

So the corpus is authored here, and three properties made it worth the work.

**Answerable only from the documents.** A real company's public policies are in
the training data, so a model can answer without retrieving anything and the
measurement stops being about the app. Meridian's wind thresholds and refund
tiers exist nowhere else, so an answer is either grounded in a retrieved passage
or invented.

**Interlocking, so multi-hop questions are real.** "Can I take my bike on the
first Kilmore sailing on a Sunday in February?" needs the timetable for whether
that sailing runs in winter, the fleet list for which vessel covers it, and the
carriage rules for how many bicycle spaces that class of vessel has. No single
passage answers it. That stratum is where candidates separate, and it only
exists if the documents were designed together.

**Gaps you can prove are gaps.** A question is only unanswerable if you know
what is absent. On someone else's corpus "the documents do not cover this" is a
guess. Here it is a fact about a file that was deliberately not written, which
is what makes the refusal stratum trustworthy.

## Prose is written, not generated

Northgate Wealth Partners in client-context-compiler is generated from a seed,
because what mattered there was the relationships between records. What matters
here is whether a paragraph is clear enough to answer a question from, and
generated prose is mush. These documents are written, checked in, and diffable.

Determinism comes from the manifest instead: every document is hashed, the
corpus has one version hash over all of them, and a scored run records it. A
document edited after a run invalidates that run rather than quietly changing
what the numbers meant.

## Rules for editing

- **Never edit a document to make a question easier.** Edit the question, or
  accept the score. A corpus tuned against its own results measures nothing.
- **Contradictions are allowed, but only on purpose.** Real policy sets
  contradict themselves, and an assistant that notices is better than one that
  picks a side. Any deliberate contradiction is recorded in the manifest.
- **A new document invalidates the cached responses that were scored without
  it.** That is the cache doing its job, not an obstacle to route around.
