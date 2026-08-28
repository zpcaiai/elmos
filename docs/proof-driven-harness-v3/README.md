# Proof-driven harness v3 integration

This directory records the fail-closed repository integration of
`elmos-proof-driven-agentic-harness-repository-semantic-compiler@3.0.0`.

The package is untrusted input. The repository importer validates its pinned
digest, ZIP safety, CRCs, checksum manifest, exact registry/DAG, declared
structure, legacy alias-only mapping, profiles, adapters, schemas, migrations,
policies, routes, and all 46,664 ETGB case identities without executing or
extracting package code. Exactly 21 unlisted `.pyc` members are identified by
path and digest in `provenance.json` and are never materialized.

The pinned digest proves byte identity only. The ZIP contains
`LICENSE-POLICY.md`, which is untrusted policy material and is not an approved
license or repository instruction. `source-assurance.json` records that the
source has no approved license, signature, SBOM, or provenance attestation;
legal review is `NOT_RUN` and commercial distribution is not authorized. The
source policy itself declares that an organization-approved license,
dependency/license review, SBOM, allow/deny policy, and legal review are
prerequisites before commercial redistribution.

Only repository-owned Skill wrappers are installed under `.agents/skills` and
`agent-skills/runtime`. The two roots must remain byte-identical. The two
digest-verified JSON declarations under `.source-data` are inert source data,
not instructions or authority.

Run:

```sh
python3 tooling/integrate_proof_driven_harness_v3.py --check
python3 -m unittest discover -s tests/proof-driven-harness-v3 -p 'test_*.py'
```

Without a complete valid receipt at
`engines/proof-driven-harness-engine/qualification/local-qualification.json`, implementation status remains
`DECLARED_RUNTIME_UNQUALIFIED`. A valid receipt can raise it only to
`LOCAL_EXECUTED_SELF_ATTESTED`, which is self-attested local engineering evidence only.
External runtimes, providers, databases, verifiers, clusters, customer routes,
deployment, release, independent evidence, and certification remain `NOT_RUN`
or `NOT_CERTIFIED` until separately authorized and executed.
