# Elmos 7+1 commercial Skills integration

This integration treats the eight archives in
`skills/subskills/archives/` as immutable, untrusted source data. The importer
validates and merges them without importing or executing archive code.
Archive Skill descriptions and bodies remain inert canonical data; installed
`SKILL.md` files contain repository-authored instructions only. All 101 source
`SKILL.md` files and the shared archive `AGENTS.md` are materialized under
neutralized data filenames with an explicit digest-bound
logical-to-materialized mapping.

## Implemented scope

- Eight package routers (`P00` through `P07`) and 93 child Skills are pinned to
  their source archive and member digests.
- A repository-owned root router provides one entry point across the eight
  packages.
- All 102 Skills have deterministic interfaces in `.agents/skills/` and
  `agent-skills/runtime/`.
- Two pre-existing Project Intelligence Skills keep their original names and
  bytes. Incoming source identities `elmos-incremental-analysis-cache` and
  `elmos-release-certification` install only as
  `elmos-7plus1-incremental-analysis-cache` and
  `elmos-7plus1-release-certification`; runtime dispatch still uses the exact
  source identities.
- `engines/software-factory-engine/` implements a bounded, typed local runtime
  for workflow compilation, permission decisions, repository intelligence,
  transformation planning, task scheduling, evidence gating, model routing,
  and knowledge promotion.
- Package, Skill, request, result, and evidence identities are content
  addressed and tenant/project scoped.
- The importer independently validates the 102-Skill binding/capability
  registries and exact 50-method public API registry, then binds all three plus
  required runtime modules by byte digest without importing or executing
  runtime Python.

## Evidence boundary

The source package describes a commercial product blueprint. Importing it does
not establish that every described provider, compiler, device, training,
deployment, or production capability has run. Local deterministic handlers may
produce `EXECUTED`; an operation requiring an unavailable external integration
produces `REQUIRES_ADAPTER`; missing policy, dependency, or evidence produces
`BLOCKED`.

Repository validation is engineering evidence only. The installed manifest
therefore keeps external evidence `NOT_RUN` and certification
`NOT_CERTIFIED`. Neither a blueprint readiness score nor a local handler result
may be promoted to external or production evidence.

## Validation

```bash
python3 tooling/integrate_elmos_7plus1_skills.py --check
python3 -m unittest discover \
  -s tests/elmos-7plus1-commercial-skills \
  -p 'test_*.py'
```
