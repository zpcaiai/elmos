---
name: model-request-audit-and-response-provenance
description: Record model purpose, exact version, route/data policy, context hashes, tokens, cost, output hash, validation, acceptance, and use. Use when tracing an Agent Patch or auditing model behavior.
---

# Model Request Audit and Response Provenance

Read `../references/batch-12-enterprise-platform.md`. Record rejected/discarded outputs as well as accepted ones and link every Agent Patch to its call, validation and human review. Store hashes/references or approved redacted summaries instead of full source/Prompt by default.

Mutable cost/token facts, missing model version or broken Patch provenance blocks T-D/T-E.
