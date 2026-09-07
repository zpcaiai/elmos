---
name: test-readiness-analyzer
description: Assess unit, integration and coverage readiness for an ELMOS migration. Use for test inventory, framework detection, baseline comparison, coverage artifacts, or test-gap risk.
---
# Test Readiness Analyzer

## Workflow
1. Count production and test sources by module and source set.
2. Detect test frameworks, integration-test conventions and coverage plugins.
3. Prefer executed baseline/coverage artifacts over file-count proxies.
4. Emit ratios, missing layers, flaky/disabled evidence and status.

## Acceptance
- File ratios are not represented as coverage percentages.
- No tests or unknown build evidence reduces readiness.
- Planning requires baseline and migrated test evidence gates.

