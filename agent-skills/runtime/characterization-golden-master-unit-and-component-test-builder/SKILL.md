---
name: characterization-golden-master-unit-and-component-test-builder
description: Capture legacy behavior and create reviewed characterization, golden-master, unit, and component test candidates without claiming observed behavior is correct. Use before risky migration, refactoring, snapshot approval, or behavior-preservation work.
---

# Characterization and Golden Master Builder

## Observe before changing

Capture function outputs, exceptions, HTTP, messages, database effects, files, logical state, visuals, model outputs, and CLI behavior against an immutable legacy artifact. Record inputs, environment, time/random controls, side effects, and evidence references.

## Separate defects

Mark known incorrect legacy behavior as `BASELINE_DEFECT`. Choose `PRESERVE_FOR_MIGRATION` or create a separate approved fix change. Never silently correct a known defect inside the same migration step.

## Normalize narrowly

Declare exact normalization for timestamps, UUIDs, sequences, generated IDs, paths, hosts, ordering, locales, random values, and dynamic headers. Reject rules that discard an entire response/body or otherwise remove meaningful differences.

## Govern snapshots

Support text, JSON, XML, binary hashes, database state, message sequence, image, PDF, and model output. Require capture, human review, approval, and signing. Never let generated output automatically become expected output.

## Build candidates

Prefer unit candidates for pure functions, domain rules, parsers, validators, mappers, calculations, and state transitions. Use component tests for framework components, in-process services, frontend components, repositories, data transforms, and model preprocessors. Grade assertions from no-assert through invariant, side effect, error, and sequence; require strong assertions for risk coverage.
