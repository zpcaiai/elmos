# M38–M45 certification evidence protocol

This protocol is shared by the conservative Migration Pack gates for Batches 38–45. It is an engineering contract, not a statement that field evidence has run.

## Required binding

A certification attempt must provide `evidence-manifest.json` conforming to `schemas/mature-product/evidence-manifest.schema.json`. The manifest binds the exact artifact and environment files, execution interval and replay command, separate executor and independent verifier identities, authorization references, raw evidence roles, and one untouched holdout plus one representative corpus. Every file reference is pack-relative and is verified against its byte count and SHA-256 digest.

Every passing claim must resolve its evidence and provenance IDs through the manifest. Evidence IDs, paths, and digests are unique. Execution, provenance, and verification roles are mandatory. Holdout and representative corpus digests must differ and both declare `authoringAccess=false`.

## External certification authority

Certification additionally requires a byte-for-byte signed `certification-request.json`, a detached `certification-request.sig`, and a separate trust store. The request binds the program, evidence, certification, and evidence-manifest digests. Revoked, unknown, wrong-Batch, stale, future-dated, out-of-scope, or invalid signatures fail closed. The program owner must be among the manifest approvals and signed request approvers.

## Batch 45 aggregation

Batch 45 cannot override domain failures. Its evidence manifest must bind exact `CERTIFIED` and `eligible=true` gate results for Batches 38–44, at least two distinct customer evidence records, and at least one independent-review record. Missing or failed domain gates, customer evidence, or independent review block the final gate.

## Evidence boundary

The synthetic signed fixture in `tests/mature_product_gate_test.py` exercises gate logic only. It is not customer, production, independent-assessment, disaster-recovery, financial, or field evidence. Checked-in certification remains `NOT_RUN` unless real authorized evidence is supplied to the gate.
