---
name: quality-risk-model-and-requirement-coverage-graph
description: Build a versioned quality-risk model and evidence-strength coverage graph linking tests to requirements, contracts, components, journeys, risks, and failure modes. Use for critical-risk coverage, residual risk, quality debt, or release-risk analysis.
---

# Quality Risk and Coverage Graph

## Model risk independently from code coverage

Model business capabilities, journeys, requirements, contracts, components, symbols, data assets, and infrastructure resources. Version the weights for business criticality, change size/complexity, dependency centrality, runtime exposure, defect/incident history, code complexity, data sensitivity, test gaps, survived mutants, flaky rate, and owner confidence.

Compute inherent risk from impact, likelihood, change exposure, and dependency impact. Compute residual risk only after evidenced effective test and operational controls. Preserve `UNKNOWN`; never coerce it to low risk.

## Build coverage edges

Link tests with `TESTS_REQUIREMENT`, `TESTS_CONTRACT`, `TESTS_COMPONENT`, `TESTS_JOURNEY`, `TESTS_RISK`, and `TESTS_FAILURE_MODE`. Grade strength as declared, inferred, execution-observed, fault-detection-proven, or human-verified. Treat name matching as inferred only; require traces or killed mutants for stronger claims.

## Find gaps and debt

Classify each requirement as covered, partially covered, uncovered, coverage unknown, or covered by manual testing. Block critical uncovered risk. Track no test, weak assertion, over-mocked, flaky, slow, duplicate, manual-only, no contract, no test data, and no owner as quality debt.

## Emit evidence

Produce versioned risk model, requirement-test graph, risk-test graph, coverage, gaps, and debt artifacts. Include source snapshot, model version, edge provenance, evidence references, and unresolved unknowns.
