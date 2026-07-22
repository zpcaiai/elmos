---
name: baseline-build-test
description: Establish dependency, compile, static-check, test and coverage baselines for an immutable source snapshot inside an approved ELMOS sandbox.
---

# Baseline Build Test

## Preconditions

Require `snapshotId`, parsed Build Model, approved image digest, enforced Sandbox Policy, artifact store and secret/network leases. If any are absent, emit `NOT_RUN` and block the Batch 2 gate.

## Workflow

1. Restore dependencies with lock/frozen modes where supported and lifecycle scripts disabled unless approved.
2. Run required safe generation/format steps as individually audited argv commands.
3. Compile/build, then static checks, unit tests and explicitly approved integration tests.
4. Collect coverage when configured.
5. Store redacted stdout/stderr, exit codes, durations, failed-test names and environment versions as evidence artifacts.
6. Classify dependency, environment, compile, test and policy failures separately.
7. Record existing source failures without modifying source code.
8. Bind every step and log to the same snapshot and environment digest.

## Hard boundaries

- Never execute customer commands in the control plane or on the host.
- Never let an Agent modify source while establishing the baseline.
- A source baseline failure is not evidence that a later migration caused it.
- Never report a baseline as passed when execution was simulated or `NOT_RUN`.

## Acceptance

Results are machine-readable and reproducible, with exact environment identity, step status, artifacts, test totals and known failures.
