---
name: test-fixture-mock-and-data-migrator
description: "Migrate Batch 8 object, database, file, snapshot, mock, clock, random, message, security, and container fixtures. Use when target tests need isolated test data or service doubles."
---
# Test Fixture Mock and Data Migrator
Read `../references/batch-8-repair-loop.md`. Preserve setup/reset/teardown, per-test isolation, mock arguments/count/order/return/throw/callback/async completion and database schema/seed/transaction/timezone/identity behavior.

Use fake or ephemeral test resources and redact sensitive data. Never connect to production, share mutable globals across parallel tests, use a mock to replace a required integration test, or leave fixtures uncleaned.
