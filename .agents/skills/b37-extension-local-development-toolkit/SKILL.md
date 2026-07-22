---
name: b37-extension-local-development-toolkit
description: Implement a local extension development toolkit with project templates code generation test fixtures emulators debug tracing packaging and deterministic reproducible builds.
---

# Skill 1316: b37-extension-local-development-toolkit

## Use this skill when

- Extension authors need a supported local workflow.
- Publisher onboarding is blocked by undocumented internal build steps.

## Domain-specific risks and invariants

- Local emulators can diverge from production and create false confidence.
- Developer tools can leak credentials or customer artifacts.

## Workflow

1. Create templates for every SDK kind.
2. Generate typed clients, schemas, fixtures, sample data, test runners, debugger integration, and local sandbox launcher.
3. Pin toolchains and dependencies and emit reproducible build manifests.
4. Compare emulator behavior with certified runtime conformance tests.
5. Document offline mirrors and credential-free development.

## Required repository outputs

- extension developer CLI and templates
- `local sandbox/emulator and debug tooling`
- reproducible package manifest

## Verification

- Build sample extensions from a clean checkout.
- Run parity tests between local and certified sandbox.
- Verify no production credentials are needed.

## Stop and escalate when

- Local development requires customer secrets or production connectivity.
- Emulator parity is below approved threshold.

## Definition of done

- A new publisher can scaffold, test, debug, package, and validate an extension locally.
- Build output is reproducible.
