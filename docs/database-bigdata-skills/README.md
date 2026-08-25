# Database and Big Data Skills Integration

This directory records the repository integration of `elmos-database-bigdata-skills` version `1.0.0`.

- Trusted source archive: `skills/subskills/elmos-database-bigdata-skills-v1.0.0.zip` (`sha256:e5baae82593d84f4784900de7be93a7fa0b582dc081ac97bc35a4d6e12865e53`)
- Immutable extracted source: `skills/elmos-database-bigdata-skills-v1.0.0/`
- Installed Skills: 46 exact names under both `agent-skills/runtime/` and `.agents/skills/`
- Repository plan-skeleton bindings: 46 exact handlers under `engines/database-bigdata-engine/`
- Source profiles / schemas / technologies: 10 / 7 / 29
- Skill implementation state: `DECLARED`
- Bounded reference-tool state: `NOT_RUN`
- Provider/runtime and external evidence: `NOT_RUN`
- Production certification: `NOT_CERTIFIED`
- Source license / signature / SBOM / provenance attestation: `ABSENT`

The importer does not execute the source package installer, validator, or manifest builder. It independently pins the ZIP, compares every extracted byte, verifies exact checksum coverage, validates the 46-Skill DAG and 554 stable task IDs, checks profiles/catalogs/Schemas/examples, and generates Codex-compatible interfaces with provenance.

The source package includes three deterministic reference tools, but no per-Skill handlers, provider adapters, infrastructure templates, or generated-project assets. The repository-owned bounded runtime emits typed plan skeletons containing identities, declared outputs, and explicit evidence gaps for every exact Skill and all 554 task IDs. It does not execute any source task or generate the declared artifacts. Whole-Skill implementation therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and certification remains `NOT_CERTIFIED`.

The authoritative repository CLI is `python3 -I -S -B engines/database-bigdata-engine/launcher.py`. The launcher refuses any weaker interpreter flags before importing non-builtin modules; isolated mode removes the script/current directory, ignores environment path injection, disables site customization, and suppresses bytecode writes. That package-external launcher rejects bytecode caches, checks every engine source file against the repository-owned manifest, and loads the package only from those verified source bytes. Each process retains that immutable byte snapshot and rejects repository drift before and after dispatch. Direct package imports are trusted-code library use, report `DIRECT_IMPORT_TRUSTED_CODE_ONLY`, and do not claim the launcher's pre-import boundary. The reviewed launcher and checked-in manifest are repository trust roots; digest checks prove local byte identity only and are not a signature, provenance attestation, or independent verification. Accepted tenant/project/actor/idempotency identifiers are caller-asserted and unverified, with digest binding only and no replay store.

Local qualification of the three source helpers, if separately sandboxed in the future, would be self-attested engineering evidence only; it would not validate any database, connector, engine, cloud, deployment, migration, benchmark, recovery path, or customer workload.

Run the repository-owned checks with:

```sh
make database-bigdata-skills
```
