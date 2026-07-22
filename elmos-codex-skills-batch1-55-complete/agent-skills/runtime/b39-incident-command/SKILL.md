---
name: b39-incident-command
description: "Implement and verify Batch 39 Skill 1356 for incident command. Use when work requires Incident Command和重大事故响应, typed evidence, negative and holdout validation, and a fail-closed certification decision."
---

# Incident Command和重大事故响应

## Operating mode

Work directly in the repository and preserve existing customer, tenant, security, and evidence boundaries. Read the shared Batch 39 contracts before changing code:

- `../../../docs/batch39/AUTHORITY.md`
- `../../../docs/batch39/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/batch39/QUALITY_GATES.md`
- `../../../docs/batch39/EVIDENCE_BOUNDARY.md`

Use `python scripts/mature_product_toolkit.py validate --batch 39` for structural checks. Use the scaffold and gate commands only against an explicit pack key and approved scope.

## Global constraints

- Bind every conclusion to an exact versioned scope, owner, evidence reference, and provenance reference.
- Keep development, negative, holdout, and representative workloads independent; never tune from holdout outcomes.
- Preserve unknown, unsupported, inaccessible, failed, and over-budget items in denominators and reports.
- Require explicit authorization before any external mutation, deployment, publication, merge, production access, or customer communication.
- Prefer deterministic typed contracts and bounded execution; prohibit unbounded fan-out, silent retries, fabricated evidence, and status-only certification.
- Keep the executor separate from the final certification authority and preserve human ownership of material risk acceptance.
- Stop on critical security, privacy, integrity, tenant-isolation, safety, legal, or evidence-provenance failures.
- Never weaken tests, policies, permissions, baselines, thresholds, or data boundaries merely to make a gate pass.

## Skill 1356: Incident Command和重大事故响应

Implement this capability as part of **Global SRE and platform operations**. The Batch objective is: Operate the migration platform to enterprise-critical reliability and support standards.

## Workflow

1. Inspect the current implementation, runtime facts, policies, incidents, decisions, and prior evidence relevant to `b39-incident-command`.
2. Freeze an exact scope and identify accountable product, engineering, security, operations, finance, legal, or customer owners as applicable.
3. Create or update the typed program, evidence, and certification artifacts; record known unknowns before implementation.
4. Implement the smallest production-shaped capability that exercises `Incident Command和重大事故响应` without bypassing existing control planes.
5. Run deterministic validation, negative cases, failure injection where safe, and independent holdout or representative workloads.
6. Record outputs, provenance, residual risks, authorization references, costs, and rollback or recovery evidence.
7. Run the Batch 39 conservative gate and accept only the strongest status supported by actual evidence.

## Required repository outputs

- `mature-product-packs/batch39/<pack-key>/program.json`
- `mature-product-packs/batch39/<pack-key>/evidence.json`
- `mature-product-packs/batch39/<pack-key>/certification.json`
- Capability-specific implementation, tests, run logs, evidence references, and residual-risk records for `b39-incident-command`
- `mature-product-packs/batch39/<pack-key>/gate-result.json` and `gate-report.md`

## Verification

- Validate all Batch 39 Skills, Schemas, templates, and local references.
- Reproduce the claimed capability from immutable inputs and compare outputs and side effects.
- Exercise rejected, unauthorized, degraded, rollback, and recovery paths in addition to the happy path.
- Confirm holdout and representative evidence was not used to tune the implementation or thresholds.
- Confirm every material claim links to raw evidence and an accountable owner.

## Stop and escalate when

- Scope, authority, provenance, required owners, safe test environments, or representative workloads are missing.
- The only available proof is a template, plan, mock, self-attestation, status field, or synthetic happy path.
- A critical regression, policy violation, privacy breach, tenant leak, unsafe external effect, or unrecoverable operation is observed.
- Certification would require hiding failures, excluding difficult scope, broadening permissions, or weakening acceptance criteria.

## Definition of done

The capability has typed artifacts, executable implementation or an explicit `BLOCKED` boundary, deterministic and negative tests, independent evidence, residual-risk ownership, and a conservative Batch 39 gate result. Unexecuted field evidence remains `NOT_RUN`; no package-level test may be represented as production certification.
