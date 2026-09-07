---
name: api-contract-and-differential-validator
description: Validate signatures, semantics, lifecycle, serialization, and service boundaries for dependency mappings using differential evidence. Use before D-D.
---
# API Contract And Differential Validator
Read `../references/dependency-migration-v1.md`. Validate every used API signature and mapped behavior, including representative/edge/error cases, state/order, concurrency, cancellation, resource cleanup, serialization compatibility, timeouts/retries and service failure modes. Bind tests to dependency, mapping, strategy, version, environment and artifact hashes. Require full required-API coverage and passing differential obligations for D-D. Compilation, mocks, snapshots without source comparison, or passing happy paths alone never prove compatibility.
