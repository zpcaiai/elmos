---
name: test-quality-elmos-unified-evidence-integration
description: Map test estates, quality risks, portfolios, characterization, contracts, properties, mutations, test data/environments, AI candidates, flaky results, selections, gates, and learning into shared ELMOS evidence, delivery, audit, and billing. Use for cross-engine quality integration or offline evidence packs.
---

# Test Quality Unified ELMOS Integration

## Reuse shared authorities

Reference Organization, Repository, System Landscape, Migration Portfolio/Plan/Step, Risk, Approval, Evidence, Delivery Snapshot, Audit, and Billing. Store test-specific content under `scope=TEST_QUALITY`, `engine=ELMOS_TEST_QUALITY`, and a versioned `engineExtension`; do not create duplicate control-plane authorities.

## Normalize evidence and risk

Publish test estate/discovery/health, risk/coverage, portfolio, characterization, golden master, contract, property, mutation, data, environment, AI candidate, flaky, selection, quality gate, release confidence, continuous validation, and defect-learning evidence. Map test-count drops, critical uncovered risks, survived mutants, critical flaky journeys, virtual drift, and unreviewed AI tests to shared risks.

## Compose checks

Expose discovery, unit/component, contract, property, mutation, data, environment, flaky, business journey, quality risk, and release confidence checks. Compose them with language, client, database, infrastructure, security, and evidence-reliability gates. The quality gate sits above individual test reports.

## Audit and meter

Audit test deletion/disablement, quarantine, retry policy, snapshot/golden updates, AI promotion, mutant exclusion, gate override, conditional pass, and test-data access. Meter discovery, test minutes, environment hours, contract verification, property examples, mutants, browser/device minutes, data and AI generation, performance, and continuous validation without changing decisions.

## Package offline evidence

Create a signed manifest with `quality/estate`, `risks`, `portfolio`, `characterization`, `contracts`, `properties`, `mutations`, `test-data`, `environments`, `ai-tests`, `flaky`, `selection`, `gates`, and `continuous-validation`. Include hashes, provenance, current artifact binding, unknowns, and independent-verification instructions.
