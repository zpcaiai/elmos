---
name: elmos-policy-supply-chain-signing
description: Centralize authorization and release policy, generate supply-chain evidence,
  scan dependencies and outputs, and verify signatures before execution or promotion.
version: 1.0.0
priority: P1
phase: G7
dependencies:
- elmos-identity-tenant-security
- elmos-reproducible-toolchain
- elmos-secure-sandbox-runtime
---

# Policy as Code, SBOM, SLSA Provenance, and Artifact Signing

## Objective

Make security, compliance, license, model, tool, network, and release decisions explicit, versioned, testable, and auditable.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Policy as Code, SBOM, SLSA Provenance, and Artifact Signing** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-identity-tenant-security`
- `elmos-reproducible-toolchain`
- `elmos-secure-sandbox-runtime`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- Enforcement occurs at the operation boundary, not only in reports.
- Policy exceptions are scoped, approved, expiring, and visible.
- Production inputs and outputs are immutable and signed where required.
- A successful build cannot override a failed supply-chain policy.

## Required inputs

- Tenant/org policy and data classifications.
- Toolchain, rules, skills, dependencies, models, artifacts, and evidence.
- Vulnerability/license/signing/trust configuration.

## Required outputs

- `Versioned policy bundles and decisions.`
- SBOM, SCA, license, secret, image, and dependency-confusion results.
- `SLSA-style provenance and signatures.`
- `Release enforcement and exception evidence.`

## Repository discovery

Before editing:

1. Locate `AGENTS.md`, `CLAUDE.md`, repository-local Skills, architecture decision records, manifests, schemas, migrations, and build commands.
2. Identify actual control-plane, workflow, runner, engine, web, database, object-store, policy, telemetry, and test modules; do not assume the reference layout exists.
3. Search for existing contracts and implementations before creating duplicates.
4. Record current behavior, known gaps, security boundaries, external side effects, and the exact validation commands that are available.
5. Create or update a durable implementation plan from `templates/IMPLEMENTATION-PLAN.yaml`.

## Execution workflow

1. Select the smallest dependency-resolved vertical slice.
2. Freeze input snapshots, schema/toolchain/policy versions, and rollback boundaries.
3. Implement contract/schema changes before consumers, using backward-compatible transitions.
4. Implement production behavior, authorization, idempotency, telemetry, audit, failure handling, tests, documentation, and runbooks together.
5. Execute focused tests, integration tests, race/failure tests, security tests, and clean-environment reproduction as applicable.
6. Save large outputs by digest; record commands, results, durations, cost, evidence, and residual risk.
7. Report autonomous **system wall-clock runtime** separately from human-equivalent engineering/review effort.
8. Never claim production completion from generated files or static validation alone.

## Implementation checklist

### Policy engine and contract

- [ ] `ELMOS-POL-001` Integrate OPA/Rego or equivalent with versioned signed policy bundles.
- [ ] `ELMOS-POL-002` Define decision input/output with subject, tenant, resource, action, context, policy digest, allow/deny, rules, reasons, obligations, and expiry.
- [ ] `ELMOS-POL-003` Evaluate user/resource authorization, runner/action, sandbox, egress, secrets, model/provider, cache sharing, artifact export, license, vulnerability, budget override, approval, and production promotion.
- [ ] `ELMOS-POL-004` Cache only safe policy decisions with exact identity/context and short TTL.
- [ ] `ELMOS-POL-005` Fail closed for high-risk operations when policy is unavailable.
### Exception governance

- [ ] `ELMOS-POL-006` Require owner, scope, justification, compensating controls, approver, creation, expiry, and ticket for exceptions.
- [ ] `ELMOS-POL-007` Prevent permanent wildcard exceptions.
- [ ] `ELMOS-POL-008` Warn before expiry and automatically stop applying expired exceptions.
- [ ] `ELMOS-POL-009` Include exceptions in risk/evidence/certification decisions.
- [ ] `ELMOS-POL-010` Audit creation, use, renewal, and revocation.
### SBOM and dependency assurance

- [ ] `ELMOS-POL-011` Generate SBOM for toolchain images, adapters, skills/rules where applicable, and generated/converted projects.
- [ ] `ELMOS-POL-012` Scan vulnerabilities, licenses, secrets, containers, lockfiles, unpinned dependencies, typosquatting, dependency confusion, malicious packages, and provenance gaps.
- [ ] `ELMOS-POL-013` Distinguish source, build, test, runtime, optional, and transitive dependencies.
- [ ] `ELMOS-POL-014` Define severity/age/exploitability/usage-aware blocking policy.
- [ ] `ELMOS-POL-015` Rescan retained deliverables as intelligence changes and issue updated evidence without mutating old packs.
### Build provenance

- [ ] `ELMOS-POL-016` Generate provenance recording builder identity/version, source snapshot, action, toolchain, dependencies, parameters, policy, environment, outputs, and timestamps.
- [ ] `ELMOS-POL-017` Bind provenance to immutable digests and authenticated isolated builders.
- [ ] `ELMOS-POL-018` Prevent unsigned/untrusted builders from publishing production cache/results.
- [ ] `ELMOS-POL-019` Store provenance in CAS/evidence and make it independently verifiable.
### Signing and verification

- [ ] `ELMOS-POL-020` Sign OCI images, toolchains, Skill packages, Rule packs, plugins, generated artifacts, release archives, and Evidence Packs according to policy.
- [ ] `ELMOS-POL-021` Verify signatures/trust before runner execution, package installation, cache promotion, and release.
- [ ] `ELMOS-POL-022` Support keyless/managed and enterprise offline roots with rotation and revocation.
- [ ] `ELMOS-POL-023` Quarantine unsigned, invalid, revoked, or provenance-mismatched objects.
- [ ] `ELMOS-POL-024` Publish checksums and verification commands.
### Release gates

- [ ] `ELMOS-POL-025` Combine authorization, sandbox, tests, behavior, security, SBOM, license, provenance, signature, evidence, cost, and approval decisions.
- [ ] `ELMOS-POL-026` Return exact blocking reasons and remediation rather than a generic failure.
- [ ] `ELMOS-POL-027` Prevent an agent or project configuration from weakening organization policy.
- [ ] `ELMOS-POL-028` Record every gate input digest and decision for deterministic replay.

## Required artifacts

At minimum, produce or update:

- Versioned contracts and schemas.
- Database migrations and compatibility/rollback notes where state changes.
- Production implementation with explicit authorization, idempotency, retries, cancellation, and failure classification as applicable.
- Unit, integration, end-to-end, race/failure, and security tests appropriate to risk.
- OpenTelemetry instrumentation, operational metrics, alerts, and runbooks for production components.
- Audit/evidence records with immutable input and output digests.
- Updated architecture and operational documentation.
- Task report based on `templates/TASK-REPORT.md`.

## Validation

- [ ] Attempt prohibited model/tool/egress/export operations and enforce denial.
- [ ] Use expired/wildcard exceptions and reject them.
- [ ] Inject critical vulnerable, unpinned, typosquatted, and forbidden-license dependencies.
- [ ] Tamper with signed artifacts/provenance and reject execution/promotion.
- [ ] Take policy service offline during a high-risk operation and fail closed.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] Policy is versioned, tested, signed, enforced, and evidenced.
- [ ] Production execution and promotion reject untrusted supply-chain inputs.
- [ ] Every exception is bounded and certification-visible.
- [ ] Artifacts are traceable to authenticated inputs and builders.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
