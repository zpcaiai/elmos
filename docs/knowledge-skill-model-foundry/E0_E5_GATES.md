# Quality & Certification Gates (E0–E5)

The Foundry enforces progressive quality gates with fail-closed verifications:

| Gate Level | Name | Requirements | Verification Technique |
|:---|:---|:---|:---|
| **E0** | Syntactic Validity | Valid JSON schemas, YAML structures, strict type conformity | Parser & JSON Schema Validators |
| **E1** | Unit Evaluation | Accuracy $\ge 0.85$, zero schema violation | Hermetic Unit Test Suites |
| **E2** | Integration Gate | Pass rate $\ge 0.95$, dependency closed | Multi-module Integration Harness |
| **E3** | Shadow & Canary | Production error rate $\le 0.01$, latency SLA met | Shadow Traffic & Canary Metrics |
| **E4** | Production Certified | Zero regressions, 100% test adequacy, immutable Merkle seal | Comprehensive Regression & Signoff |
| **E5** | Formal Proof | Mathematical invariant satisfaction, Lean/SMT proof | Formal Verification & Solver Check |
