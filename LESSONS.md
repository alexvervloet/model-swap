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
