---
name: change-impact-and-revalidation-scope-analyzer
description: "Compute the minimum safe Batch 8 revalidation scope from a patch, dependency/call graphs, tests, contracts, and framework semantics. Use before incremental validation."
---
# Change Impact and Revalidation Scope Analyzer
Read `../references/batch-8-repair-loop.md`. Trace modified files and declarations through signatures, callers, modules, tests, public contracts, configuration, persistence, messaging, security and lifecycle.

Trigger full contract/regression validation for public API, shared type, dependency, serialization, security, transaction, ORM, message, global middleware or compatibility-runtime changes. Expand low-confidence scopes. Never select tests by filename or name alone.
