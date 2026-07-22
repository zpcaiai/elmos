---
name: b37-evidence-collector-sdk
description: "Implement an Evidence Collector SDK for immutable typed artifacts digests signatures source links privacy classification retention and certification references."
---

# Skill 1312: b37-evidence-collector-sdk

## Use this skill when

- Extensions need to emit evidence accepted by platform gates.
- Current collectors write arbitrary logs or mutable files.

## Domain-specific risks and invariants

- Evidence forgery or mutable references invalidate certification.
- Collectors can accidentally export customer source or secrets.

## Workflow

1. Define evidence envelope, artifact identity, digest, producer, scope, timestamps, source links, privacy class, retention, signature, and validation status.
2. Generate collector APIs and local/remote sinks.
3. Implement content-addressed storage and append-only indexing.
4. Add redaction and DLP hooks before egress.
5. Test tampering, stale links, duplicate IDs, clock skew, and deletion policy.

## Required repository outputs

- evidence collector SDK and envelope schema
- reference local collector and verifier
- tamper and privacy negative corpus

## Verification

- Verify every evidence ref resolves and digest matches.
- Attempt tampering and cross-tenant reference attacks.
- Check retention and deletion behavior.

## Stop and escalate when

- Required evidence cannot remain inside approved data boundary.
- Signature or trustworthy timestamp is unavailable for a claimed certification.

## Definition of done

- Third-party collectors produce gate-consumable immutable evidence.
- Tampered or cross-tenant evidence is rejected.
