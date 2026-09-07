# ELMOS Codex Skills — Batch 1–55 Slightly Strict Test Suite

## Inventory

- Foundation testing Skills: **16**
- Batch-specific certification Skills: **55**
- Total Skills: **71**
- Machine-readable baseline test cases: **660**
- Test cases per numbered Batch: **12**

## Package groups

- Foundation: shared architecture, data, environments, contracts, property/fuzz/mutation,
  differential tests, security, performance, chaos and release gates.
- Batch 1–19: migration engine and early platform capabilities.
- Batch 20–39: platform, route, framework, data, cloud, identity, runner, evidence,
  policy and finance capabilities.
- Batch 40–55: enterprise and industry domain planning-edition capabilities.

## Install

```bash
./install.sh ~/.codex/skills
```

## Validate

```bash
./validate.sh
```

## Gate strength

- P0: 100% pass.
- Critical P1: 100% pass or approved expiring waiver.
- Ordinary P1: >=98% pass.
- Critical mutation score: >=80%.
- P95 latency regression: <=10% unless approved.
- Flaky quarantine: <=7 days.

## Trust boundary

This package is a test design and execution Skill suite. Static package validation
does not mean Batch 1–55 implementations passed their tests. Real certification
requires execution in the target repository and immutable evidence.
