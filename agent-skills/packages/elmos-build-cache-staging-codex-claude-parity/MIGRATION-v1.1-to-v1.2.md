# Migration Guide: v1.1.0 to v1.2.0

## 1. Preserve existing truth

Do not delete v1.1.0 CAS, Action Cache, run journals, checkpoints, staged files, or published-tree evidence. Freeze a backup and record their schema/config digests before migration.

## 2. Upgrade Skills

```bash
./install.sh --all --overwrite
```

The installer replaces Skill directories, not production ELMOS data.

## 3. Add v1.2.0 metadata

Apply the production-adapted equivalent of:

```text
references/sql/postgres-parity-migration.sql
```

Add tenant row-level security, partitioning, retention, and migration framework metadata required by the ELMOS repository.

## 4. Introduce versioned namespaces

Create new namespaces for:

- provider/model/effort/tool/prompt compatibility groups;
- repository context ledger streams;
- environment snapshots;
- parity reports and policy certificates.

Do not rewrite old keys in place. Use dual-read or compatibility adapters where exact semantics are proven.

## 5. Observation-only phase

Enable only:

- provider normalized usage observations;
- Prompt Prefix Manifests and first-difference diagnostics;
- context ledger shadow events;
- environment/worker cache inventory;
- unified cache outcome reasons and accounting.

No production execution decision should change yet.

## 6. Canonical prompt and context ledger

Canary canonical prompt layout by provider/model/tool profile. Validate answer/tool behavior, cached-token reuse, unexpected misses, and policy correctness. Then enable append-only repository context projections and stale/reread handling.

## 7. Environment and affinity

Build environment snapshots under a new trust namespace. Run secret, corruption, clean-build equivalence, and revocation tests. Enable affinity as a soft scheduler preference with bounded-load/fairness escape.

## 8. Coordinator and compaction

Enable exact-result-before-model planning, partial-hit DAG execution, singleflight, restore-versus-recompute, unified attribution, and planned context compaction. Keep independent kill switches.

## 9. Certify

Run the full parity corpus and require every mandatory gate, including zero false hits. Bind the certificate to code, configuration, provider profiles, corpus, platform, and date.

## 10. Rollout and rollback

Proceed through observe, shadow, internal, canary, 5%, 25%, 50%, and 100%. Any false hit, cross-tenant hit, corrupt execution, under-validated publication, mandatory-SLO breach, OOD, or unknown-outcome budget breach returns to the frozen v1.1-compatible safe baseline.
