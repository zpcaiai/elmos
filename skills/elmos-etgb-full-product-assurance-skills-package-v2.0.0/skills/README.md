# ETGB Skills

This directory contains **24 composable Skills**. `skills/manifest.yaml` is the machine-readable registry and `etgb-orchestrator` is the entry Skill.

## Layers

- **Domain validation:** Spring modernization, repository translation, project generation, SQL/routines.
- **Assurance:** differential Oracles, test authoring, metamorphic/fuzz/mutation, statistical validity.
- **Runtime control:** production Harness, Environment authority, checkpoint/recovery, budget/ETA, multi-tenant scheduling.
- **Integrity and governance:** immutable candidate, hidden tests, corpus, supply chain, evidence provenance.
- **Operations and certification:** risk selection, observability/triage, incident learning, scale certification and release gates.

Run:

```bash
etgb skills-audit
```

A Skill dependency is an execution prerequisite, not permission inheritance. Each invoked Skill still operates under the exact authority of its Environment/Attachment.
