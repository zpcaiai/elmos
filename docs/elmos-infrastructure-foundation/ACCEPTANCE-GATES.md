# Acceptance Gates

| Gate | Mandatory evidence | Blocks |
|---|---|---|
| G0 Contracts | ADRs, versioned API/schema, state machine, implementation plan | All implementation |
| G1 Security | OIDC, membership tenant, RBAC, RLS attack tests, runner mTLS, secret tests | Private source |
| G2 Reliability | Idempotent start/complete, lease/reaper/fencing, cancel/checkpoint/reconcile/replay | Long tasks |
| G3 Reproducibility | Fixed commit, snapshot manifest, CAS integrity, action-key tests, sealed staging, reproducible toolchain | Conversion |
| G4 Execution | Capability/fair/locality scheduler, transfer resume, shard recovery, sandbox escape tests | Multi-tenant scale |
| G5 Semantics | Native compiler resolution, stable IR, explicit gaps, source maps, idempotent rules | Broad automation |
| G6 Java loop | Installation-to-PR fixture, bounded repair, no duplicate side effects | Pilot |
| G7 Verification | Baseline/target diff, E1-E5, SBOM/provenance/signature, offline Evidence Pack | Delivery |
| G8 Operations | SLO, alerts/runbooks, cost reconciliation, ETA calibration, restore/replay, canary rollback | Production |
| G9 Certification | Scale/fault/security suite, three repeatable pilots, signed readiness decision | Commercial claim |

## Status semantics

- `CERTIFIED`: all mandatory evidence passes for the exact declared scope.
- `LIMITED`: usable only under explicit constraints, deviations, monitoring, approval, and expiry.
- `EXPERIMENTAL`: non-production evaluation; evidence is insufficient for controlled production use.
- `BLOCKED`: mandatory gate failed, missing, stale, ambiguous, or untrusted.

A static Skill bundle can be structurally valid while the eLMOS implementation remains `BLOCKED`.
