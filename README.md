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
measuring nothing.

Generation happens once and is cached on disk. Rescoring a cached run against a
new rubric is free and offline, and the response set ships as a committed
fixture so every published number reproduces without a key.

Any command that spends estimates first, prints the estimate, and requires
`--confirm`.

## Status

Early. Scaffold and preflight only. Nothing measures anything yet.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .

# The system under test is imported, so its dependencies live in this venv too.
pip install -r ../knowledge-desk/requirements.txt && pip install -e ../knowledge-desk

# And it needs its database up:
(cd ../knowledge-desk && docker compose up -d db && python -m knowledge_desk.migrate)

python check_setup.py
```

One virtualenv holds both dependency trees. That is a real constraint rather
than a convenience: a version this repo wants and the system under test does
not is a conflict you have to resolve, so this repo's own `requirements.txt`
stays as small as it can.


`check_setup.py` finds Knowledge Desk at `../knowledge-desk`, or wherever
`KNOWLEDGE_DESK_PATH` points if you keep it somewhere else.
