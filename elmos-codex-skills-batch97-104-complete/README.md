# ELMOS Codex Skills — Batch 97–104 Product Closure

This package contains **128 implementation-ready Codex Skills** designed to turn the broad Batch 1–96 capability estate into a smaller executable and certifiable product core.

## Batches

- **Batch 97 — Canonical Capability Graph Consolidation Pack**: 16 Skills (`B97-S01`–`B97-S16`)
- **Batch 98 — Executable Skill Contract and Registry Pack**: 16 Skills (`B98-S01`–`B98-S16`)
- **Batch 99 — Durable Runtime Kernel Pack**: 16 Skills (`B99-S01`–`B99-S16`)
- **Batch 100 — Hardened Runner Fabric Pack**: 16 Skills (`B100-S01`–`B100-S16`)
- **Batch 101 — Three Golden Route Packs**: 16 Skills (`B101-S01`–`B101-S16`)
- **Batch 102 — Semantic Equivalence Lab Pack**: 16 Skills (`B102-S01`–`B102-S16`)
- **Batch 103 — Evidence and Certification Fabric Pack**: 16 Skills (`B103-S01`–`B103-S16`)
- **Batch 104 — Real World Product Certification Pack**: 16 Skills (`B104-S01`–`B104-S16`)

## Identity policy

The package uses stable batch-local IDs (`B97-S01` … `B104-S16`) because a single authoritative global PG namespace is not available. This prevents accidental collision. A proposed allocation is non-mutating and remains unapproved unless it is backed by a separately governed namespace-authority document:

```bash
python3 scripts/remap_global_ids.py --root . --start <NEXT_PG_NUMBER> --out global-id-proposal.json
```

The proposal command never edits this package or installed Skills.

## Install

```bash
./install.sh ~/.codex/skills
./install.sh ~/.codex/skills --batch 101
```

Existing destinations are rejected by default. `--overwrite` first moves every collision into a recoverable `.elmos-backups/` transaction directory and restores it if installation fails.

## Validate

```bash
./validate.sh
```

## Trust boundary

Static validation proves package structure, exact immutable inventory, acyclic dependencies, all 128 compiled contracts, schemas, deterministic tooling and negative gate behavior. The local certification gate byte-verifies evidence files but can only return `ready_for_external_gate`; it never returns `certified`. It does not claim that the ELMOS product core, runners, route packs, external environments, customer pilots or production certification already exist. Those states must be earned in authorized target environments and independently accepted through an external trust store.
