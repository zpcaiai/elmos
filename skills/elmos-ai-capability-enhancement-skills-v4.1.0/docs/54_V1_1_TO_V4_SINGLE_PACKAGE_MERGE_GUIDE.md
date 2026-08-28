# v1.1.0 → v4.0.0 Single-Package Merge Guide

## Objective

Replace the earlier AI-Native Project Factory v1.1.0 installation with one consolidated v4.0.0 package without introducing a new top-level route owner or a second source of semantic/completion truth.

## Architectural invariants

- The existing K1–K8 kernels remain authoritative for intent, repository facts, semantics, reasoning, transformation, verification, durable execution and certification.
- All 362 component Skills are non-routable and use `route_owner: domain-pack.project-generation`.
- All 275 Adapters are replaceable implementation boundaries; an Adapter cannot certify its own output.
- Exact `RevisionSet`, environment authority, tool/model/database versions, evidence freshness and independent K8 decisions remain mandatory.
- `UNKNOWN`, `UNSUPPORTED`, stale evidence and unresolved critical side effects block production certification.

## What is merged

The v4 package contains the complete v1.1 AI project-generation baseline plus:

1. Polyglot language/framework semantic routes and compiler/toolchain conformance.
2. Relational SQL, routine, ORM, NoSQL, search, graph, vector, stream and lakehouse semantic fabrics.
3. API, OpenAPI/Arazzo, AsyncAPI/CloudEvents, MCP, A2A, ACP, webhook, saga and distributed-consistency contracts.
4. Model serving, inference engines, routing, realtime, multimodal, edge, quantization and model-artifact provenance.
5. Knowledge graph, GraphRAG, citation, temporal knowledge, retrieval and memory lifecycle controls.
6. Full-spectrum automated QA, record/replay, mutation/fuzz/chaos, statistical gates and evidence assembly.
7. Formal-method routing, model checking, SMT/symbolic execution, proof-assistant bridges and TCB governance.
8. Zero-trust identity, confidential runtime, WASI capability sandboxing, supply-chain and certificate-bound admission.
9. Platform engineering, GitOps, multi-region SRE, FinOps, sustainability, SaaS productization and operator tooling.
10. Continuous governance, post-market monitoring, safe self-improvement and independent E0–E5/P05 certification.

## Recommended migration

```bash
# 1. Validate the extracted package.
./validate.sh

# 2. Inspect the exact install plan.
./install.sh --repo /path/to/elmos --host both --profile p0 --dry-run

# 3. Back up/commit the target repository.
git -C /path/to/elmos status

# 4. Install with backed-up replacement where an older package is present.
./install.sh --repo /path/to/elmos --host both --profile p0 --force

# 5. Run Elmos registry and dependency checks in the target repository.
# 6. Implement B00–B05 first; do not enable all native routes simultaneously.
```

The installer moves conflicting destinations into `.elmos/install-backups/<timestamp>/` before replacement. The uninstaller removes only files whose hashes still match the receipt, preserves locally modified files and restores backed-up content when the destination is free.

## Delivery sequence

1. **B00–B05:** registry, contracts, AI-SIR/Repository-SIR/DB-SIR, authority and evidence foundations.
2. **First vertical route:** Requirement → LangGraph Python + Spring AI Java + PostgreSQL, with normalized-trace differential verification.
3. **First database route:** Oracle or SQL Server → PostgreSQL, including routine, data, CDC and rollback evidence.
4. **QA mesh:** Proof Obligation → Validation DAG → authoritative oracle → counterexample repair → sealed evidence.
5. **Certification lab:** clean-room build, native conformance, customer holdout, WORM/Merkle sealing, independent K8 decision.
6. **Expansion:** NoSQL/vector/lakehouse, model serving, protocol interoperability, multi-region and regulated deployment.

## Upgrade and rollback rules

- Install a new package only against a clean Git state or an approved change window.
- Preserve old package archives, receipts and controlled-file checksums.
- Do not reuse production evidence merely because a Skill name is unchanged.
- Recompute affected Proof Obligations whenever a Skill, Adapter, policy, model, database, protocol or toolchain version changes.
- Rollback restores package files only; production data/schema/model rollback must follow the relevant Golden Route and Side-Effect Ledger.

## Completion boundary

Successful package installation and package validation establish only the implementation contract. They do not prove that Elmos has executed native compiler/database/framework/cloud runs or earned E5/P05/customer certification.
