
# Batch 31 Repository Layout

```text
database-packs/<pack-key>/
├── pack.json
├── support-matrix.json
├── route-matrix.json
├── source-fingerprint/
│   ├── manifest.json
│   ├── evidence.json
│   ├── static/
│   └── runtime/
├── source-snapshots/
│   ├── ddl/
│   ├── catalogs/
│   ├── stats/
│   └── plans/
├── canonical-ir/
│   ├── model.json
│   ├── schema/
│   ├── queries/
│   ├── routines/
│   └── pipelines/
├── target-profile/
│   ├── profile.json
│   ├── ddl/
│   ├── config/
│   └── dependency-locks/
├── transformations/
│   ├── schema/
│   ├── query/
│   ├── routine/
│   └── pipeline/
├── compatibility/
│   └── manifest.json
├── migration/
│   ├── data-migration-plan.json
│   ├── schema/
│   ├── backfill/
│   ├── cdc/
│   ├── reconciliation/
│   └── cutover/
├── corpus/
│   ├── development/
│   │   ├── schema/
│   │   ├── queries/
│   │   ├── routines/
│   │   ├── data/
│   │   ├── pipelines/
│   │   └── negative/
│   ├── holdout/
│   └── representative-workloads/
└── certification/
    ├── gap-inventory.md
    ├── evidence.json
    ├── certification.json
    ├── gate-result.json
    └── gate-report.md
```

Reusable source/target adapters belong under engine or platform modules, not inside one customer pack. Customer-specific DDL, data, SQL, mappings, and evidence remain tenant-private.
