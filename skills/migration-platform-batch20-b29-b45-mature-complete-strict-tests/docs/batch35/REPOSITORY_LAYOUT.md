# Batch 35 Repository Layout

```text
verification-packs/<pack-key>/
├── pack.json
├── support-matrix.json
├── validation-profile.json
├── oracle-registry.json
├── properties/
├── metamorphic/
├── mutation/
├── fuzz/
├── symbolic/
├── models/
├── state-machines/
├── contracts/
├── invariants/
├── security/
├── concurrency/
├── queries/
├── numeric/
├── solver/
├── coverage/
├── counterexamples/
├── assurance/
├── corpus/{development,negative,holdout,representative-workloads}/
└── certification/
```

Technique-specific source code belongs in existing engine/test modules; the pack stores exact specifications, manifests, results, and evidence rather than copied implementations.
