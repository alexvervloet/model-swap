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

## 9. The same bug, one level in, and this time it was silent

**Immediately after** fixing LESSONS 8 by giving model-swap its own database, I
restarted the 97 failed answers, and 84 of them failed again.

**What happened.** model-swap's own test suite. `test_load.py` has two tests
marked `sut` that call the loader with `reset=True` and `allow_mock=True`,
because that is the behaviour they exist to check. Run against the measurement
database while a generation was in flight, they deleted the tenant, recreated
it, and reindexed the corpus with mock embeddings.

The first isolation fix stopped knowledge-desk's tests from reaching this
project's data. It did nothing about this project's own tests, which were
pointed at the same database the whole time.

**The half that would have poisoned the study.** A deleted tenant produces a
foreign key error, which is loud. A *reindexed* tenant produces nothing at all:
the answers generated after the reset retrieved against deterministic fake
vectors, came back with confident text about the wrong passages, and were cached
as ordinary successes. There is no flag on them and no way to tell them from the
good ones, so the whole answer cache went in the bin and was regenerated. The
crash cost $0.33. The silent half would have cost the credibility of every
number downstream of it.

**Fixed** by giving the tests a third database, `model_swap_test`, configured in
`tests/conftest.py` at module level rather than in a fixture, because
knowledge-desk reads the environment once at import and a fixture runs too late.
Verified by loading the corpus with real embeddings, running the full suite, and
checking the tenant still holds 44 voyage-3 chunks.

**What I keep relearning.** Both times, the fix I reached for first was a rule
about ordering: do not run the tests during a generation. Both times the real
fix was to remove the sharing. A rule about when to touch a shared resource
survives exactly as long as your attention does, and background jobs exist
specifically so your attention can be elsewhere.

**The check I did not have.** Nothing in the pipeline asserted that the index it
was reading had been built with real embeddings. The loader refuses to *build* a
mock index, which is not the same as a run refusing to *read* one. A guard on the
write path is not a guard on the read path.

## 10. Out of credit, and the partial set looked like a result

**What happened.** The Haiku judging run stopped 50 verdicts into 120 with
`Your credit balance is too low to access the Anthropic API`. The account ran
out mid-run.

**Three separate problems, one event.**

The exception propagated out of the loop and killed the process. Every verdict
already written was fine, but nothing said the run was incomplete, and the next
thing to read that directory would have found 50 judgments sitting there looking
exactly like a finished set.

Worse, 50 of 120 is not a sample of anything. The judge iterates the question
set in file order, so the 50 it reached were `single` (20), `multihop` (20) and
the first 10 of `override`. The three strata designed to be hardest, refusal,
nearmiss and unflattering, were entirely absent. A rate computed from that
subset would have been both wrong and flattering, and nothing about the numbers
would have looked off.

And I had run the command as `... | tail -3`, so the shell reported the exit
status of `tail`. The run "succeeded".

**Fixed.** The judge catches `APIStatusError`, prints how far it got and why,
and exits non-zero. Progress was already written per item, so a re-run resumes.

**The general form.** A long paid job has to assume it will be interrupted, and
the question is not whether it can resume but whether an interrupted run is
distinguishable from a finished one *by the thing that reads it next*. Partial
output that looks complete is the failure; the interruption is just weather.

**And the small one.** Piping a command into `tail` throws away its exit status.
For anything whose failure matters, capture the status before the pipe or do not
pipe it.

## 11. The calibration report was reading half the calibration set

**Found by writing the test, not by running the code.** `agreement.report` took
a `--variant` and used it to look up each judgment. The calibration set is drawn
from two models, and every label already records which model produced the answer
it graded, so passing one variant meant every item from the other one found no
judgment and was silently dropped.

Ten labeled items scored `n=6`. Nothing errored, nothing warned, and the number
printed next to it was a real agreement rate over a real subset. If the two
models had disagreed with the human in different ways, which is the entire
reason both are in the set, the report would have measured one of them and named
neither.

**Why it survived until a test.** Running it by hand never showed it, because
with no labels the report exits early, and I had no labels. The first thing that
ever supplied a full set of labels and judgments was the test, and the assertion
that caught it was `"5 disagreement(s)" in out` failing against three.

**The general form.** A parameter that duplicates something the data already
carries is a chance for the two to disagree. The label knew its variant; asking
the caller to supply one as well created a second source of truth whose only
possible contribution was to be wrong. When a function's argument can be derived
from its input, deriving it is not a convenience, it removes a failure mode.

## 12. An afternoon of testing cost more than a month of real use

**What happened.** The account went from funded to empty in a few hours of
exploratory runs. The bill was not one expensive thing, it was Opus everywhere:
Opus generating 120 answers twice over after two outages, Opus judging them, and
Opus as the default `answer_model` inherited from the system under test.

**The arithmetic I never did.** Opus is $5 in and $25 out per million tokens.
Sonnet is $2 and $10, Haiku $1 and $5. A pass over this question set costs $2.60
on Opus and $0.96 on Sonnet, and every failed run cost the same as a good one.
Nothing in the project stopped, or even mentioned, a second full-price rerun.

**What was wrong with the design, not just the spending.** The study was framed
as Opus against Sonnet against Haiku, as though the interesting question were
whether a better model is better. Nobody migrates in that direction under cost
pressure. The real question is always whether the cheaper model is good enough,
and answering it does not require the expensive one to be in the study at all.
Dropping Opus made the project cheaper and the question sharper at the same
time, which is usually a sign the original framing was carrying weight it had
not earned.

**Three guards now, in order of how much they help.**

A ceiling, $1.50 for generation and $1.00 for judging, checked against the
estimate *before* the first call and against actual spend *during* the run. A
`--samples 5` pass costs $4.80 and is refused rather than reported afterwards.

An estimate priced at the dearest model still in play, so it over-states rather
than under-states.

`ANSWER_MODEL` pinned to Sonnet in the one place every entry point already goes
through, because the system under test defaults to Opus and any code path that
forgot to set a variant would have quietly used it.

**The general form.** A cost estimate printed after the fact is a receipt. The
control is a number the code refuses to exceed, and it has to be checked before
the spending starts, because by the time a total is worth reading it has already
been paid.

**And the cheaper lesson.** `cache/index.json` recorded which index had been
built, globally, while describing one specific database. The test suite's mock
load overwrote the record for the measurement database, and the next real run
refused itself. Same shape as LESSONS 8 and 9 for the third time: state shared
between two things that should not see each other. It is now named after the
database it describes. I appear to need to learn this once per storage layer.

## 13. The retired data was worth more than the data it replaced

**The situation.** Dropping Opus stranded 120 answers that cost $2.60 and 170
verdicts from a judge that no longer exists in the project. The obvious move was
to delete them, since neither is a candidate any more.

**What they turned out to be.** The answers are a measurement nobody would fund
on purpose: what a model five times the price actually buys on this workload,
which is 8.5x the cost and 2.6x the median latency for the same 120 questions.
That number is free now and would cost $2.60 to obtain again.

The verdicts are worth more. A retired judge is a second opinion, and two
independent judges over one identical set of answers is exactly the measurement
this project needed and had no way to buy: the current judge is also one of the
two candidates, so its verdicts on its own family's answers are the one place a
thumb could be on the scale. Grading the archived answers again with the current
judge costs $0.24 and turns the sunk cost into the calibration the design was
missing.

**The design flaw it exposed.** A `Judgment` recorded its rubric hash, which is
an identity, and nothing about the judge, which is a description. Two rubrics
could always be told apart; neither could be named. The field exists now, and
the 170 records that predate it load with it empty and report as "unrecorded"
rather than being guessed at from what I happen to remember.

**The general form.** Before deleting the output of a retired approach, ask what
it is evidence *of* rather than what it was *for*. Data generated under a
configuration you have abandoned is often the only independent sample you will
ever have of that configuration, and independence is the expensive part. The
question is never "do we still use this model", it is "what can only be measured
by having two of something".

## 14. The sample size was decidable before the corpus was written

**What the plan said.** 120 questions, stratified six ways. The number came from
what felt like enough to be credible without being unaffordable.

**What the decision layer said, once it existed.** At the spread two real models
produce on this corpus, 120 paired cases resolve a difference of about 11.5%.
The margin declared for shipping is 5%, which needs roughly 636 pairs. The suite
cannot answer the question it was built to answer, at the threshold it declared,
and no amount of care in the questions changes that.

**The part that stings.** This was arithmetic, not a discovery. `required_sample_size`
is four lines and needs one input: a guess at how often the two models will
differ. Twenty per cent would have been a fine guess. Running it before authoring
would have taken a minute and returned 636, and the corpus would have been
designed around that number or the margin would have been set somewhere the
corpus could reach.

Instead the calculation arrived in M4, three milestones after the decision it
should have informed, as a verdict on work already finished.

**What I did with it.** Not quietly widen the margin, which is the move that
makes the number go away and the project worthless. The margin was declared
before any comparison ran and it stays. The report prints the detectable
difference next to every verdict, so a reader sees what the suite could see even
in principle, and the write-up names the three ways out and which one was taken.

**The general form.** Any measurement has a resolution, and the resolution is
computable from the design before any of it is built. Do that arithmetic at the
point where the design is still cheap to change. A study whose sample size was
chosen by feel and justified afterwards is the ordinary way these go wrong, and
the tell is that the power calculation appears in the analysis rather than in
the protocol.

**And the honest reframing.** A suite that cannot resolve 5% can still resolve
20%, which is the difference between "this model is fine" and "this model is
visibly broken on this workload". That is a smaller claim than the project set
out to make and it is still worth making, as long as it is the claim that gets
published.
