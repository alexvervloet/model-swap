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

**Fixed upstream**, so the workaround is gone from this repo. knowledge-desk's
`delete_org` and `TenantScope.remove_member` now both call
`accounts.purge_stranded_users`, which deletes only the users the caller just
affected and only when no membership remains. A member of another org keeps
their account, which is the reason users are global in the first place. See
that repo's LESSONS entry 44.

The temporary version here deleted the owner row from another repo's table,
which was the right call for an afternoon and the wrong one to keep. A
workaround that reaches into someone else's schema is a bug report with a
deadline.

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

## 7. The fleet register is unreachable unless you say "vessel"

**Expected.** Writing 120 questions and checking they retrieve was a formality
before the interesting work started.

**What happened.** 117 of 120 reached their sources at the app's default k=6.
The three that did not were three different problems, which is the reason the
verifier exists rather than a spot check.

Two were my bookkeeping: `sources` listed every document that was *relevant*
rather than the ones *necessary* to answer. "I missed my sailing, I had a Flex
ticket" named terminal operations as well as the refunds policy, but the refunds
policy answers it alone; terminal operations only supplies the gate time the
question already assumes. Over-specifying sources turns a passing question into
a failing one and hides the real failures among the noise.

The third is a genuine limit of the app. "What is the most passengers a single
Kilmore sailing can carry?" retrieves the fares document three times, the
animals policy, and the timetable. The fleet register, which holds the only
capacity table in the corpus, never appears. Rephrasing to "how many cars can
one Kilmore sailing carry" does not help. Rephrasing to "which vessel carries
the fewest vehicles" puts the fleet register at rank 1.

**What that means.** Retrieval matches the document's subject, not the user's
framing. The fleet register is *about vessels*, so it is reachable by questions
about vessels. A passenger asking about capacity does not think in vessels, they
think in "how many people fit", and that phrasing lands in the fares document,
which is full of the words passenger and adult and child. No amount of model
quality fixes it, because the answer never reaches the context window.

**What I did.** Replaced the question, because a question every candidate fails
identically measures nothing and contributes only noise to a paired comparison.
The finding itself is worth more than the question was, and belongs in the
write-up: this is the class of failure a model migration study will not catch,
and it is sitting underneath every number the study produces.

**What to do differently.** Verify retrieval before writing the question, not
after writing 120 of them. The probe existed first, and I still batched the
authoring. Ten minutes of probing per stratum would have shaped better
questions.

## 8. I wrote down the hazard, then walked into it

**The lesson I had just written**, in knowledge-desk's LESSONS 45: two projects
share one Postgres, and running one repo's test suite truncates the other's
data. I wrote that paragraph, pushed it, and forty minutes later started a
120-answer paid generation in the background and then ran knowledge-desk's test
suite while it was still going.

**What happened.** The `clean_db` fixture truncated every table 23 answers in.
The org the run was writing against stopped existing, and the remaining 97
answers failed on `answers_org_id_fkey`, "Key is not present in table orgs".
The run reported `120 generated, 97 failed, $0.4589 spent` and exited 0.

**Why writing it down did not help.** The lesson was stated as a sequential
hazard: run the tests, lose the data, reload it. What actually bit was
concurrent. The data was there when the run started and gone in the middle,
which is a different failure with the same cause, and the sentence I wrote did
not cover it.

**The second bug, which was worse.** Every one of those 97 failures was written
to the answer cache. `read_cached` returned them as hits, so the next run would
have said "120 cached, 0 to generate" and the judge would have scored 97 empty
strings as the model's output. An outage would have been reported as a quality
regression, and the numbers would have looked plausible.

**Fixed twice.** A failed generation is kept on disk and never returned as a
hit, so it regenerates. And model-swap now creates and migrates its own
`model_swap` database on the same server, so the two projects cannot reach each
other's rows at all. Verified rather than assumed: knowledge-desk's full
222-test suite now runs without the corpus tenant noticing.

**The general form.** A shared mutable resource does not need a rule about who
touches it when. It needs to stop being shared. Every version of "remember not
to do X while Y is running" fails the first time something runs in the
background, and the whole point of a background job is that you stop thinking
about it.

**And the one that generalises furthest.** Any cache that stores failures
alongside successes has to distinguish them on read, or it converts a transient
outage into a permanent, plausible-looking result. That is worse than crashing.
