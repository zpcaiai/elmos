---
name: legacy-test-discovery-normalization-and-health-assessment
description: Discover, normalize, identify, and assess legacy automated, scripted, manual, hidden, disabled, and quarantined tests across repositories and historical systems. Use for test estate inventory, count reconciliation, stable test identity, test smells, or historical health.
---

# Legacy Test Discovery and Health Assessment

## Discover from multiple sources

Inspect source, builds, CI, test-management systems, spreadsheets, tickets, wikis, shell scripts, schedulers, manual checklists, and production runbooks. Detect JUnit/TestNG, MSTest/NUnit/xUnit, pytest/unittest/nose, Jest/Vitest/Mocha/Jasmine/Karma, Playwright/Cypress/Selenium/Appium, SQL/data/model tests, and infrastructure checks without trusting a single runner report.

## Create stable identities

Build each identity from repository, module, framework, suite, class or file, logical method/scenario, parameter signature, and environment profile. Persist a stable hash and distinguish active, disabled, ignored, skipped, quarantined, orphaned, unexecutable, duplicate, manual-only, and unknown tests.

## Reconcile counts

Record source, discovered, executed, and reported counts separately. Emit a blocking finding for every unexplained difference. Bind historical results to the same immutable snapshot and environment profile.

## Assess strength and health

Detect no assertion, sleep, shared mutable state, order dependency, real network, hard-coded port, production credential, broad exception, conditional assertion, unseeded randomness, excessive mocks, oversized snapshots, disabled tests, and always-passing tests. Calculate pass/failure rate, duration, flaky observations, last run/failure, owner, runtime, and environment. Classify health as healthy, degraded, flaky, stale, unmaintained, unexecutable, or unknown.

## Emit artifacts

Produce `test-estate.json`, `test-discovery-snapshot.json`, `test-case-identities.json`, `test-framework-inventory.json`, `test-health.json`, `test-smells.json`, and `manual-test-inventory.json` with evidence references.
