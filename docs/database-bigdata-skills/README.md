# Database and Big Data Skills Integration

This directory records the repository integration of `elmos-database-bigdata-skills` version `1.0.0`.

- Trusted source archive: `skills/subskills/elmos-database-bigdata-skills-v1.0.0.zip` (`sha256:e5baae82593d84f4784900de7be93a7fa0b582dc081ac97bc35a4d6e12865e53`)
- Immutable extracted source: `skills/elmos-database-bigdata-skills-v1.0.0/`
- Installed Skills: 46 exact names under both `agent-skills/runtime/` and `.agents/skills/`
- Source profiles / schemas / technologies: 10 / 7 / 29
- Skill implementation state: `DECLARED`
- Bounded reference-tool state: `NOT_RUN`
- Provider/runtime and external evidence: `NOT_RUN`
- Production certification: `NOT_CERTIFIED`
- Source license / signature / SBOM / provenance attestation: `ABSENT`

The importer does not execute the source package installer, validator, or manifest builder. It independently pins the ZIP, compares every extracted byte, verifies exact checksum coverage, validates the 46-Skill DAG and 554 stable task IDs, checks profiles/catalogs/Schemas/examples, and generates Codex-compatible interfaces with provenance.

The source package includes three deterministic reference tools, but no per-Skill handlers, provider adapters, infrastructure templates, or generated-project assets. Local qualification of those three helpers against the three synthetic examples is self-attested engineering evidence only; it does not implement a whole Skill or validate any database, connector, engine, cloud, deployment, migration, benchmark, recovery path, or customer workload.

Run the repository-owned checks with:

```sh
make database-bigdata-skills
```
