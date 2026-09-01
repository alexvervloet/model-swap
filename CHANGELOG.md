# Changelog

## Unreleased

### Added
- Scaffold: license, ignore rules, package config, requirements, CI.
- `modelswap.sut`, which locates the knowledge-desk checkout by sibling path or
  `KNOWLEDGE_DESK_PATH`, and refuses a directory that only has the right name.
- `check_setup.py`, a preflight that finds the system under test, imports it,
  reports the model it currently answers on, and connects to its database.
- CI: tests against a real knowledge-desk checkout and its Postgres, plus ruff,
  mypy, a secret scan of the full history, and an advisory dependency audit.
