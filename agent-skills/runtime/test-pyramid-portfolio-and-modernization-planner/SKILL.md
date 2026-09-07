---
name: test-pyramid-portfolio-and-modernization-planner
description: Design a risk-based target test portfolio and modernization DAG using feedback speed, realism, diagnosis, maintenance, environment cost, and business coverage. Use for test pyramid correction, E2E reduction, integration expansion, or modernization sequencing.
---

# Test Portfolio and Modernization Planner

## Avoid fixed percentages

Do not impose a universal 70/20/10 pyramid. Evaluate static, unit, component, contract, integration, system, E2E, business-journey, manual exploratory, and production-validation layers by purpose, risk, feedback time, defect localization, realism, maintenance, environment cost, flaky risk, and business coverage. Add property, mutation, visual, accessibility, security, performance, resilience, data-quality, and model-validation tests where the risk requires them.

## Diagnose the estate

Identify ice-cream-cone, hourglass, mock-tower, manual-dependence, and coverage-illusion portfolios. Preserve critical system journeys even when redundant brittle E2E cases can move down to component/unit tests. Promote up to real integration when mocks hide dependency behavior.

## Plan transformations

Assign `PRESERVE`, `REPAIR`, `REWRITE`, `SPLIT`, `PROMOTE_DOWN`, `PROMOTE_UP`, `REPLACE_WITH_CONTRACT`, `REPLACE_WITH_PROPERTY`, `AUTOMATE_MANUAL`, or `RETIRE_DUPLICATE`. For every risk, specify the required layer, frequency, environment, owner, cost, prerequisites, and evidence gate.

## Build the DAG

Sequence discovery, stabilization, characterization, unit/component, contract, real integration, property, mutation, redundant-E2E reduction, and continuous gates. Do not retire a legacy test until equivalent risk coverage is proven and approved.
