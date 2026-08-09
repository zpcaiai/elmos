# Batch 30 Repository Layout

```text
framework-packs/<pack-key>/
├── pack.json
├── support-matrix.json
├── version-matrix.json
├── source-fingerprint/
│   ├── manifest.json
│   └── evidence.json
├── contracts/
│   ├── web/
│   ├── di/
│   ├── configuration/
│   ├── validation/
│   ├── security/
│   ├── persistence/
│   ├── transaction/
│   ├── messaging/
│   ├── cache/
│   ├── scheduler/
│   └── lifecycle/
├── target-profile/
│   ├── profile.json
│   ├── dependency-locks/
│   ├── scaffold/
│   └── contract-tests/
├── recipes/
├── adapters/
├── compatibility/
│   └── manifest.json
├── coexistence/
├── corpus/
│   ├── development/
│   │   ├── smoke/
│   │   ├── contracts/
│   │   └── negative/
│   ├── holdout/
│   └── real-repository/
└── certification/
    ├── evidence.json
    └── certification.json
```

Shared code belongs in:

```text
packages/framework-contracts/
engines/framework-contract-core/
engines/<source>-framework-adapter/
engines/<target>-framework-target/
recipes/frameworks/
tests/framework-contracts/
```

Do not put source-framework APIs in core UIR. Do not let one pack write another pack's evidence or customer-private corpus.
