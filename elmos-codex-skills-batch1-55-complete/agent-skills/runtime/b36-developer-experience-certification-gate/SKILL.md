---
name: b36-developer-experience-certification-gate
description: "Run the conservative Batch 36 developer-experience certification gate and emit certified limited experimental or blocked status from exact hosts protocols extensions CLI bots preview navigation provenance fixes conflicts ownership tests offline privacy holdout and evidence."
---

# Skill 1304: b36-developer-experience-certification-gate

## Use this skill when

- A Developer Experience Pack requests certification or release readiness.
- A reviewer needs one conservative decision across IDE, CLI, PR, local, offline, privacy, and evidence capabilities.

## Domain-specific risks and invariants

- A pack can appear complete while relying on mocks, stale source maps, permissive permissions, weak holdout evidence, or hidden cloud dependencies.
- Certification must not be granted by editing a status field.

## Workflow

1. Validate pack, support matrix, IDE protocol, extension manifests, CLI contract, PR-bot policy, navigation map, ownership, local-eval, authoring, offline, telemetry, evidence, and certification schemas.
2. Verify exact host/provider/OS versions, owners, artifact digests, permissions, trust boundaries, and representative workflow scope.
3. Run required real host, CLI, SCM sandbox, local preview, navigation, quick-fix, conflict, ownership, local-eval, authoring, review, offline, and privacy evidence checks.
4. Evaluate quantitative thresholds and zero-tolerance findings.
5. Emit gate result and report without mutating claimed evidence.

## Required repository outputs

- `certification/gate-result.json` and `certification/gate-report.md`
- Machine-readable failures linked to exact missing or invalid evidence
- Strongest support status justified by immutable evidence

## Verification

- Run the gate against intentionally incomplete and falsely certified packs.
- Verify every evidence reference resolves.
- Confirm holdout and representative workflow corpora are nonempty and independent.
- Re-run after artifact, host, protocol, policy, or permission changes.

## Stop and escalate when

- Any P0 workflow is unknown or only mock-tested where real evidence is required.
- Cross-tenant access, unauthorized repository writes, secret leakage, protected-code overwrite, test-integrity violation, telemetry violation, or stale critical source map exists.
- Offline mode has hidden network dependencies.
- Evidence, owner, version, permission, or artifact scope is ambiguous.

## Definition of done

- The gate deterministically emits certified, limited, experimental, or blocked.
- False certification is rejected.
- All required evidence and corpora are present.
- Only the strongest evidence-supported status is retained.
