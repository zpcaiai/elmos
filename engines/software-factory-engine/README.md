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
```

Request paths are stat-checked as regular files and size-checked before a
bounded read. Standard input is also bounded to the canonical JSON limit.

Dependency receipts emitted by successful local results are content-integrity
records, not signatures or external attestations. An external observation must
be tenant/project/correlation/policy/source-revision scoped and content
addressed. Its authorization and verification booleans remain caller assertions;
even a structurally valid observation cannot turn an unresolved external action
into local success.

The four JSON Schemas under `schemas/` cover requests, results, dependency
receipts, and external observations. Run the dependency-free test suite with:

```bash
PYTHONPATH=engines/software-factory-engine/src \
  python3 -m unittest discover -s engines/software-factory-engine/tests -v
```
