# Changelog

## Unreleased

### Changed
- Claude Opus is no longer a candidate or the judge. Every tier moved down one:
  Sonnet is the arbiter and the strong candidate, Haiku the weak one. Opus costs
  five times Sonnet's input price, and the migration question worth asking is
  whether the cheaper model is good enough, which does not need the expensive
  one in the study.
- `ANSWER_MODEL` is pinned to Sonnet in `modelswap.database`, so no code path
  can reach Opus by inheriting the system under test's default.
- Cost estimates are priced at Sonnet, the dearest model in play, rather than
  at Opus.

### Added
- `modelswap.ledger`: every spending run records what it actually spent, and
  every run about to spend checks its estimate against what is left of a $2.00
  project budget. Per-run ceilings stop one command running away; they do
  nothing about six sensible commands adding up, which is how the first budget
  went.
- `Judgment` records what each verdict cost, so the ledger is accurate rather
  than estimated.
- `modelswap.decision`: paired bootstrap on per-case outcomes, read against a
  predeclared 5-point margin rather than against zero, with one error budget
  split across the metric family. Verdicts are ship, do not ship, or
  inconclusive with the number of extra pairs that would settle it. Prints the
  smallest difference the sample can detect beside every verdict.
- `modelswap.compare`: cost, latency, token counts and accuracy per variant,
  read from the cache with no API calls, no database and no key.
- `modelswap.judges`: two judges over the same answers, with a
  difference-in-differences that separates self-preference from a calibration
  offset. Uses the 170 verdicts a retired Opus judge left on disk.
- `REFERENCE_VARIANTS`: models whose cached answers are readable and gradeable
  but which will never be generated again. Opus's 120 answers cost $2.60 and
  are kept as a reference arm rather than deleted.
- `Judgment.judge_model`, so a verdict records which model produced it. The
  rubric hash always distinguished two judges; nothing said what either was.
- A hard spend ceiling: $1.50 per generation run, $1.00 per judging run, checked
  against the estimate before the first call and against actual spend during the
  run. A run that exceeds it stops and keeps what it has.
- `--max-spend` to raise either ceiling deliberately.
- `modelswap.agreement`: self-agreement, judge-vs-human agreement and Cohen's
  kappa, against a floor declared before any label existed.
- `modelswap.labels`: two-round blind human labeling of a fixed, stratified
  42-answer calibration set.
- `modelswap.judge`: reference-based grading, blind to the candidate, reasoning
  generated before the verdict. Cached and keyed by rubric version.
- `modelswap.answers`: generates and caches answers per variant and sample,
  with a cost estimate behind `--confirm`.
- `modelswap.database`: model-swap creates and migrates its own `model_swap`
  database, so the system under test's test suite cannot truncate it.
- The 120-question set across six strata, with a verifier that checks retrieval
  can reach each question's named sources.
- The Meridian Ferries corpus: 13 interlocking policy documents, written by
  hand, with the deliberate gaps recorded so the refusal cases are provable.
- `modelswap.corpus`, which loads the documents and pins a run to a version
  hash over their ids and contents.
- `python -m modelswap.load`, which creates the tenant and indexes the corpus.
  Refuses to run on mock embeddings, and `--reset` forces a re-embed, which
  content-hash reconciliation will not do on its own.
- Scaffold: license, ignore rules, package config, requirements, CI.
- `modelswap.sut`, which locates the knowledge-desk checkout by sibling path or
  `KNOWLEDGE_DESK_PATH`, and refuses a directory that only has the right name.
- `check_setup.py`, a preflight that finds the system under test, imports it,
  reports the model it currently answers on, and connects to its database.
- Preflight reports whether the provider is real or mock.
- CI: tests against a real knowledge-desk checkout and its Postgres, plus ruff,
  mypy, a secret scan of the full history, and an advisory dependency audit.

### Fixed
- The index record is named after the database it describes. It was a single
  global file, so the test suite's mock load overwrote the record for the
  measurement database and the next real run refused itself.
- A failed generation is no longer returned as a cache hit. An outage would
  otherwise have been scored as the model's output.

### Found in the system under test
- `accounts.delete_org` cascades every org-scoped table but leaves the owner's
  `users` row, which then has no memberships, cannot log in, and holds an email
  that signup will refuse to reuse. Fixed upstream; see LESSONS entry 5.
- Sonnet 5 was priced 50% high and Haiku had no price at all, in a table the
  per-org budget is summed from. Fixed upstream.
- `output_config.effort` was sent to every model, and Haiku 4.5 rejects it, so
  the app could not run on Haiku at all. Fixed upstream.
