# ELMOS Codex Skills — Batch 105–108

This package extends the Batch 97–104 product core with a customer-visible modernization proof loop:

```text
Modernization Golden Route
  → Polyglot Ephemeral Preview Runtime
  → Live API / Browser / Streaming Validation
  → Evidence-rich PR / Executive Report / Commercial Certificate
```

## Inventory

- **4 Batches**: 105–108
- **64 implementation Skills**: 16 per Batch
- **64 executable JSON contracts**
- **1 acyclic Capability Graph**
- **7 JSON Schemas**
- **4 polyglot Runtime Manifest examples**
- **4 reusable templates**
- installer, compiler, execution planner, conservative gate and unit/negative tests

| Batch | Theme | Closure Skill |
|---:|---|---|
| 105 | Modernization Demonstration Golden Routes | `modernization-demo-route-certifier` |
| 106 | Polyglot Ephemeral Preview Runtime | `preview-runtime-provider-abstraction` |
| 107 | Live API, Browser and Service Validation | `live-service-equivalence-gate` |
| 108 | Evidence PR, Executive Report and Commercial Closure | `customer-ready-modernization-certificate` |

## Install

```bash
bash ./install.sh ~/.codex/skills
bash bash ./install.sh ~/.codex/skills --batch 106
```

Duplicate destinations are rejected unless `--overwrite` is explicitly supplied.

## Validate

```bash
bash ./validate.sh
```

## Build an execution plan

```bash
python3 scripts/build_execution_plan.py --out plan.json B108-S16
python3 scripts/compile_contracts.py --out compiled-contracts
```

## Conservative gate demonstration

```bash
python3 scripts/run_conservative_gate.py tests/fixtures/valid-candidate.json
python3 scripts/run_conservative_gate.py tests/fixtures/forged-success.json
```

The second command must be rejected.

## Trust boundary

Static PASS proves package structure, contracts, dependency DAG, installer behavior, helper tools and negative-gate behavior. It **does not** claim the ELMOS repository already implements these capabilities, that a real Sandbox Provider has been certified, or that any customer project is production ready. Those states must be earned through the implementation, tests and Evidence requirements in each Skill.
