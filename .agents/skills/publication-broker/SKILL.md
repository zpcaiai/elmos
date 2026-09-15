# publication-broker

**Priority:** P1

## Purpose
Certified checkpoint to PR/merge/tag/release/deploy through separate authority.

## Contract
- Non-routable implementation Skill; existing Elmos route owners remain canonical.
- MUST fail closed when policy, runtime capability, provenance or evidence semantics cannot be preserved.
- MUST emit machine-readable timeline events and typed artifacts for material state changes.
- MUST NOT treat model prose as authority, execution proof or certification evidence.

## Done when
Acceptance, negative, recovery and replay cases in `acceptance.yaml` pass against the target Elmos integration.
