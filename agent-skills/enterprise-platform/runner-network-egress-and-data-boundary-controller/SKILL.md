---
name: runner-network-egress-and-data-boundary-controller
description: Enforce job-scoped default-deny Runner egress and source-code data boundaries for Git, registries, models, databases, DNS, logs, and HTTP. Use for network profiles, DLP, or source-stays-local validation.
---

# Runner Network Egress and Data Boundary Controller

Read `../references/batch-12-enterprise-platform.md`. Authorize exact destination, port, purpose and expiry; distinguish package registries from arbitrary Internet and force model access through the Gateway. Scan source, Prompt, logs, exceptions, environment and traffic for leakage.

Unexpected egress, DNS tunneling or unapproved source transfer blocks T-C; Air-gap permits zero undeclared network requests.
