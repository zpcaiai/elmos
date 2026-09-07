# ELMOS Cache and Staging Acceptance Matrix

Every executed row must record: test ID, exact command, fixture, source commit, package version, platform, toolchain profile, result, output digest, and evidence reference.

| ID | Capability | Scenario | Required result |
|---|---|---|---|
| SNAP-001 | Snapshot | Same logical repository on Linux/macOS/Windows fixtures | Same canonical root digest |
| SNAP-002 | Snapshot | Whitespace-only edit | Raw digest changes; semantic digest follows declared policy |
| SNAP-003 | Snapshot | Content-preserving rename | Rename recognized; unrelated Merkle subtrees unchanged |
| KEY-001 | ActionKey | Change irrelevant temporary path | ActionKey unchanged |
| KEY-002 | ActionKey | Change rule pack, compiler, target SDK, prompt, model snapshot, or public dependency interface | ActionKey changes |
| KEY-003 | ActionKey | Change undeclared environment value | Key unchanged and hermeticity audit records exclusion |
| CAS-001 | CAS | Two concurrent identical writers | One canonical object; both receive same digest |
| CAS-002 | CAS | Kill during blob write | No visible partial canonical object |
| CAS-003 | CAS | Corrupt stored bytes | Read rejects; object quarantined or repaired |
| CACHE-001 | Action Cache | Repeated exact deterministic action | Outputs restored without stage execution |
| CACHE-002 | Action Cache | Lower validation than consumer minimum | Entry rejected with `VALIDATION_TOO_LOW` |
| CACHE-003 | Action Cache | Same ActionKey, different result digest | Both quarantined; nondeterminism alert emitted |
| STAGE-001 | Staging | Kill after logical-path reservation | Safe reclaim; no published file |
| STAGE-002 | Staging | Kill during write | Partial temp deleted/quarantined; never sealed |
| STAGE-003 | Staging | Kill after fsync before metadata commit | Recovery converges without duplicate logical file |
| STAGE-004 | Staging | Kill after seal before CAS promotion | Resume verifies and promotes idempotently |
| STAGE-005 | Staging | Undeclared generator output | Quarantined and excluded from final tree |
| STAGE-006 | Staging | Path traversal, reserved name, case collision, or symlink escape | Rejected before write |
| STAGE-007 | Staging | Stale worker attempts seal | Rejected by lease epoch/version |
| PUB-001 | Publication | Kill while materializing candidate tree | Active previous tree unchanged |
| PUB-002 | Publication | Atomic pointer/rename switch | Readers see old or new complete tree only |
| PUB-003 | Publication | Evidence bound to different tree digest | Publication blocked |
| DAG-001 | Incremental | Private method-body change | Unrelated dependents remain cached |
| DAG-002 | Incremental | Public route/schema/event change | Affected dependents invalidated |
| DAG-003 | Incremental | Rule-pack upgrade with compatible IR schema | Parse/analysis/IR hits retained where safe |
| CHECK-001 | Checkpoint | Resume after worker crash | Same sealed output digest as clean run |
| CHECK-002 | Checkpoint | Relevant source/toolchain/rule change | Checkpoint rejected with exact reason |
| CHECK-003 | Checkpoint | Side effect committed before crash | Retry does not duplicate effect |
| JOURNAL-001 | Journal | Duplicate event delivery | Materialized state unchanged after idempotent replay |
| LEASE-001 | Lease | Stale worker commits after recovery | Commit rejected |
| REMOTE-001 | Remote | Network loss during multipart upload | No discoverable incomplete entry |
| REMOTE-002 | Remote | Offline execution, later sync | Local run succeeds; synchronization is idempotent |
| REMOTE-003 | Remote | Untrusted fork result | Cannot satisfy official/production trust namespace |
| SEC-001 | Security | Cross-tenant digest lookup | Access denied without useful existence leak |
| SEC-002 | Security | Secret in generated file | Shared upload and publication blocked |
| SEC-003 | Security | Forged provenance or elevated validation claim | Rejected and audited |
| GC-001 | GC | Artifact reachable from active checkpoint | Not deleted |
| GC-002 | GC | Interrupted deletion pass | Resumes idempotently with receipts |
| OBS-001 | Observability | Cache miss | Exact changed fingerprint dimensions shown |
| OBS-002 | Observability | Failure trace | Run/node/artifact/staged-file/checkpoint IDs correlate |
| PERF-001 | Performance | No-change full-project rerun | Meets declared saved-work and p95 budgets |
| PERF-002 | Performance | Single independent method change | Meets declared partial-hit budget |
| CHAOS-001 | Recovery | Kill at each file-write boundary | No partial publication; recovery converges |
| CHAOS-002 | Recovery | Disk full/inode exhaustion | Controlled failure; no corrupt canonical state |
| CERT-001 | Certification | Expired/revoked/scope-mismatched certificate | Production reuse rejected |
| E2E-001 | End to end | Java/Spring → C#/ASP.NET complete project | Complete staged, validated, atomically published tree |
| E2E-002 | End to end | Service restart during generation | Resume without duplicate side effects or partial output |
| E2E-003 | End to end | No-change rerun | Same final tree digest; model/compiler work avoided except freshness policy |

## Required performance scenarios

1. identical rerun;
2. formatting/comment-only edit;
3. private body edit;
4. public API edit;
5. database/event/schema edit;
6. rule-pack upgrade;
7. compiler/SDK upgrade;
8. dependency lockfile edit;
9. prompt/model snapshot edit;
10. remote-cache outage and recovery.

## Suggested initial engineering targets

Targets are workload-dependent and must be calibrated against real ELMOS projects:

- identical rerun stage hit rate: 95–100%;
- one independent file edit: 80–98% unaffected-stage reuse;
- one internal module implementation edit: 70–95% unaffected-stage reuse;
- process restart: nearly all sealed/promoted completed work recoverable;
- published output: zero partial-tree exposure;
- same ActionKey/different output: zero silent acceptance.
