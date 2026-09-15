---
name: elmos-engineering-control-plane-v3.2
description: Implement the next incomplete Elmos v3.2 durable Harness work package in dependency order while preserving K1-K8 ownership and fail-closed assurance.
---
# Elmos Engineering Control Plane v3.2

Use this Skill for implementation of the v3.2 Harness delta.

## Mandatory operating rules
1. Read `package.yaml`, `docs/ARCHITECTURE.md`, `docs/INVARIANTS.md`, and `implementation/work-packages.yaml`.
2. Select the next READY work package whose dependencies are complete.
3. Do not introduce a second authority, evidence, completion or route-owner system.
4. Preserve exact authorization semantics across resume/replay/handoff/model switch.
5. Adapter uncertainty fails closed; do not silently map removed upstream security modes.
6. Builder results are candidates until Truth Runner + Gate + Certifier complete.
7. Update tests, traceability and migration receipts with every contract change.
