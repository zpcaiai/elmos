# ADR-0054: Evidence-bound Operations, SRE and ITSM loop

## Status

Accepted on 2026-07-22.

## Decision

Implement Batch 25 as a shared operations graph without allowing correlation or AIOps to become decision authority. Incident command, root cause, Change, SLO, remediation and continuity remain distinct. Automated remediation requires bounded blast radius, verification, rollback and approval. Store projections in `operations_sre`.

## Consequences

The engine may propose hypotheses and prepare actions but cannot confirm root cause, close major Incidents or approve high-risk Changes. Business recovery evidence is required in addition to technical command success.
