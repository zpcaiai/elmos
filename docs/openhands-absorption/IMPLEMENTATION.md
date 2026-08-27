# OpenHands Absorption P0/P1 Implementation

The supplied ZIP is a specification package, not executable authority. Its
SHA-256 is recorded by `tools/validate_engine.py`; archive scripts are not
executed by the importer or runtime.

| Package capability | Repository implementation |
|---|---|
| P0-01/02/04 | `models.py`, `ledger.py`, `runtime.py`, CAS and fenced checkpoints |
| P0-03/08 | `tools.py`, `firewall.py` |
| P0-05/06 | `workspace.py`, `plane.py` |
| P0-07/09 | `context.py`, `gates.py` |
| P1-01/02/03 | `skills.py`, `packages.py`, `dag.py` |
| P1-04/05 | `providers.py`, `browser.py` |

The local implementation provides deterministic engineering qualification. It
does not claim external Provider, Temporal, microVM, browser/device, cloud,
independent verifier, production deployment or customer golden-repository
execution. Those are explicit adapter/evidence boundaries and remain
`NOT_RUN`/`NOT_CERTIFIED` until the named environments execute them.

The only success transition is `CompletionGateEngine`; Agent prose produces a
`CompletionProposal` and cannot bypass mandatory failed or evidence-free checks.
All side effects pass through `ToolGateway`, which writes action, policy and
observation events with tenant scope and idempotency keys.
