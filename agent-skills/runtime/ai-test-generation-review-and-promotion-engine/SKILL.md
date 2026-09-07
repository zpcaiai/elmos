---
name: ai-test-generation-review-and-promotion-engine
description: Generate traceable AI test candidates from changes, requirements, contracts, threats, risks, mutants, defects, gaps, or failure traces and govern their review and promotion. Use for agent-assisted test creation or regression generation.
---

# AI Test Generation, Review, and Promotion

## Minimize context

Provide only the target symbol, public contract, existing test pattern, risk, fixture API, build command, allowed tools, and related failure. Record candidate ID, source, target, model/provider, context hash, generated files, and evidence. Avoid sending an entire repository.

## Treat output as a candidate

Allow unit, component, contract, property, integration, regression, negative, security, data, and model candidates. Start at `GENERATED`; never auto-promote.

## Run the promotion pipeline

Require parse/compile, execution, fail-before-fix, pass-after-fix, isolation, repeatability, mutation effectiveness, and human review before promotion. If a regression was not proven to fail on the defect version, do not label it a defect-regression test.

## Reject weak behavior

Reject tests that mock the subject, assert true/not-null only, catch all exceptions, copy the implementation, create meaningless snapshots, modify production logic for convenience, sleep, use uncontrolled networks, or omit random seeds. Do not delete tests, lower assertions, add retries to hide failure, modify gates, auto-update golden masters, or change production logic.

## Learn from review

Record approval/rejection reasons, killed mutants, defects found, maintenance cost, flaky behavior, and later removal. Feed accepted patterns and rejected anti-patterns back into candidate generation without bypassing review.
