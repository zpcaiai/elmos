# R10 / D6 — independent client-repository verification: what it actually requires

> Written 2026-08-18 by Claude Code, from reading the gate and schema, not from
> assumption. Status of R10 is **0/90 and structurally blocked** — not merely
> neglected. Read this before planning any work against D6 or D7.

## 1. The only permitted gate

`make b29-repository-gate B29_REPOSITORY_CAMPAIGN=<campaign.json>`
→ `scripts/batch29/run_repository_gate.py`
→ validated against `schemas/batch29/repository-capability-campaign.schema.json`

The Makefile refuses to run without an explicit campaign file that exists; there
is no default and no dry-run.

## 2. The gate can never certify. By construction.

`run_repository_gate.py` hardcodes its own ceiling:

```python
"decision": "READY_FOR_EXTERNAL_GATE" if ready else "LIMITED",
"maximum_local_decision": "READY_FOR_EXTERNAL_GATE",
"certification_decision": "NOT_CERTIFIED",
"external_verification_status": "NOT_RUN",
```

and it *fails the campaign* if the input claims otherwise:

```python
if root.get("external_verification_status") != "NOT_RUN":
    context.fail("campaign.external_verification_status must remain NOT_RUN at this local gate")
if root.get("certification_status") != "NOT_CERTIFIED":
    context.fail("campaign.certification_status must remain NOT_CERTIFIED")
```

**Consequence: D7 / R11 cannot be reached by any local action — by anyone.**
Best achievable locally is `READY_FOR_EXTERNAL_GATE`. Certification requires an
external party outside this repository. Any plan that says "run the gate and get
CERTIFIED" is wrong about the gate.

## 3. Actor separation is enforced, per-execution and campaign-wide

```python
if executor_valid and verifier_valid and executor == verifier:
    context.fail(f"{label} executor and verifier must be different actors")
...
actor_overlap = sorted(context.executors & context.verifiers)
...
context.fail("campaign-wide executor/verifier separation was not demonstrated")
```

Every execution names an `executor` and a `verifier`; they must differ, and the
two role *sets* must not intersect anywhere in the campaign. A single actor
cannot produce a valid campaign. Inventing two names to satisfy this is
gate-gaming and is forbidden by the repository's own constraints — the suite
already carries explicit anti-vacuity guards against exactly this pattern.

## 4. There is no placeholder path — the schema forbids skeletons

```
routes                         minItems 90, maxItems 90
route.workloads                minItems 2,  maxItems 2      (SMALL + MEDIUM)
workload  required             repository_class, repository_id, source_inventory,
                               source_baseline, classification, conversion,
                               target_repository
inventory required             repository_class, file_count, source_file_count,
                               source_bytes, snapshot            (snapshot = artifact)
source_baseline required       build (execution) + test (test_execution)
execution required             status, executor, verifier, command, artifacts
execution.artifacts            minItems 1
artifact required              artifact_id, role, subject, path, sha256, bytes, media_type
```

Every artifact is **content verified** (sha256 + byte length) below the selected
evidence root. So a campaign cannot be authored as a plan: you cannot declare a
route `NOT_RUN` and omit its artifacts, because the required fields bottom out in
real files with real digests. **Writing JSON cannot advance R10 by one cell.**

## 5. Therefore the true size of R10

```
90 directed routes x 2 repository classes            = 180 workloads
per workload: source build + source test
              classification + conversion
              target build + target test             = 6 executions
                                                     -----------------
                                                      1,080 executions
```

each with real logs, real digests, on **independent client repositories** that
must not cross-contaminate the development / negative / holdout / representative
corpora. Class bounds from the gate:

```
SMALL   <=   500 files,  <=  8 MiB
MEDIUM  <= 5,000 files,  <= 64 MiB
```

## 6. What does not exist yet

- No campaign file anywhere in the tree (`find . -name '*repository*campaign*.json'`
  returns only the schema).
- No client-repository corpus on disk — no `client-repos/`, `corpora/`, or
  `external-corpus/` root.
- No second actor. The 182/182 matrix proves the *engine*; it says nothing about
  D6, because the matrix runs the engine's own fixtures, not independent repos.

## 7. The honest next step

R10 is a procurement-and-execution programme, not a coding task:

1. **Decide the two actors.** Who executes and who verifies must be genuinely
   distinct, and the split must hold across all 1,080 executions. This is a
   human/organisational decision and it gates everything else.
2. **Assemble an independent corpus** of 180 repositories inside the SMALL and
   MEDIUM bounds, with provenance recorded, kept disjoint from every corpus the
   engine was developed or tuned against.
3. **Run one workload end to end first** and feed it to the gate alone. The gate
   will report exactly which required fields the engine's current output does not
   yet emit. Expect gaps: the engine was built to satisfy the pytest matrix, not
   this artifact contract.
4. Only then scale to 180. Budget compute accordingly — the 182-node matrix alone
   took 2h43m on engine-owned fixtures.
5. Run the gate. Best case `READY_FOR_EXTERNAL_GATE`. Then hand to the external
   party. `NOT_CERTIFIED` remains true until they act.

## 8. What this means for the current status line

`R9 IMPLEMENTED / R10 MISSING / R11 MISSING` is accurate and should not be
softened. The correct reading is:

- the engine is proven against its own 90-route matrix (D4, D5 — done),
- D6 has not started and cannot start without step 1 and step 2 above,
- D7 is not reachable locally at all.
