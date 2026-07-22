---
name: ephemeral-runner-and-sandbox-isolation
description: Design per-job ephemeral Runner sandboxes with signed images, least privilege, resource limits, isolated cache, wipe, and destruction. Use for untrusted repository execution safety.
---

# Ephemeral Runner and Sandbox Isolation

Read `../references/batch-12-enterprise-platform.md`. Select process/container/Pod/MicroVM/VM isolation from risk. Deny privilege, host network/PID and Docker socket; isolate tenant caches, mount short-lived secrets, upload bounded evidence, wipe all job data and destroy the environment.

Workspace reuse across tenants, unsigned images, secret residue or any sandbox escape blocks T-C.
