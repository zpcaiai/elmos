---
name: isolated-build-test-sandbox
description: "Define and verify a restricted Batch 8 sandbox for dependency restore, build, analysis, and tests. Use before executing any migrated target repository or external test resource."
---
# Isolated Build Test Sandbox
Read `../references/batch-8-repair-loop.md`. Mount the source Snapshot read-only and an isolated candidate workspace writable; deny host home, production resources, privileged mode, host processes and the Docker Socket.

Default network to denied and allow only approved registries/services for the required phase. Use short-lived test-only secret references, redact values, terminate process trees on timeout and clean ephemeral resources. Record commands, environment variable names, versions, limits, exit codes, sandbox identity and evidence.

Return `NOT_RUN` or `BLOCKED` when isolation, cleanup, allowlists or immutable image identity cannot be proven.
