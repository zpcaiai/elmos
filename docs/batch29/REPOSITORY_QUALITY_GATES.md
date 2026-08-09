# Batch 29 Repository Capability Quality Gates

## Purpose and evidence boundary

This gate defines the repository-level capability target for the nine languages
currently recognized by the Batch 29 polyglot engine: Java, Python, C#,
TypeScript, Go, Rust, C++, Objective-C, and Swift. It does not infer support
from an analyzer, emitter, single-function corpus, or reverse direction.

The contract covers all `9 × 8 = 72` ordered source-to-target directions. Each
direction carries its own status and both a `SMALL` and `MEDIUM` workload.
Existing per-route evidence is not rewritten or promoted by this gate.

The input contract is
`schemas/batch29/repository-capability-campaign.schema.json`. The result
contract is `schemas/batch29/repository-gate-result.schema.json`.

## Exact repository classes

The class is derived from measured inventory; it is not a free-form label.

| Class | Exact bounded rule |
| --- | --- |
| `SMALL` | `file_count <= 500` and `source_bytes <= 8 MiB` |
| `MEDIUM` | Not `SMALL`, while `file_count <= 5,000` and `source_bytes <= 64 MiB` |

`source_file_count` must equal `file_count` for a directed workload. A mixed
supported-language code estate must first be decomposed into explicit directed
workloads; otherwise a whole-repository claim could hide unconverted code.
Every source file must contribute at least one classified unit.

## Required 72-route matrix

The canonical language order is:

1. `java`
2. `python`
3. `csharp`
4. `typescript`
5. `go`
6. `rust`
7. `cpp`
8. `objc`
9. `swift`

The campaign must contain every ordered pair exactly once, must contain no
self-route, and must not substitute one direction for its reverse. Every route
must have status `PASSED`. `FAILED`, `SKIPPED`, `UNSUPPORTED`, and `NOT_RUN`
are explicit non-passing states; omission is also non-passing.

Each direction must contain exactly one `SMALL` and one `MEDIUM` workload, for
144 workload records in total.

## Gate R29-REPO-A — Source baseline

Before translation, each workload must provide a real source baseline:

- the source repository snapshot has a content-addressed artifact;
- the source build or language-native compile/check command is recorded and
  has status `PASSED`;
- the source test command is recorded, has at least one test, and reports every
  test passed;
- source failed and skipped test counts are both zero.

A dynamically interpreted source still needs its real compile/check boundary;
the field cannot be declared not applicable.

## Gate R29-REPO-B — Complete classification

Every source unit must receive an explicit verdict. The following equalities
are mandatory:

```text
classified_units == total_units
ready_units == total_units
unsupported_units == 0
skipped_units == 0
failed_units == 0
unknown_units == 0
```

The verdict counts must sum exactly to `total_units`, and `total_units` must
cover every source file. A successful subset cannot be rounded up to a
repository claim.

## Gate R29-REPO-C — Complete conversion

Every classified unit must be attempted and converted:

```text
attempted_units == total_units
converted_units == total_units
unsupported_units == 0
skipped_units == 0
failed_units == 0
```

Classification and conversion totals must agree. A partial artifact, permissive
stub, silent drop, or unsupported unit fails the gate.

## Gate R29-REPO-D — Whole target repository

The assembled target must set `whole_repository=true`, include every converted
unit, and report `excluded_units=0`. Its real target toolchain build and full
test suite must both pass. Target failed and skipped test counts are zero. The
target build evidence includes both a build log and the complete repository
artifact digest.

## Gate R29-REPO-E — Content-addressed evidence

Every snapshot, classification report, conversion report, build log, test log,
and target repository artifact records:

- a unique `artifact_id`, unique path, and exact subject containing campaign,
  route, source, target, repository, size class, stage, and role;
- a relative POSIX path below the selected evidence root;
- exact byte count and lowercase `sha256:<hex>` digest;
- `application/json` media type and the same subject inside the verified bytes.

The gate rejects absolute paths, traversal, symlink components, missing files,
digest or byte-count mismatch, artifact-ID/path reuse, hard-link reuse, subject
swaps, and files that change while being read. It parses the raw inventory,
unit verdicts, conversion outcomes, test cases, and target manifest, then
recomputes every reported counter. Verified artifacts are checked again before
the result is emitted.

The result binds the canonical campaign digest, campaign/result schema digests,
gate implementation digest, and canonical evidence-set digest. Synthetic unit
fixtures exercise the evaluator but are not checked-in route evidence.

## Gate R29-REPO-F — Executor/verifier separation

Every build, test, classification, and conversion record names an executor and
a verifier. They must differ for the individual record, and the executor and
verifier identity sets must be disjoint across the entire campaign. A label is
local engineering provenance, not proof of organizational independence;
external review remains a separate gate.

## Decisions and certification boundary

`scripts/batch29/run_repository_gate.py` is the only authority for this
repository campaign result.

- All 72 directions, all 144 workloads, all zero-tolerance counters, all actor
  separation checks, and all artifact checks passing yields
  `READY_FOR_EXTERNAL_GATE` with process exit `0`.
- Any missing direction or class, malformed record, `NOT_RUN`, skip, failure,
  unsupported/unknown unit, incomplete build/test, actor overlap, or artifact
  failure yields `LIMITED` with process exit `1`.
- Both outcomes remain `NOT_CERTIFIED`. The maximum local decision is
  `READY_FOR_EXTERNAL_GATE`; the gate cannot emit `CERTIFIED`.

The campaign must record `external_verification_status=NOT_RUN`. This one
external boundary does not masquerade as local evidence and therefore does not
block preparation for the external gate; it does block certification. Every
route, workload, build, test, classification, and conversion `NOT_RUN` state
fails closed.

## Invocation

```bash
python3 scripts/batch29/run_repository_gate.py \
  path/to/repository-capability-campaign.json \
  --evidence-root path/to/evidence \
  --output path/to/repository-gate-result.json
```

The evidence root defaults to the campaign file's directory. The gate verifies
recorded evidence; it does not execute repository commands and does not create
route certification evidence.
