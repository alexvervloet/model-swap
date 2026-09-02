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

### The finding that arrived before the comparison did

At the spread two real models produce, 120 paired cases can resolve a difference
of about **11.5%**. The declared margin is 5%, which needs roughly **636 pairs**.

| pairs | smallest difference it can see |
|---|---|
| 40 | 19.9% |
| 120 | 11.5% |
| 300 | 7.3% |
| 600 | 5.1% |

So this suite cannot answer its own question at its own margin, and it could
have told me that before I wrote a single question. The report prints that number
next to every verdict, because a "ship" from a suite that cannot see the margin
is not evidence and the only way a reader learns that is if it is on the screen.

Three ways out, none of them free: more questions, a wider margin, or publishing
inconclusive and saying why. That choice is the write-up.

## Status

Built and tested: the corpus, the 120-question set, the answer runner, the
judge, the two-round labeling flow, and the calibration report. 61 tests, green
in CI.

Generated so far, against the real system under test with real embeddings:

| Variant | Answers | Cost | Role |
|---|---|---|---|
| claude-haiku-4-5 | 120 | $0.30 | candidate |
| claude-sonnet-5 | pending | ~$0.96 | candidate, and the judge |
| claude-opus-5 | 120 | $2.60, already spent | reference only, never generated again |

```bash
python -m modelswap.compare    # free: cost, latency and accuracy from the cache
python -m modelswap.judges     # free: the retired judge against the current one
```

The Opus answers were generated before it was dropped as too expensive. They are
kept because deleting them refunds nothing and they answer two questions the
project could not otherwise afford. The first is what a much dearer model
actually buys: it costs 8.5x Haiku for the same 120 questions and is 2.6x slower
at the median, both measured rather than quoted. The second is better.

**A retired judge is a second opinion.** Those 120 answers were graded by an
Opus judge under a rubric that has since been retired, and 50 of Haiku's were
too. Grading the same answers again with the current Sonnet judge gives two
independent judges over one identical set of outputs, which is the only handle
this project has on the bias it carries: the judge is also one of the two
candidates. If the Opus judge was markedly softer on Opus's answers than the
Sonnet judge, and the two agree on Haiku's, that gap is self-preference. If both
differ by the same amount on both, it is a calibration offset, which a paired
comparison cancels.

That costs $0.24 to find out, on answers already paid for.

An exploratory pass on Opus, before it was dropped as too expensive for this
project, answered the corpus correctly 118 times out of 120. That was a problem
before it was a result: a calibration set drawn from one strong model is 41
correct answers and one wrong one, the human and the judge agree on nearly
everything, Cohen's kappa is undefined, and the floor refuses to certify a judge
nobody actually tested. The calibration set draws from both candidates for that
reason.

The two it got wrong are worth keeping, because both landed in strata invented
to catch exactly them. It refused a question the documents answer ("can I bring
a horse across to Kilmore" — livestock are named and excluded), and it reported
the refit schedule correctly while denying the documented link between refits
and the reduced winter service.

**Blocked on two things.** The Anthropic account is out of credit; finishing
the comparison needs about $1.44. And the human labels, which are two rounds
weeks apart and are the one part of this that cannot be automated or hurried.

Twelve write-ups in [LESSONS.md](LESSONS.md), including three defects found in
the system under test and fixed there, one outage I caused by ignoring a hazard
I had written down forty minutes earlier, one cache that would have reported an
outage as a quality regression, one report that was quietly reading half the
data it claimed to, and the afternoon that emptied the account.
