# Batch 32 repository layout

```text
client-packs/<pack-key>/
├── pack.json
├── support-matrix.json
├── source-fingerprint/
│   ├── manifest.json
│   ├── evidence.json
│   ├── static/
│   └── runtime/
├── source-snapshots/
│   ├── routes/
│   ├── components/
│   ├── templates/
│   ├── styles/
│   ├── assets/
│   ├── screenshots/
│   ├── accessibility/
│   ├── network/
│   └── state/
├── ui-ir/
│   ├── model.json
│   ├── routes/
│   ├── views/
│   ├── components/
│   ├── state/
│   ├── forms/
│   ├── interactions/
│   └── resources/
├── target-profile/
│   ├── profile.json
│   ├── config/
│   └── dependency-locks/
├── transformations/
│   ├── routes/
│   ├── components/
│   ├── state/
│   ├── forms/
│   ├── api-client/
│   ├── auth/
│   ├── rendering/
│   └── styling/
├── compatibility/
│   └── manifest.json
├── acceptance/
│   └── acceptance-profile.json
├── baselines/
│   ├── visual/
│   ├── accessibility/
│   ├── network/
│   └── performance/
├── corpus/
│   ├── development/
│   ├── holdout/
│   └── representative-journeys/
└── certification/
    ├── gap-inventory.md
    ├── evidence.json
    ├── certification.json
    ├── gate-result.json
    └── gate-report.md
```

Generated target applications remain in repository-native application directories. The client pack stores contracts, transformations, exact profiles, and evidence rather than duplicating the full target repository.
