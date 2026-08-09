
# Batch 33 repository layout

```text
cloud-packs/<pack-key>/
├── pack.json
├── support-matrix.json
├── route-matrix.json
├── source-fingerprint/
│   └── fingerprint.json
├── runtime-architecture/
│   └── contract.json
├── iac-ir/
│   └── model.json
├── target-profile/
│   └── profile.json
├── validation/
│   └── validation-profile.json
├── transformations/
├── mappings/
├── adapters/
├── container/
├── orchestration/
├── pipelines/
├── managed-services/
├── gateway/
├── observability/
├── security/
├── policies/
├── state/
├── rollout/
├── cost/
├── drift/
├── corpus/
│   ├── development/
│   ├── negative/
│   ├── holdout/
│   └── representative-workloads/
└── certification/
    ├── gap-inventory.md
    ├── evidence.json
    ├── certification.json
    ├── gate-result.json
    └── gate-report.md
```

Large plans, state snapshots, logs, SBOMs, images, and runtime observations should be content-addressed artifacts. Metadata and digests belong in the pack.
