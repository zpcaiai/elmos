# ADR-0044: Evidence-bound enterprise platform conformance

## Status

Accepted for cross-language Batch 12 repository scope on 2026-07-21.

## Context

Batch 1–11 form a migration engine, while enterprise delivery also requires tenant isolation, federated identity, policy and approvals, private execution, model governance, accurate metering, audit/provenance, data sovereignty, offline delivery and recoverability. Existing governance and commercial modules already own many runtime primitives. Copying those authorities would create conflicting tenant, billing and audit truths, while letting the platform judge perform privileged work would make synthetic repository results indistinguishable from field evidence.

## Decision

Add `modules/enterprise-platform` as a cross-language evidence conformance layer. Reuse existing enterprise-governance, commercial, infrastructure, security and quality domains through seven explicit authority ports. Admit only one immutable, signed platform version with Batch 1–11 provenance, require all five deployment modes, and evaluate T-A through T-G sequentially without averaging or cross-mode compensation.

Keep untrusted execution and production mutations outside this module. It cannot execute customer code or host commands, provision IAM, access keys, bill, delete, install or change production. Evidence must carry the assessment run, platform version, authority, observation time and references. Missing or mismatched evidence fails closed; authority exception detail is sanitized.

Make enterprise delivery readiness a model invariant: only T-G, complete external evidence, zero blockers/critical risks and five independently ready deployment modes can set it. Persist `production_operation_executed=false`. Write only atomic, append-only artifacts outside the platform repository and reject symbolic-link paths.

## Consequences

Repository tests can establish deterministic policy, schemas, output layout and fail-closed behavior. They cannot prove a customer SSO/SCIM integration, private Runner, KMS rotation, charge, deletion, private/offline installation, HA/DR exercise or customer acceptance occurred. Those claims stay `NOT_RUN` until an approved external authority supplies exact-version evidence.
