---
name: b36-developer-workflow-factory
description: Implement and certify a production-shaped IDE CLI and pull-request-native developer workflow pack with exact host versions protocols permissions local execution ownership navigation review privacy and evidence boundaries.
---

# Skill 1287: b36-developer-workflow-factory

## Use this skill when

- A repository needs a complete developer-facing workflow spanning IDE, CLI, pull requests, local preview, review, and certification.
- Several Batch 36 capabilities must be coordinated for one exact migration route and customer workflow.

## Domain-specific risks and invariants

- A polished UI can still hide unsafe repository writes, stale source maps, unbounded local agents, or unverifiable results.
- IDE, CLI, and bot behavior must resolve to the same immutable artifacts, policies, and evidence as the control plane.

## Workflow

1. Inspect Batch 21-35 contracts, repository topology, source maps, ownership metadata, policies, build/test commands, and existing developer tools; create a developer-workflow gap inventory.
2. Confirm accountable product, developer-experience, security, migration-engine, repository, and customer owners plus exact IDE, SCM, operating-system, route, and workload scope.
3. Scaffold a Developer Experience Pack and lock host versions, protocol versions, permissions, sandbox, telemetry, and certification profile.
4. Implement the smallest production-shaped path from local preview to source-target navigation, explainability, quick fix, affected tests, review, and pull-request evidence.
5. Run development and negative corpora, then untouched holdout and representative developer workflows.
6. Run the conservative Batch 36 gate and retain only the strongest evidence-supported status.

## Required repository outputs

- `developer-experience-packs/<pack-key>/pack.json`, `support-matrix.json`, protocol and policy contracts
- IDE/CLI/PR artifacts, signed extension manifests, local-eval evidence, ownership and navigation maps
- Independent development, negative, holdout, and representative-workflow corpora
- `certification/{evidence.json,certification.json,gate-result.json,gate-report.md}`

## Verification

- Run all Batch 36 schema, pack, protocol, navigation, policy, and gate validators.
- Build and launch real extensions or approved host harnesses for every claimed IDE.
- Execute the real CLI and PR bot in isolated repositories with negative permission tests.
- Replay local preview and affected-test workflows from immutable manifests.
- Verify every evidence reference resolves to an immutable file or approved external reference.

## Stop and escalate when

- Exact host, SCM, artifact, route, owner, policy, or workflow scope is missing.
- The workflow requires unrestricted filesystem, shell, repository-write, secret, or network access.
- Source maps are stale, ownership is ambiguous, protected code could be overwritten, or a P0 workflow is unknown.
- Certification relies only on mocks where a real extension, CLI, SCM, or local build is required.

## Definition of done

- One exact end-to-end developer workflow is independently usable without direct database edits or privileged operator intervention.
- All repository outputs validate and include exact versions, digests, permissions, and evidence.
- Negative tests prove unauthorized writes, secret access, protected-region overwrite, and telemetry leakage are blocked.
- Holdout and representative workflows meet the approved profile with no unresolved P0 unknowns.
- The conservative gate emits only the strongest status supported by actual evidence.
