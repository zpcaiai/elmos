---
name: batch-7-conformance-and-gate-controller
description: "Compute per-module AFSM F-A through F-D gates and Batch 8 admission from framework migration evidence. Use at the end of Batch 7 or after any recipe, emission, validation, or obligation change."
---
# Batch 7 Conformance and Gate Controller
Read `../references/afsm-v1.md` and validate reports against `contracts/framework-schema/batch-7-conformance-report.schema.json`. Compute coverage and fidelity per module; keep deterministic and Agent emissions separate.

Apply non-compensating blockers for lost endpoints, route/order/scope/security/validation/transaction/message/cache/scheduler/lifecycle semantics, secrets, placeholders and unreviewed high-risk patches. Require safe bootstrap/discovery/smoke/shutdown evidence. Report F-D only as eligibility for further verification, never production equivalence.

