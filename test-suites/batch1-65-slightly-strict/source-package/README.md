# ELMOS Batch 1–65 Slightly Strict Test Skills

This package provides an independent, moderately adversarial test suite for the **ELMOS Batch 1–65 Complete Package**.

## Inventory

- Source ELMOS Skills covered: **1,296**
- Batch-specific test Skills: **65**
- Cross-batch and release-gate Skills: **23**
- Total test Skills: **88**
- Core test cases: **750**
- Batch coverage: **1–65**
- Product lines: Legacy Modernization and Project Synthesis

## Test Model

Each Batch receives eight core cases:

1. representative success;
2. boundary and moderate scale;
3. malformed or contradictory input;
4. dependency failure and recovery;
5. security and tenant isolation;
6. replay and idempotency;
7. version and schema drift;
8. evidence tamper and anti-fraud.

Twenty-three cross-batch Skills add end-to-end, interoperability, traceability, policy, multitenancy, supply-chain, sandbox, recovery, regeneration, anti-cheating, deployment, scale, Domain Pack, multi-agent, approval, parity, audit and final release certification.

## Layout

```text
agent-skills/runtime/<test-skill-name>/SKILL.md
CASE_CATALOG.json
CASE_CATALOG.csv
COVERAGE_MATRIX.csv
SKILL_CATALOG.csv
manifest.json
references/
schemas/
examples/
scripts/
subpackages/
```

## Install

```bash
./install.sh ~/.codex/skills
```

Review collisions before using `--overwrite`.

## Validate

```bash
./validate.sh
```

## Evaluate a Test Run

```bash
python3 scripts/evaluate_results.py results.json
```

The evaluator applies the slightly strict profile. Critical failures and anti-fraud signals are non-compensating.
