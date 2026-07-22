---
name: b37-sdk-compatibility-versioning
description: "Implement SDK semantic versioning compatibility matrices deprecation adapters contract tests migration tooling and support windows across product editions."
---

# Skill 1319: b37-sdk-compatibility-versioning

## Use this skill when

- SDKs and product versions evolve.
- Existing extensions break during platform upgrades.

## Domain-specific risks and invariants

- False compatibility claims can disable migration workflows across many customers.
- Permanent compatibility shims create hidden security and maintenance debt.

## Workflow

1. Define product, protocol, ABI, SDK, schema, pack, and extension version axes.
2. Generate compatibility matrix and automated contract tests.
3. Implement deprecation notices, adapters, migration tools, telemetry, and removal dates.
4. Test N-1/N/N+1 and supported LTS combinations.
5. Require explicit waivers and exit dates for compatibility shims.

## Required repository outputs

- version policy and compatibility matrix
- contract test suites and migration tools
- deprecation and removal records

## Verification

- Run compatibility tests for every claimed combination.
- Verify unsupported combinations fail with actionable diagnostics.
- Verify deprecated APIs emit measurable warnings.

## Stop and escalate when

- A breaking change lacks migration tooling.
- Compatibility requires disabling security or policy checks.

## Definition of done

- Published support claims match automated tests.
- Extensions can upgrade or remain on documented LTS windows.
