# Batch 29 Repository Layout

The skill pack expects or creates this route overlay. Adapt engine paths to the existing repository, but keep route artifacts and evidence separate by direction.

```text
engines/
  java-engine/
  csharp-engine/
  python-engine/
  typescript-engine/

contracts/
  psp/
  uir/
  engine-protocol/
  source-map/

routes/
  java-to-csharp/
    route.json
    support-matrix.json
    lowering/
    mappings/
    compat-runtime/
      manifest.json
    corpus/
      development/
      holdout/
      real-repository/
    certification/
      evidence.json
      economics.json
      certification.json

runtimes/
  compat/

tests/
  contracts/
  routes/
```

If the existing repository uses different paths, create a short ADR and update `route.json` path fields. Do not duplicate working engines merely to match this layout.
