# Changelog

## Unreleased

### Added
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
