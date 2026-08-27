# ETGB SOTA Skills repository integration

The archive at `skills/subskills/elmos-etgb-sota-skills-package-v1.0.0.zip` is
an immutable, untrusted source specification. The repository-owned runtime is
`engines/etgb-engine/src/elmos_etgb`; it provides the executable lifecycle,
safe local fixture adapters, independent oracles, durable state, evidence, and
fail-closed gate calculations.

The ten installed interfaces under `agent-skills/runtime/etgb-*` and
`.agents/skills/etgb-*` preserve exact source names and provenance while
keeping source-package instructions inert. `installed-manifest.json` records
the archive digest and current evidence boundary.

Local smoke results are engineering evidence only. Real repository translation,
Spring/target runtime, multi-database, provider, security sandbox, independent
verification, and production certification remain `NOT_RUN`/`NOT_CERTIFIED`
until their named environments and evidence exist.
