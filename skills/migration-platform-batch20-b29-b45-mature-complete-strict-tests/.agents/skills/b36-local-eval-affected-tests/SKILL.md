---
name: b36-local-eval-affected-tests
description: Implement local evaluation and affected-test execution from semantic impact graphs with exact toolchains sandboxing budgets deterministic results and escalation to broader suites.
---

# Skill 1299: b36-local-eval-affected-tests

## Use this skill when

- Developers need fast local feedback after migration edits or conflict resolution.
- The platform must select tests from semantic impact rather than run only manually chosen happy paths.

## Domain-specific risks and invariants

- Under-selection can miss critical regressions; over-selection makes local workflows unusable.
- Local tests can differ from certified runners due to toolchain, data, service, or network drift.

## Workflow

1. Define exact local-eval profile, toolchain, commands, fixtures, services, sandbox, resource limits, timeouts, and remote fallback.
2. Use changed symbols, call graph, dependency graph, routes, entities, transactions, messages, and ownership to select affected tests.
3. Run parse, build, static, focused, module, contract, behavior, and security tests according to risk.
4. Compare local results with certified-runner results and record environment differences.
5. Add calibration corpora measuring precision, recall, latency, flakiness, and missed-regression rate.

## Required repository outputs

- `local-eval/profile.json`, impact-selection manifest, result schema, replay command
- Toolchain/container manifests, fixture digests, local/remote parity evidence
- Calibration, flakiness, timeout, cancellation, and representative workflow results

## Verification

- Seed known regressions and verify affected-test selection catches them.
- Measure selection precision and recall against full suites.
- Test stale graph, missing services, wrong toolchain, offline mode, cancellation, and resource exhaustion.
- Verify local failures are replayable remotely.

## Stop and escalate when

- Impact graph or test inventory is stale or incomplete for a P0 change.
- Local environment cannot reproduce required services or data safely.
- A P0 change would run only focused tests without broader required suites.
- Local/remote divergence is unresolved.

## Definition of done

- Affected-test recall and developer feedback latency meet the profile.
- P0 changes execute all mandated suites.
- Results are deterministic or explicitly flaky and replayable.
- Local and certified-runner evidence agree within approved limits.
