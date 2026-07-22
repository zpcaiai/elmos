# ADR-0041: Horizontal Security and Compliance Engine

## Status

Accepted for Batch 17 repository scope.

## Context

The six modernization execution engines and Composite control need one cross-cutting security estate, finding, exposure, risk, control, evidence, and authorization model. Adding scanners independently to each engine would duplicate policy, hide coverage gaps, and let execution components judge their own work.

## Decision

Add an independently deployable Java 21 `ELMOS_SECURITY_COMPLIANCE` worker on port 8091. Reuse shared Tenant, Identity, Secret Lease/Reference, Workflow, Runner, Risk Exception/Acceptance, Approval, Evidence, Audit, Billing, Portfolio, Delivery, and Authorization Decision authorities.

Security tools are isolated versioned adapters with deny-by-default network, declared targets, permissions, license, data handling, coverage, and false-positive policy. Active tests require explicit authorization. The control plane only evaluates policy; it cannot run scanners, mutate production, accept risk, or grant formal certification.

Keep Vulnerability, Finding, Exposure, Risk, Control Implementation, Control Assessment, and Authorization distinct. Treat no findings with incomplete coverage as `COVERAGE_INSUFFICIENT`. Bind internal authorization to immutable evidence and expiry; changes trigger reassessment.

## Consequences

Batch 17 adds 17 Runtime Skills, nine core schemas, 30 executable scenarios, a fail-closed worker/API, and Flyway V17 with 94 new tenant-isolated projections. Existing shared authorities are extended rather than duplicated. Real scanner execution, cloud/runtime telemetry, customer catalogs, active tests, risk approval, audit opinion, certification, and formal ATO remain external gates.
