---
name: flaky-nondeterminism-order-and-isolation-governor
description: Detect, reproduce, classify, quarantine, and remediate flaky tests caused by time, randomness, order, concurrency, network, data, resources, locale, or environment. Use when repeated attempts disagree or retries hide failures.
---

# Flaky and Nondeterminism Governor

## Prove flakiness

Hold code, artifact, test, environment, input, and seed constant, then repeat in the same process, new process, and new environment. Add random order, parallelism, resource pressure, network faults, time shifts, and seed variation as controlled detection modes. Preserve every attempt; report `FAILED_THEN_PASSED` instead of only the final pass.

## Classify cause and confidence

Classify time, randomness, order, shared state, concurrency, network, external service, test data, resource, port, filesystem, timezone, locale, eventual consistency, environment, or unknown. Advance confidence through suspected, reproduced, confirmed, root-cause identified, fixed-pending-validation, and fixed.

## Govern quarantine

Keep quarantined tests running and visible outside normal pass counts. Require owner, reason, due date, maximum duration, risk, and remediation task. Block new flaky tests in changed code and every flaky critical journey. Treat unknown flaky growth as review-required.

## Fix deterministically

Prefer fake clocks, fixed seeds, isolated data, unique ports, condition waits, deterministic ordering, synchronization, local virtual services, and resource reservations. Do not accept sleep or retry as a permanent fix. Validate repairs across multiple detection modes.

## Track cost

Measure flaky count/rate, quarantine age, mean time to repair, retry cost, and critical flaky count. Include these metrics in quality gates and release confidence.
