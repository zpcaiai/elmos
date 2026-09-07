# Storage and Workspace Layout Contract

## Local cache

```text
.elmos/cache/
├── cas/
│   └── sha256/
│       └── ab/
│           └── cd/
│               └── <digest>.blob
├── metadata/
│   └── index.sqlite
├── uploads/
├── quarantine/
├── locks/
└── metrics/
```

Canonical CAS paths are internal implementation details and must not leak into public APIs. Public references use `cas://sha256:<hex>` or a normalized equivalent.

## Workspace

```text
.elmos/workspaces/<tenant>/<project>/<run_id>/
├── control/
├── source/
├── overlay/
├── scratch/
├── generated/pending/
├── generated/sealed/
├── artifacts/
├── checkpoints/
├── quarantine/
├── publish/
└── logs/
```

## Temporary filename

Use a same-directory or same-filesystem name such as:

```text
.<basename>.elmos-tmp-<node-id>-<attempt>-<nonce>
```

Never derive trust from the temporary name. The staged-file record and lease epoch are authoritative.

## Publication

```text
publish/<run_id>/<tree-digest>/
publish/<run_id>/current -> <tree-digest>
```

A portable pointer file may replace a symlink on platforms where atomic symlink replacement is not available.
