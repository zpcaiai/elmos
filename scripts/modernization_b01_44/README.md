# Batch 01-44 Modernization Runtime

Executable implementation of the Batch 01-44 Application Modernization Skill
system that ships as data under
`skills/modernization-skills-batch-01-44/`.

The packages describe sixteen Skill archetypes that repeat across all 44
batches.  This package implements those archetypes **once, as real code**, and
drives every batch through them.  A package's own `policies/*.yaml` and
`schemas/*.json` are read at runtime, so relaxing a policy file measurably
relaxes enforcement - the policy files are executable, not decorative.

## Modules

| module | responsibility |
| --- | --- |
| `canonical.py` | canonical JSON, content addressing, stable ordering, idempotency keys |
| `validation.py` | Draft 2020-12 validation at the trust boundary (jsonschema + strict built-in fallback) |
| `packages.py` | load and digest-verify all 44 packages; index skills, schemas, policies, obligations |
| `policy.py` | default-deny capabilities, tenant isolation, the Agent boundary, audit records |
| `evidence.py` | evidence records, expiry, lineage graph, dual-run reconciliation |
| `certification.py` | the conservative certification gate and the status lattice |
| `engine.py` | deterministic execution: replayable, worker-invariant, bounded |
| `workflow.py` | durable runs, leases, exactly-once events, compensation |
| `approval.py` | human approval bound to the exact request; dual control |
| `adapters.py` | provider registry, version pinning, drift detection |
| `corpus.py` | development / representative / negative / holdout corpora, budgets |
| `orchestrator.py` | one batch end to end, and the Batch 01 -> Batch 44 chain |
| `cli.py` | `packages`, `run`, `gate` commands |
| `generate_foundation.py` | generates the Batch 01-05 package content and re-issues their manifests |
| `foundation_spec.py` | typed field specifications for the 50 bespoke Batch 01-05 schemas |
| `audit_repo.py` | reports which Skill series in this repository are backed by code |
| `mutation_check.py` | deletes one enforcement at a time and requires the suite to go red |

## Guarantees, and where they are enforced

| guarantee | enforced in | proved by |
| --- | --- | --- |
| unknown input fields are refused | `policy.check_trust_boundary` | `T002`, mutation `M02` |
| a batch cannot run without its upstream certificate | `certification.require_upstream` | `T003`, `M04` |
| status is derived from evidence, never from the request | `certification.evaluate` | `T004`, `M05` |
| cross-tenant access is denied and audited | `policy.check_tenant` | `T005`, `M01` |
| agents cannot touch tests, golden data, gates or policy | `policy.check_agent_write` | `T006`, `M03` |
| breaking provider drift invalidates the pin | `adapters.assert_no_breaking_drift` | `T007`, `M07` |
| duplicate events produce one effect | `workflow.apply_event` | `T008`, `M08` |
| an expired lease reconciles instead of vanishing | `workflow.reap_expired_leases` | `T009`, `M09` |
| compensation runs newest-first and escalates on failure | `workflow.compensate` | `T010`, `M10` |
| holdout regression blocks certification | `corpus` + `certification` | `T011`, `M06` |
| expired evidence turns certificates stale | `certification.sweep_expired_evidence` | `T012`, `M11` |
| a model claim is not evidence | `evidence.NON_EXECUTION_TRUST` | `M12` |
| output does not depend on worker count | `engine.verify_worker_invariance` | `M13`, `M14` |
| unknown is never collapsed into match | `evidence.reconcile` | `M15` |
| an exhausted budget refuses, never truncates | `corpus.Budget` | `M16` |
| approval does not survive a change to the request | `approval.require` | `M17`, `M18` |
| package digests are verified against the manifest | `packages.load_package` | `M19` |
| closed schemas reject undeclared properties | `validation` | `M20` |

## Running it

```bash
make modernization-b01-44-packages   # load and digest-verify all 44 packages
make modernization-b01-44-foundation # assert Batch 01-05 content matches its generator
make modernization-b01-44-test       # the executable conformance suite
make modernization-b01-44-mutation   # prove the suite is load bearing
make modernization-b01-44-gate       # all of the above
make modernization-b01-44-run        # execute the Batch 01 -> 44 chain, print certificates
```

## What this does not claim

Executing this runtime issues `limited` certificates, because the corpora it
runs are synthetic.  `certified` additionally requires `independent-review`
evidence, which by construction cannot be produced by the same process that
produced the artefact.  Static package validation is not runtime certification,
and neither is a green suite.
