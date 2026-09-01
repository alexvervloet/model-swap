# Changelog

## Unreleased

### Added
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

### Found in the system under test
- `accounts.delete_org` cascades every org-scoped table but leaves the owner's
  `users` row, which then has no memberships, cannot log in, and holds an email
  that signup will refuse to reuse. Worked around here; see LESSONS entry 5.
