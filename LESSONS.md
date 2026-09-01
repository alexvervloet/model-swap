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

## 3. The first CI run failed on tests that passed locally

**Expected.** The locator tests build their own directories in `tmp_path`, so
they looked hermetic. Five green locally, and the CI job was a formality.

**What happened.** CI sets `KNOWLEDGE_DESK_PATH` for the test step, because the
system under test is checked out inside the workspace rather than beside it.
The locator reads that variable first, by design, so every test that passed an
explicit `root=` got CI's answer instead of the directory it had just built.
Two of five failed.

**The part worth keeping.** The tests were not hermetic and passing locally had
nothing to do with the code being right. They passed because this machine
happens not to export that variable. A test that reads process environment it
does not set is a test whose result depends on whose machine it ran on, and the
only reason this surfaced in twenty minutes rather than in six weeks is that CI
runs somewhere configured differently on purpose.

**Fixed by** an autouse fixture that clears the override for every test, so the
one test that cares about precedence sets it explicitly and the rest start from
nothing.

**What to do differently.** When a module reads environment, the fixture that
clears it is part of writing that module, not something to add after a red
build. The general form: anything ambient (environment, cwd, clock, network,
locale) is either set by the test or cleared by the test.

**And then the fix was wrong too.** Clearing the variable in `conftest.py` made
it autouse for the whole suite. Two milestones later the loader tests arrived,
which need the real checkout, and in CI the only way to find it is that same
variable. They failed with "knowledge-desk checkout not found" while the
checkout sat in the workspace. The fixture moved into the module that needs it.

A blanket fixture in `conftest.py` is a decision about every test that will ever
be written in that directory, including the ones that want the opposite. Scope
it to the module unless it is genuinely universal.

## 4. The index went in on mock embeddings and said nothing

**Expected.** Loading the corpus into the system under test was plumbing:
create a tenant, sync the documents, drain the queue.

**What happened.** It worked on the first run. Thirteen documents, 44 chunks,
every job succeeded. It also embedded every chunk with knowledge-desk's
deterministic mock embedder, because no `VOYAGE_API_KEY` was set, and the load
reported success without mentioning it. Retrieval over that index returns
passages unrelated to the question, so anything scored on it would have been
noise dressed as a measurement.

**Why it nearly got past.** knowledge-desk's mock fallback is loud in the
places it was designed to be loud: its own preflight prints the provider mode,
and the UI says so on screen. Called as a library from another repo, none of
that is in the path. A guard that lives in the caller does not protect a
different caller.

**Fixed by** refusing outright. `python -m modelswap.load` exits non-zero under
mock embeddings and prints what the index would be worth. `--mock` overrides it
for exercising the pipeline, and prints the same banner anyway.

**The second half, which was worse.** knowledge-desk reconciles documents on
content hash, so an unchanged document is never re-embedded. Setting a real key
and re-running therefore changes nothing at all: the corpus is already
"in sync", and the vectors stay mock. A scored run would sit on the old
embeddings with every surface reporting success. That is why the loader has
`--reset`, and why it prints how many documents it actually re-embedded rather
than only that the sync succeeded.

**The general form.** A cache keyed on content is invalidated by content. It is
not invalidated by the thing that turned the content into what you actually
stored. Anywhere a derived artefact depends on a provider, a model, or a
version, that dependency belongs in the key.

## 5. A tenant delete leaves the owner behind, and the email is gone for good

**Found in the system under test**, not in this repo.

`accounts.delete_org` cascades everything org-scoped: memberships, documents,
chunks, answers, audit records, sessions. `users` is deliberately not
org-scoped, because one person can belong to several orgs, so the user row
survives. For a user whose only membership was that org, what survives is an
account with no memberships, which can never log in, and whose email is
permanently unavailable, because signup enforces a unique email.

So `--reset` deleted the tenant and then failed to recreate it:
`duplicate key value violates unique constraint "users_email_key"`.

**Worked around here** by deleting the owner row when nothing references it,
scoped to this loader's own email. That is right for a local measurement
harness and is not the right fix for the system under test, which has a
decision to make about what "delete this tenant" means when the request is an
erasure request and the surviving row holds an email address and a password
hash.

**What to do differently.** The thing that made this expensive to diagnose was
that the first failure surfaced as a unique violation on `users` during
*create*, several steps after the delete that caused it. A delete that strands
a row should either remove it or say it kept it.

## 6. A UUID is not a string, and row-level security notices

Reading an existing org's id back from Postgres gives a `UUID` object, while
`create_org_with_owner` returns one already stringified. The two paths through
the loader therefore disagreed about the type, and the failure landed inside
knowledge-desk's `connect()` as
`function set_config(unknown, uuid, boolean) does not exist`, which reads like
a database configuration problem and is not one.

Only the already-exists path was affected, so the create path stayed green and
the bug only appeared on the second run. Worth remembering when a first run
passes: the second run is a different code path.
