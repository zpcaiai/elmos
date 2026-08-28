---
name: benchmark-integrity-hidden-tests
description: Protect ETGB against memorization, leakage, self-authored Oracles, benchmark gaming and temporal contamination through isolated hidden tests and controlled variants.
---

# Benchmark Integrity and Hidden Tests

## Threats

- public benchmark memorization or Prompt overfitting;
- generation worker reading hidden expected outputs;
- target tests weakened or rewritten to pass;
- selection of only the best random seed;
- future fixes leaking into historical tasks;
- manual ignore rules added after observing a failure;
- hidden tests exposed through logs, traces, artifacts or model context.

## Partition model

Keep public fixtures, private hidden tests, customer-confidential tests and release-gate policy in separate permission domains. Transformation/generation workers never receive hidden-test read/write access. Validation workers execute hidden tests in a clean Environment and publish only permitted evidence.

## Anti-contamination methods

- exact commit and temporal cutoff;
- train/public/hidden/time-split partitions;
- paraphrased and structurally transformed requirements;
- parameter, schema, locale, timezone and data perturbations;
- semantics-preserving source refactors before conversion;
- metamorphic variants and independently generated properties;
- private incident regressions;
- canary cases introduced after candidate freeze.

## Test independence

The converter/generator may translate public source tests for compatibility, but an independent validator owns final acceptance. Snapshot expectations generated solely from the target under test are not valid Oracles.

## Leakage monitoring

Probe worker filesystem, tool calls, logs, traces, caches and evidence for hidden-test identifiers or content. Rotate leaked cases and record the affected candidate/evaluation. Never reveal a hidden-test corpus merely to explain a failure; create a minimized disclosure-safe reproduction.

## Statistical honesty

Run all declared seeds and report the distribution. No best-of-N cherry-picking. Keep failed and unavailable cases in the denominator according to published policy.

## Gate

Hidden-test read/write by unauthorized workers, target-test weakening, post-hoc scope changes or material leakage invalidates the evaluation, regardless of score.
