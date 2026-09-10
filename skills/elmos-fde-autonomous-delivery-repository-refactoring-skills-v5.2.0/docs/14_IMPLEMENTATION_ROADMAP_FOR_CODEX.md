# 14 — Codex Implementation Roadmap

| Batch | Outcome | Depends on | Tasks |
|---|---|---|---|
| B00 | Package contracts and canonical bindings |  | 1 |
| B01 | Authority, identity and append-only ledgers | B00 | 2 |
| B02 | FDE engagement and customer delivery hub | B00, B01 | 60 |
| B03 | Repository custody, inventory and support profile | B00, B01 | 30 |
| B04 | Native Runtime Lab and service virtualization | B03 | 30 |
| B05 | Unified semantic system graph | B03, B04 | 50 |
| B06 | Finding ontology, coverage and assessment orchestration | B05 | 20 |
| B07 | Architecture, correctness, security and data audits | B06 | 40 |
| B08 | Performance, QA, UX, AI and FinOps audits | B06 | 50 |
| B09 | Invariant recovery and target-state planning | B07, B08 | 30 |
| B10 | Proof-guided ChangeSet execution | B09, B01 | 20 |
| B11 | Modernization, polyglot and database transformation routes | B10 | 30 |
| B12 | Verification mesh and formal assurance routing | B10 | 30 |
| B13 | Release rehearsal, incident and handoff | B12 | 30 |
| B14 | Product UX and collaboration surfaces | B02, B06, B09, B12 | 13 |
| B15 | Connector and Adapter ecosystem | B01, B03 | 27 |
| B16 | Commercial multi-tenant operations, metering and trust center | B01, B14, B15 | 1 |
| B17 | Reusable recipe learning, portfolio and roadmap feedback | B13, B16 | 30 |
| B18 | Scale certification fixtures and release hardening | B17 | 12 |

## Delivery discipline

- Implement a working vertical slice for one Skill before mass-generating scaffolding.
- Keep every task independently reviewable and executable from a clean checkout.
- Resolve target canonical bindings during B00; do not guess IDs.
- Run package/unit/schema/eval tests continuously.
- Add native tool/database/cloud tests only where the environment really supports them; otherwise keep an explicit unexecuted gate.
- Promote P0 before P1/P2; do not enable all routes simultaneously.

Detailed tasks: `catalog/implementation-tasks.json` and `implementation/batches/`.
