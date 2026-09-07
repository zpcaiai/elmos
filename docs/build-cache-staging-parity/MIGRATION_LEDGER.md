# Build-cache parity v1.2 migration ledger

## Source identity

| Field | Value |
| --- | --- |
| Package | `elmos-build-cache-staging-codex-claude-parity` |
| Version | `1.2.0` |
| Source archive | `skills/subskills/elmos-build-cache-staging-codex-claude-parity-skills-v1.2.0.zip` |
| Archive SHA-256 | `dde312b55a95cbc7af6753ec88f07833e93ffa296b782ddcf3ef1a6470b73cb7` |
| Vendored immutable root | `agent-skills/packages/elmos-build-cache-staging-codex-claude-parity/` |
| Machine-readable ledger | `installed-manifest.json` |
| Certification | `NOT_CERTIFIED` |
| External evidence | `NOT_RUN` |

The archive is input data, not an instruction channel. The importer inventories
and validates it without executing its scripts.

## Delta decision

The v1.2 package owns 42 Skills. The importer compares each Skill with the
installed v1.1 package before writing:

- 31 retained Skills have unchanged bodies; only v1.2 frontmatter/provenance
  changes. Their engine implementations are not rewritten or reclassified.
- 11 Skills are new and are installed as the parity delta.
- Installation is exact and byte-identical under `agent-skills/runtime`,
  `.agents/skills`, `.codex/skills` and `.claude/skills`.
- Under `docs/build-cache-staging-parity`, the importer owns only
  `installed-manifest.json`; runbooks and evidence documents are independent
  siblings and are neither synchronized nor deleted.
- A second importer run is idempotent. It does not synchronize or delete
  unrelated Skill directories in any root.

New Skills:

1. `elmos-provider-prompt-cache-adapters`
2. `elmos-canonical-prompt-prefix-layout`
3. `elmos-append-only-repository-context-ledger`
4. `elmos-cache-preserving-context-compaction`
5. `elmos-environment-snapshot-cache`
6. `elmos-cache-affinity-routing`
7. `elmos-multi-layer-cache-coordinator`
8. `elmos-cache-miss-diagnostics`
9. `elmos-codex-claude-parity-benchmark`
10. `elmos-cache-hit-slo-autotuning`
11. `elmos-codex-claude-cache-parity-rollout`

The canonical spelling in the package and installed manifest is authoritative;
do not rename a Skill or silently create an alias.

## Engine migration

| Layer | v1.2 delta |
| --- | --- |
| Package/config | Python package and cache configuration version 1.2.0; parity is `measured_only` / `observe` |
| Contracts | 9 new Schemas (19 total) and one parity OpenAPI control plane |
| SQLite | `0003_context_ledger.sql`, `0004_cache_parity.sql` |
| PostgreSQL | `0005_context_ledger.sql`, `0006_cache_parity.sql` |
| Prompt | `prompt_cache.py`, `prompt_tools.py` |
| Context | `context_ledger.py`, `context_compaction.py` |
| Environment | `environment_cache.py`, `environment_service.py` |
| Routing/coordination | `affinity.py`, `coordinator.py` |
| Diagnostics/runtime | `miss_diagnostics.py`, `parity_runtime.py` |
| Evidence/gate | `parity.py`, `parity_harness.py`, `slo_autotune.py` |
| Persistence | `parity_store.py` |
| Public surface | `parity_api.py`, `api.py`, `cli.py` |

## OpenAPI overlay decision

The canonical ZIP remains unchanged. The engine's
`cache-parity-control-plane.openapi.yaml` is a production overlay, not a
byte-for-byte copy of the source package OpenAPI. It intentionally:

- declares `Idempotency-Key` on mutation operations; and
- gives append-context an event payload matching the implemented request
  contract instead of referencing a completed event document.

The human-facing engine copy and packaged `_data/openapi` copy must remain
byte-identical. Schema files remain exact between the canonical package,
human-facing engine root and packaged `_data` copy.

## Rollback

Functional rollback is configuration-first:

1. keep `parity.rollout_phase: observe`;
2. keep prompt serving, environment snapshots, affinity and coordinator
   disabled;
3. disable `parity.enabled` if observation itself must stop;
4. preserve ledger, outcome and report rows for audit; do not delete or rewrite
   append-only history;
5. quarantine/revoke suspect environment artifacts and invalidate affected
   exact identities.

Database migrations are additive. Do not down-migrate by dropping v1.2 tables
in an incident; old code can leave them unused, and retained evidence stays
available for reconciliation.
