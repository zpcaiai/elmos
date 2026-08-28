---
name: elmos-functional-assurance-certification-skills
description: Independently evaluate, certify, monitor, revoke and recertify the functional and production claims of exact Elmos-generated systems.
version: 4.1.0
status: production-contract
priority: P0
risk: critical
route_owner: domain-pack.project-generation
routable: false
---

# Elmos Functional Assurance & Certification Skills

## Objective

Turn exact, immutable evidence into bounded functional assurance and certificate decisions without changing the candidate.

## Package Boundary

- Source total package: `elmos-ai-native-project-factory-total-skills-v4.0.0`.
- This split contains 178 of 474 Skills and 112 of 376 Adapters.
- No Skill or Adapter overlaps the companion package.
- Shared canonical JSON Schemas and API contracts are intentionally duplicated byte-for-byte as an interoperability plane.
- K8 remains the only Elmos completion authority; external accredited/statutory certification remains independent.

## Required Workflow

1. Resolve exact Goal and RevisionSet.
2. Load local Skill dependencies and declared cross-package interfaces.
3. Enforce Environment-owned authority, lease/fencing and side-effect reconciliation.
4. Produce immutable artifacts and evidence.
5. Review evidence independently, apply decision rules, issue a bounded certificate or a typed BLOCKED result, and maintain surveillance/revocation.

## Definition of Done

- Local dependency graph validates.
- External dependencies are declared, version-bounded and not silently vendored.
- Native, negative, failure and authority-denial evidence is preserved.
- No file count, mock, LLM review or self-assertion is promoted to E4/E5/P05.
