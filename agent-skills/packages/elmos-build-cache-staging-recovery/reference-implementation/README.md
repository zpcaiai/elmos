# Reference implementation

This standard-library Python package demonstrates core semantics:

- canonical ActionKey hashing;
- immutable local SHA-256 CAS;
- append-only journal;
- generated-file reservation;
- atomic temporary write and sealing;
- CAS promotion;
- complete-tree validation/materialization;
- atomic publication pointer;
- state-based recovery planning.

It is intentionally small and is **not** the production ELMOS server. Production work must implement the Skills, SQL, API, security, leases, sandboxing, telemetry, distributed cache, native build adapters, chaos tests, and certification gates.

Run:

```bash
python3 -m unittest discover -s reference-implementation/tests -v
```
