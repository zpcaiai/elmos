---
name: python2-and-old-python-modernizer
description: Modernize Python 2 and obsolete Python 3 syntax, standard-library APIs, imports, bytes/text, iteration, numeric, comparison, pickle, and runtime behavior. Use for Python 2.7 migrations, removed stdlib modules, legacy 2to3 workflows, or cross-version golden-behavior analysis.
---

# Python 2 and Old Python Modernizer

## Keep legacy tools subordinate

Use a frozen `2to3`/lib2to3 adapter only on the isolated Legacy Runner to produce a candidate diff or baseline comparison. Use a maintained parser/legacy grammar bridge plus LibCST Codemods for approved transformation. Never treat a successful 2to3 run as completion.

Inventory syntax, standard-library moves/removals, builtins, implicit relative imports, iterator materialization, exception changes, pickle compatibility, ordering, integer division, hash/dict assumptions, and extension dependencies.

Classify every string boundary as `TEXT`, `BINARY`, `MIXED`, or `UNKNOWN` across HTTP, files, CSV/JSON, database, messages, crypto/compression, subprocess, and native code. Do not convert every `str` uniformly.

Capture golden stdout, file/data hashes, API responses, database effects, exception types, encoding, and exit codes in the isolated original environment. Compare target behavior independently.

Permit a Python 2/3 shared-source compatibility layer only with owner, scope, removal date, and removal gate. Accept only when bytes/text, numeric, ordering, import, pickle, and extension risks are explicit and golden behavior is compared.

