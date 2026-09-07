---
name: test-body-migration-agent
description: "Translate source test bodies into executable target tests while preserving assertions, async behavior, skips, and traceability. Use when Batch 4 test skeletons require Batch 8 completion."
---
# Test Body Migration Agent
Read `../references/batch-8-repair-loop.md`. Map setup/teardown, parameters, assertions, exceptions, async, timeouts, mocks, snapshots, categories, temporary resources, fake time and random seed to the target framework.

Preserve equality type, ordering, tolerance, exception type/message/cause, predicates, identity and side effects. Never emit `assert true`, delete an assertion, weaken precision silently, block an async test or convert a conditional source skip into a permanent skip. Record every unmigratable assertion as an obligation.
