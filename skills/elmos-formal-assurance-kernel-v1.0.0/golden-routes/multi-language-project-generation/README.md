# Multi-language Project Generation Formal Golden Route

This Golden Route defines the minimum repeatable path for commercial certification of `project-generation`.

## Critical properties

- P0 ambiguities are resolved before code certification
- data/API/workflow/security/resource specifications are traceable
- architecture and tenant isolation constraints hold
- workflow safety/liveness properties hold under explicit assumptions
- verified core is separated from tested shell

## Certification conditions

- at least three target-language stacks
- multi-tenant threat tests
- payment/task workflow models
- load and failure tests
- E1-E5 complete

A successful package validation is not an E5 certification. E5 requires real repositories/environments, exact toolchain pins, failure injection and signed evidence.
