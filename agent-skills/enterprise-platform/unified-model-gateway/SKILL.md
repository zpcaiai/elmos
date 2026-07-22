---
name: unified-model-gateway
description: Route every Agent/model request through one tenant-aware policy, capability, quota, cost, audit, redaction, retry, and provenance boundary. Use for cloud, customer, private, local, or offline model access.
---

# Unified Model Gateway

Read `../references/batch-12-enterprise-platform.md`. Authenticate the caller, enforce tenant/data/purpose policy, select an approved exact deployment, minimize/redact context, reserve quota, bound retry/fallback and record hashes, tokens, cost and result provenance.

Agents cannot call providers directly. Cross-tenant credentials/cache, unapproved source upload or Air-gap egress blocks T-D/T-F.
