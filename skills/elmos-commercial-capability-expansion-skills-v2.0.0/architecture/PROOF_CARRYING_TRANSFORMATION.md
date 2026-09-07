# Proof-Carrying Transformation Bundle

Every release-grade transformation should be able to emit:

```text
bundle/
  source-input.json
  transform-plan.json
  edit-ledger.json
  environment.json
  build-results.json
  test-results/
  differential-results/
  fuzz-results/
  static-analysis/
  formal-results/
  performance-results/
  sbom/
  provenance/
  attestations/
  signatures/
  certification.json
  rollback-map.json
```

The bundle proves *what changed, why, under which environment, with which tools/models/skills, and which evidence justified release*. It is not a claim of mathematical proof unless formal proof artifacts are actually present.
