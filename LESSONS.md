# Lessons

What did not go according to plan, written down when it happened.

## 1. Importing the system under test means adopting its dependency tree

**Expected.** model-swap would depend on the sibling knowledge-desk checkout the
way `local-lora` depends on its sibling: read some files, stay independent.

**What happened.** The preflight found it on the first clean virtualenv. This
repo imports `knowledge_desk.config` and drives the assistant in-process, so
everything knowledge-desk imports has to be installed here too. A fresh venv
with this repo's two test dependencies failed on `pydantic_settings`, four
layers down someone else's import chain.

**Why it matters beyond the annoyance.** One virtualenv now holds both
dependency trees, so any version this repo wants and knowledge-desk does not is
a conflict that has to be resolved rather than avoided. That is a live
constraint on every future milestone: the statistics layer wants numpy, the
judge wants the Anthropic SDK, and both have to sit alongside FastAPI, psycopg,
pgvector, voyageai and langfuse at whatever versions the system under test has
pinned.

**What to do differently.** Keep this repo's own `requirements.txt` as small as
it can be, and add to it deliberately rather than reaching for a library because
it is convenient. Check a new pin against the SUT's before adding it. If the
trees ever genuinely conflict, the fallback is to stop importing and drive
knowledge-desk over HTTP instead, which costs realism in the measurement and is
worth avoiding for as long as possible.

**Also.** The README's setup block was wrong when written, and the preflight
caught it rather than a person. That is the argument for a preflight that runs
the real path instead of printing a checklist.

## 2. The system under test had no corpus worth measuring

**Expected.** Knowledge Desk is deployed, seeded and demoed, so the plan assumed
M1 was about writing questions against documents that already existed.

**What happened.** Its seeded corpus is four documents of one sentence each.
"Acme refunds are processed within five business days of the request" is the
whole of the refund policy. That is exactly right for what those documents were
built to do, which is prove that Globex cannot retrieve Acme's answer, and it is
useless for telling two models apart. Every question over a one-sentence
document is either a lookup any model passes or unanswerable.

**Why the plan missed it.** The corpus was reviewed for whether it existed
rather than for what it could support. A demo corpus and a measurement corpus
have almost nothing in common: one needs two documents that must not reach each
other, the other needs enough depth that a weaker model can plausibly get a
question wrong.

**What to do differently.** M1 grew a half it did not have: authoring the
documents, not just the questions. Following the precedent CCC set with
Northgate Wealth Partners, the corpus is synthetic, deterministic from a seed,
and lives in this repo rather than in the system under test, because the
questions and the documents have to be designed together. A question that is
genuinely unanswerable is only knowable if you wrote what is absent.

**The check that would have caught it earlier.** Before planning a measurement,
ask what the weakest candidate would score. If the answer is "the same as the
strongest", there is nothing to measure yet.
