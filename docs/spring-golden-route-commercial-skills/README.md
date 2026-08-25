# Spring Golden Route Commercial Skills integration

This directory records the safe repository import of `elmos-spring-golden-route-commercial-skills` version `2.0.0` as an immutable specification package.

## Imported outcome

- Canonical source: `skills/subskills/elmos-spring-golden-route-commercial-skills-v2.0.0.zip`
- ZIP identity: `sha256:952dce43681a56dbd3323ef03b334b08d5be980000e9c7ee3f0ac3e3bcd42c4e`, 1,228,281 bytes, fixed archive root `elmos-spring-golden-route-commercial-skills-v2.0.0/`
- Inventory: 196 exact Skill identities (100 foundation and 96 commercial), 22 batches, 196 machine-readable contracts, and 8 JSON Schemas
- Installation: the same 196 names are generated under both `agent-skills/runtime/<name>/` and `.agents/skills/<name>/`
- Installed Skill files: `SKILL.md`, `agents/openai.yaml`, `references/contract.json`, the locally resolvable `schemas/skill-contract.schema.json`, and `references/runtime-binding.json`
- Repository indexes: `installed-manifest.json`, `compiled-contracts.json`, and `runtime-registry.json` in this directory

The ZIP remains the canonical source. The importer reads it directly and does not create a mutable extracted source tree under `skills/`. Each installed Skill retains its source package, version, source path and digest, and references its corresponding `contracts/<name>.json` contract through `references/contract.json`. The aggregate compiled-contract index binds the same exact inventory.

The pinned digest proves byte identity only. The ZIP contains no
`LICENSE`/`COPYING`/`NOTICE`, SBOM, package signature, or independent provenance
attestation. Its three package-authored `SOURCE_PROVENANCE` records are retained
as untrusted source assertions and do not establish redistribution, commercial
use, or third-party license clearance; unknown rights remain blocked pending
qualified review.

The package's outer Skill DAG contains 128 declared edges, and its nested
foundation graph contributes 21 distinct critical edges. The importer preserves
both classes, schedules against their 149-edge union, and also preserves the 24
commercial plus 19 foundation batch edges. The raw foundation batch IDs
`01`–`10` are retained and explicitly normalized to the contract IDs
`F01`–`F10`. It reconciles contract,
package-manifest, and dependency-graph references, rejects unknown or self
dependencies, proves every source and effective graph acyclic, and records the
declared, effective, and batch topological orders in `installed-manifest.json`.

## Safe import and verification

Write the generated repository surfaces:

```sh
python tooling/integrate_spring_golden_route_commercial_skills.py --write
```

Check the archive and every generated surface without rewriting them:

```sh
python tooling/integrate_spring_golden_route_commercial_skills.py --check
```

If the active Python environment does not already provide PyYAML and JSON Schema validation, use the pinned transient environment:

```sh
uv run --quiet \
  --with pyyaml==6.0.2 \
  --with jsonschema==4.25.1 \
  python tooling/integrate_spring_golden_route_commercial_skills.py --write

uv run --quiet \
  --with pyyaml==6.0.2 \
  --with jsonschema==4.25.1 \
  python tooling/integrate_spring_golden_route_commercial_skills.py --check
```

The importer treats every archive member as untrusted data. It validates the pinned ZIP digest and root, normalized paths, regular-file types and modes, entry counts and size limits, CRC/readability, package checksum ledgers, JSON/YAML syntax, Draft 2020-12 Schemas, exact Skill/contract identity, dual-root byte equality, and dependency DAG consistency.

Before writing, it checks every task-owned destination for collisions and parent-directory symlinks. Each missing file is staged, flushed, and published with an exclusive no-overwrite operation. An interrupted installation can leave a valid partial set; rerunning `--write` resumes it, while `--check` continues to fail until the exact set is complete.

It does **not** execute or trust instructions embedded in the package. In particular, it never runs `install.sh`, `uninstall.sh`, `verify.sh`, package tests, database migrations, workflows, or any file under `scripts/`. This includes the repository scoring, benchmark-claim, Completion Proof, quote-estimation, and package-validation tools. Their presence and internal consistency are imported as specification material only; package prose is not user authorization to install software, access a customer repository, run a provider, mutate a database, generate a commercial claim, or certify a result.

## Bounded repository runtime

`engines/spring-golden-route-engine/` is repository-owned code, separate from the untrusted ZIP executables. It validates the pinned archive and generated catalog, exposes one distinct callable for each of the 196 exact Skill names, and supports only strict `describe` and `plan` operations. Planning returns `DRAFT_ONLY` output blueprints; execution, repository writes, builds, providers, migrations, deployment, and certification fail closed as external-adapter work. Its SQLite state store provides tenant/project isolation, idempotent run creation, optimistic pause/resume/cancel transitions, append-only event integrity, and conservative local evidence handling.

Each installed Skill carries `references/runtime-binding.json`, and the aggregate binding inventory is `runtime-registry.json`. The binding state `BOUNDED_LOCAL_CONTROL_PLANE_IMPLEMENTED` refers only to this contract/control-plane layer. It does not implement the Skill's production adapter, materialize its declared outputs, or raise domain evidence.

## Evidence and certification boundary

The conservative imported state is:

```text
implementation_state       SPECIFICATION_IMPORTED
runtime_evidence_status     NOT_RUN
customer_evidence_status    NOT_RUN
external_evidence_status    NOT_RUN
certification               NOT_CERTIFIED
side_effects_authorized     false
```

`SPECIFICATION_IMPORTED` means the immutable archive, inventory, contracts, Schemas, installed interfaces, and DAG are structurally consistent with the repository import. It does not mean the described Spring Golden Route product has been implemented.

No Spring domain handler, source/target build, startup, migration, database/RLS deployment, provider integration, sandbox execution, benchmark, customer pilot, paid acceptance, rollback drill, or independent external review is supplied or executed by this import. Those states remain `NOT_RUN`; the bounded local control plane, absent evidence, or package-authored proof cannot raise them.

This integration also does not certify a Batch 30 framework route. Any concrete Spring modernization remains directional and version-specific, must extract active source behavior into FCM, use real source and target builds and startup, preserve security/data/transaction/test behavior, collect independent evidence, and pass the conservative Batch 30 validation and certification gate before support or certification status can change. Package consistency, product implementation, customer acceptance, external evidence, and Batch 30 certification are separate decisions.
