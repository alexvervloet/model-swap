"""Point every test at a database of its own, before anything imports the
system under test.

This is module-level rather than a fixture on purpose. knowledge-desk builds
its settings object when `knowledge_desk.config` is first imported and reads the
environment exactly once, so a fixture would run too late for any test module
that imported it at the top.

Why it exists: the sut-marked tests reset the corpus tenant and reload it with
mock embeddings. Run while a paid generation is in flight, that deletes the org
mid-run and leaves the index full of fake vectors, which is worse than the
crash because nothing about it looks wrong afterwards. See LESSONS 8 and 9.
"""

from __future__ import annotations

from modelswap import database

database.configure(database.TEST_DB_NAME)
