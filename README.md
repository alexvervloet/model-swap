# model-swap

What a forced model migration actually costs, measured on a live app.

## The sentence this exists for

*The model this app was tuned on is being retired, the eval suite is green
either way, and nobody can say whether the replacement is worse.*

## The problem

Most eval suites in a portfolio, including the ones in my own, are **structural
assertions that hold regardless of what the model says**. They check that a
permission boundary held, that a citation key resolves, that an injected
instruction was quoted rather than obeyed. Those are the right tests for that
machinery and they pass identically on any model you point them at.

Which means they cannot answer the question a migration forces on you: the
provider is retiring the model this app was built on, or the bill says move
from Opus to Sonnet, and the prompts were tuned against the old one. "The evals
are green" is not evidence. It was green before you changed anything.

## What this is

Two things, in this order.

1. **A measurement rig** that scores a real app's real answers, with a judge
   calibrated against human labels before it is trusted to grade anything.
2. **One real decision made with it**, published with its interval and the
   threshold that was committed before the run.

The rig outlives the decision. The decision is what proves the rig works.

## The system under test

[Knowledge Desk](https://github.com/alexvervloet/knowledge-desk), a multi-tenant
permissions-aware knowledge assistant, checked out as a sibling directory and
imported as a library:

```
WebDev/AI/
├── knowledge-desk/     # the system under test
└── model-swap/         # this repo
```

It runs in-process against Knowledge Desk's own Postgres and seeded corpus, the
same way that repo's eval runner already does. No HTTP, no deployment
dependency, nothing between the measurement and the thing being measured.

Knowledge Desk rather than one of the agent projects because it emits free-text
answers with citations, and free text is the thing whose quality varies. An
agent's output is a sequence of tool calls, which trajectory evals already
cover.

## Two limits, stated up front

**The corpus is hand-built and author-labeled.** It is not mined from production
traffic, because there is no production traffic. A single annotator has no
inter-annotator agreement to report, so the calibration set is labeled twice,
weeks apart, blind to the first pass, and that self-agreement is reported as the
ceiling on what judge agreement can mean here.

**The judge and the candidates come from one provider family.** Self-preference
bias is measurable in that setup but not eliminable. It gets measured and
reported, not argued away.

## Cost

This is the first project here that has to spend real money. The subject is
output variance and a mock provider has none, so a keyless run would be
measuring nothing. It is still a portfolio project, and the whole thing is meant
to cost a couple of dollars.

**Opus is not a candidate.** At $5/$25 per million tokens it is five times
Sonnet's input price, and one afternoon of exploratory runs on it cost more than
this project's entire budget. The comparison that matters to a real migration is
the one where somebody is trying to spend less, so the study is Sonnet against
Haiku and the judge is Sonnet too.

| | Input $/1M | Output $/1M | Role |
|---|---|---|---|
| claude-sonnet-5 | $2.00 | $10.00 | candidate, and the judge |
| claude-haiku-4-5 | $1.00 | $5.00 | candidate |

A full pass over the 120 questions costs about $0.96 on Sonnet and $0.30 on
Haiku. Judging both costs about $0.48.

Three things keep it there:

**Generation happens once and is cached.** Rescoring a cached run against a new
rubric is free and offline.

**Every spending command estimates first**, prints the number, and does nothing
without `--confirm`. The estimate is priced at Sonnet, the dearest model in
play, so it is never lower than what gets spent.

**There is a hard ceiling**, $1.50 for generation and $1.00 for judging. A run
whose estimate exceeds it refuses before the first call, and a run that exceeds
it anyway stops mid-flight and keeps what it has. `--samples 5` costs $4.80 and
is refused, which is the mistake the ceiling exists for.

## The corpus

The system under test ships with four documents of one sentence each. They prove
a permission boundary and cannot support a measurement: every question over a
one-sentence document is either a lookup any model passes or one no model can
answer.

So the corpus is authored here. Meridian Ferries is an invented regional ferry
operator, 13 interlocking policy documents, and it is deliberately unlike a real
company whose policies would already be in a model's training data. Its wind
thresholds and refund tiers exist nowhere else, so an answer about them is
either grounded in a retrieved passage or invented, with nothing in between.

[corpus/README.md](corpus/README.md) covers why it is written by hand rather
than generated, and [corpus/gaps.md](corpus/gaps.md) records the subjects left
out on purpose, because a question is only unanswerable if you know what is
absent.

```bash
python -m modelswap.load            # into the system under test
```

It refuses to run on mock embeddings. An index of deterministic fake vectors
retrieves passages unrelated to the question, and a score over that is noise
wearing a number.

## The question set

120 questions over the corpus, 20 in each of six strata, in
[questions/](questions/). Each states what it expects and which documents have
to be reachable for an answer to be possible.

| Stratum | What it tests |
|---|---|
| single | One passage answers it. The floor. |
| multihop | Two or more documents. A candidate that stops at the first plausible chunk fails. |
| override | Two passages both look right and one governs the other. |
| refusal | The documents do not cover it. Inventing a plausible policy is the worst outcome. |
| nearmiss | Reads like a gap and is not. Punishes the opposite mistake to the refusal set. |
| unflattering | Answerable, and the honest answer is bad for the company. |

```bash
python -m modelswap.questions --verify    # can retrieval reach what each one needs?
```

All 120 reach their sources at the app's default depth. Getting there found a
retrieval limit worth more than the question it cost: the fleet register, which
holds the only capacity table in the corpus, is unreachable by any question
phrased in passenger language rather than vessel language. See LESSONS 7.

## Grading

```bash
python -m modelswap.answers --variant claude-sonnet-5 --samples 1 --confirm
python -m modelswap.judge   --variant claude-sonnet-5 --samples 1 --confirm
python -m modelswap.labels  --round 1      # you, by hand
python -m modelswap.agreement              # is the judge worth listening to?
```

The judge grades against a reference: every question carries the correct answer
in its notes, written when the question was written. It never learns which model
produced an answer. Its reasoning field is generated before its verdict, because
a model that states a verdict first spends the rest of the response defending
it.

None of its verdicts count until `agreement` says they do. The floor is 85%
agreement with human labels and a Cohen's kappa of 0.60, both declared in the
repository before the first label existed.

## The decision

```bash
python -m modelswap.decision --control claude-sonnet-5 --candidate claude-haiku-4-5
```

Free to run, and it reads against a margin rather than against zero. Nobody
migrates to a cheaper model hoping it is better, so the question is whether it is
worse by more than you will accept. A candidate reliably two points worse is
inside a five-point margin, and blocking that trade is how a cost saving dies to
a difference nobody would notice.

The margin is 5 percentage points, the family error budget is 5% split across
three metrics, and the floor for a look is 30 pairs. All three are declared in
`modelswap/decision.py`, committed before any comparison ran, and the git history
is what makes them mean anything.

The verdict is ship, do not ship, or **inconclusive with the number of extra
cases that would settle it**. Inconclusive is a real answer and, at sample sizes
this project can afford, the most likely one.

### What the comparison says

Every number below is reproducible from the cache with `python -m modelswap.compare`,
`python -m modelswap.decision` and `python -m modelswap.judges`, all of which are free
to run and call no model.

| Variant | Correct | $/100 answers | p50 | p95 |
|---|---|---|---|---|
| claude-haiku-4-5 | 110/120 (92%) | $0.25 | 1.9s | 3.8s |
| claude-sonnet-5 | 116/120 (97%) | $0.68 | 3.6s | 5.7s |
| claude-opus-5 (reference) | 117/120 (98%) | $2.16 | 5.1s | 8.9s |

Haiku is 2.7 times cheaper than Sonnet and half the latency, for five points of
accuracy. Opus buys one point over Sonnet for three times the price.

**The verdict is inconclusive, and that is the answer.**

```
correct              -5.0% [-10.0%, -0.8%]  inconclusive, needs ~81 more pairs
                     smallest difference 120 pairs can see: 6.5%
behaviour_matches    -2.5% [-6.7%, +0.0%]   inconclusive
cited                +0.0% [+0.0%, +0.0%]   ship
```

Haiku is worse. The interval excludes zero, so that part is real. What 120 pairs
cannot settle is whether it is worse by more than the five points declared as
acceptable, because the interval spans the margin in both directions. Roughly 81
more paired cases would settle this particular comparison; resolving the margin
in general takes about 201.

A suite that returns "inconclusive" is not a broken suite. It is one that
declined to launder a 5-point measurement into a decision it could not support,
which is the failure mode the whole project was built to make visible.

**Where Haiku loses is legible.** Its ten misses are concentrated in multihop
(17/20 against Sonnet's 19) and override (18/20 against 20), the two strata built
to punish a model that stops at the first plausible passage. It matched Sonnet
exactly on refusals, 20/20, so it is not inventing policy. That is a different
recommendation from "Haiku is 5% worse": it is fine for lookups and weaker when
an answer needs two documents reconciled.

### The judge is not favouring its own answers

The archived Opus verdicts turned into the calibration the design was missing.
Two independent judges over the same 170 answers:

| Answers by | n | Agree | Kappa | Retired judge | Current judge |
|---|---|---|---|---|---|
| claude-haiku-4-5 | 50 | 98% | 0.88 | 92% correct | 90% correct |
| claude-opus-5 | 120 | 99% | 0.80 | 98% correct | 98% correct |

The retired Opus judge was one point softer on Opus's own answers and two points
softer on Haiku's. A spread of one point, in the wrong direction for
self-preference. Sonnet judging Sonnet's answers is the sharpest version of a
bias this design cannot avoid, and the measurement says it is not moving the
result. That cost $0.36, on answers already paid for.

## Status

The comparison has run. Corpus, question set, answer runner, judge, calibration
report, decision layer and spend ledger are built and tested: 120 tests, green in
CI, 80% coverage.

| | |
|---|---|
| Answers generated | 360, across three models |
| Verdicts | 360 under the current rubric, plus 170 from a retired judge |
| Total spent | $1.87 of a $2.00 budget the code enforces |

Not done: the human labels. Two rounds, weeks apart, and the one part of this
that cannot be automated or hurried. Until they exist the judge is uncalibrated
against a person, and every accuracy number above carries that caveat. The
inter-judge agreement is a partial substitute and not the same thing.

Fifteen write-ups in [LESSONS.md](LESSONS.md): three defects found in the system
under test and fixed there, an outage I caused by ignoring a hazard I had written
down forty minutes earlier, a cache that would have reported an outage as a
quality regression, a report quietly reading half its data, an afternoon that
emptied the account, and a published number that came from a guess.
