# Skill Benchmark: java-modernization-runtime

**Model**: current-session-inline
**Date**: 2026-07-20T17:04:33Z
**Evals**: 1, 2, 3 (1 with-skill run each; no baseline)

## Summary

| Metric | With Skill | Baseline | Interpretation |
|--------|------------|----------|----------------|
| Pass Rate | 100% (12/12) | Not run | No comparative uplift claim |
| Time | Not captured | Not run | Inline harness telemetry unavailable |
| Output size | 831 chars mean | Not run | Not provider token usage |

## Analysis

- All three single-run evaluations passed, so there is no within-evaluation variance to analyze.
- Sub-agent delegation is disabled for this task, therefore no without-skill baseline was run. The generated JSON delta is a missing-baseline artifact, not measured skill uplift.
- Coverage exercises fail-closed edge cases across recipe licensing, constrained repair, independent validation, and delivery governance. It does not replace live Docker, provider, SCM, or signing-key integration tests.
