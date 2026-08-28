# ELMOS OpenHands Absorption Engine

This is the repository-owned implementation of the supplied
`elmos-openhands-absorption-p0-p1-v1.0.0` specification package. It is a
dependency-free reference runtime with durable SQLite/CAS persistence and
replaceable production adapters.

Implemented boundaries:

- P0-01 stateless turn runtime with fenced leases and budgets;
- P0-02 hash-chained immutable event ledger, outbox and projections;
- P0-03 typed action/observation protocol and tool gateway;
- P0-04 checkpoints, CAS snapshots, resume and audit replay;
- P0-05 tenant-scoped workspace and sandbox provider abstraction;
- P0-06 worker leases, admission control and resumable event streams;
- P0-07 evidence-aware context ranking, retention and token packing;
- P0-08 fail-closed action firewall with secret, path, network and destructive
  command checks;
- P0-09 deterministic hooks, verification gates and traceability graph;
- P1-01 staged Skill disclosure and permission-aware routing;
- P1-02 signed capability package registry with pin/revoke/rollback lifecycle;
- P1-03 durable multi-agent DAG with fan-out/fan-in and fencing;
- P1-04 native, Codex-compatible, Claude-compatible and OpenHands-compatible
  provider adapters plus circuit breaking;
- P1-05 browser scenario validation, privacy masking, evidence capture and
  semantic replay contracts.

The local provider is intentionally limited to trusted local development. L2+
isolation and real external provider/browser execution require an explicitly
configured adapter and are reported as `NOT_RUN` when unavailable. No module
executes package-provided scripts or treats model prose as authority.

```bash
PYTHONPATH=engines/openhands-absorption-engine/src \
  python -m unittest discover -s engines/openhands-absorption-engine/tests -p 'test_*.py'
python3 engines/openhands-absorption-engine/tools/validate_engine.py
```
