# ELMOS software-factory engine

This is a dependency-free, bounded local runtime for the eight `P00`-`P07`
commercial software-factory packages. It loads an explicit checked-in registry,
validates all 102 repository bindings against the machine-readable
`capability_registry.json` and all 50 stable APIs against
`public_method_registry.json`, enforces package dependency receipts and scope
envelopes, then dispatches each exact Skill to its declared local or adapter
boundary. The registry records a child-specific action, mode, and required-input
contract; a child cannot switch itself to another package action.

Each public method has its own required-input contract. `domain_errors` are the
source-declared stable domain codes for that API. They are not an exhaustive list
of runtime failures: `platform_errors` separately records policy, approval,
dependency, adapter, request, and envelope failures that callers must also handle
fail closed.

The runtime deliberately separates local engineering results from external
execution. Local handlers can return `EXECUTED`; missing policy, dependency, or
evidence returns `BLOCKED`; provider/compiler/device/training and other external
actions always return `REQUIRES_ADAPTER` in this engine. Supplied observations
are scope- and digest-validated caller integrity records, but they can never
substitute for adapter execution, evidence-byte resolution, signature/trust-root
verification, or authorization verification. Handler faults return `FAILED`.
Every result has deterministic `warnings`, `retry`, `evidence`, and typed error
fields. `request_digest` binds the complete canonical request—including payload,
policy, dependency receipts, and observations—into both the result digest and
any emitted dependency receipt without copying the request into the envelope.
External evidence remains `NOT_RUN`, certification remains
`NOT_CERTIFIED`, and no local result is certification.

## Local qualification campaigns

The repository-owned evidence runner now implements three deterministic,
replayable profiles without accepting commands, plugins, credentials, network
access, providers, or production writes:

- `local-holdout` runs an immutable local case corpus against exact Skill
  bindings and rejects overlap with declared development-case digests. It may
  report `LOCAL_HOLDOUT_EXECUTED_SELF_ATTESTED`; independent holdout remains
  `NOT_RUN`.
- `provider-contract-simulation` validates request/response digests, exact
  adapter fields, provider error mappings, and asserts that the real runtime
  remains `REQUIRES_ADAPTER`. Real provider execution remains `NOT_RUN`.
- `production-like-rehearsal` evaluates synthetic Canary outcomes and requires
  byte-equivalent rollback to the initial state with zero population, zero
  network/provider calls, and zero production writes. Production execution
  remains `NOT_RUN`.

Every campaign must provide content references for its target, environment, and
immutable input corpus under an explicitly approved evidence root. The runner
opens those files without following the final symlink, checks byte counts and
SHA-256, verifies every target-manifest file beneath that root, enforces exact
tenant/project/campaign/policy/source scope, and then issues a receipt binding
the complete manifest, target artifact, environment, corpus, every case result,
runtime/registry identities where applicable, and a deterministic replay
contract. Campaign execution additionally requires the target manifest to bind
the exact 15 Python modules and three registry resources used by this package.
It verifies the loaded dispatcher, engine, handler, and registry-loader source
identities before and after every campaign, and includes that runtime binding in
the execution digest. Environment and corpus manifests must carry the same
tenant/project/policy/source scope and conservative local-only state.

The external
evidence intake path performs bounded no-follow content reads, exact scope and
digest checks, role separation, revocation, organization policy, and explicit
receipt allowlisting. Its maximum state is
`EXTERNAL_RECEIPT_POLICY_ADMITTED`: without an external signature trust root it
is still unverified and cannot change any external evidence state.

The `external-preflight` path validates production-shaped adapter, holdout,
representative-workload, HSM reference, Canary, rollback, and authorization
bindings. It never executes them and can reach only
`STRUCTURALLY_READY_FOR_EXTERNAL_TRUST_VERIFICATION` locally.

## Archive-script safety

The two supplied Python scripts remain untrusted source material. The importer
materializes them as `_neutralized-executable-data/**/*.source-data` with mode
`0644`, while preserving their original `0755` mode and SHA-256 in the logical
source mapping. `archive-inspect` is a repository-owned bounded reimplementation
of their useful readiness, Schema/config/example, frontmatter, Markdown-fence,
and manifest-count checks. It never imports, compiles, or executes either source
script. The supplied logical union lacks the root files required by the original
validator, so that incompatibility remains explicit rather than being patched
over or reported as a source pass.

Requests use this shape:

```json
{
  "contract_version": "1.0",
  "tenant_id": "tenant-a",
  "project_id": "project-a",
  "correlation_id": "run-a",
  "idempotency_key": null,
  "policy_revision": "policy-v1",
  "source_revision": "git-commit-or-contract-revision",
  "policy": {
    "allowed_skills": ["elmos-software-factory-master"],
    "allowed_actions": ["compile-workflow"]
  },
  "dependencies": [],
  "observations": [],
  "payload": {"nodes": [], "action": "compile-workflow"}
}
```

The CLI reads a request from a file or standard input:

```bash
python -m elmos_software_factory execute \
  --skill elmos-software-factory-master --request request.json
python -m elmos_software_factory registry
python -m elmos_software_factory methods
python -m elmos_software_factory digest --request request.json
python -m elmos_software_factory archive-inspect --source-root canonical-source
python -m elmos_software_factory campaign-run \
  --manifest campaign.json --evidence-root .
python -m elmos_software_factory campaign-replay \
  --manifest campaign.json --receipt receipt.json --evidence-root .
python -m elmos_software_factory evidence-ingest \
  --receipt receipt.json --policy policy.json --evidence-root evidence
python -m elmos_software_factory external-preflight --config preflight.json
```

Request paths are opened once with `O_NOFOLLOW` and `O_NONBLOCK`, checked from
the open descriptor as regular files, and size-checked before a bounded read.
Platforms missing either safety flag fail closed. Standard input is also
bounded to the canonical JSON limit.

Dependency receipts emitted by successful local results are content-integrity
records, not signatures or external attestations. An external observation must
be tenant/project/correlation/policy/source-revision scoped and content
addressed. Its authorization and verification booleans remain caller assertions;
even a structurally valid observation cannot turn an unresolved external action
into local success.

The JSON Schemas under `schemas/` cover requests/results, dependency and caller
observations, campaign manifests/receipts, safe archive inspection, external
receipt quarantine, intake policy/decision, and structural preflight. Run the
dependency-free test suite with:

```bash
PYTHONPATH=engines/software-factory-engine/src \
  python3 -m unittest discover -s engines/software-factory-engine/tests -v

/opt/homebrew/bin/uv run --quiet --with jsonschema==4.25.1 \
  env PYTHONPATH=engines/software-factory-engine/src \
  python -m unittest discover -s engines/software-factory-engine/tests -v
```
