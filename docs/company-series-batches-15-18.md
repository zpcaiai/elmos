# Authoritative company-series Batches 15–18

This additive company series implements the supplied Skills 461–745 after the cross-language Batch 14 product-growth system. Existing repository documents named `batch-15-verification.md` through `batch-18-verification.md` belong to a separate technical-engine sequence and remain unchanged.

| Batch | Authority model | Skills | Sequential gate | Final status | Persistence |
| --- | --- | ---: | --- | --- | --- |
| 15 | Company Operating and Governance System (`COGS`) | 461–525 (65) | C15-A → C15-G | `company-scale-operating-ready` | V24 / `company_ops` / 88 tables |
| 16 | AI-native operating system | 526–592 (67) | AI16-A → AI16-G | `bounded-autonomous-company-ready` | V25 / `agent_workforce` / 76 tables |
| 17 | Vertical Solution Pack four-layer model | 593–668 (76) | V17-A → V17-G | `vertical-commercial-delivery-ready` | V26 / `vertical_solutions` / 40 tables |
| 18 | Group Integration Target Model (`GITM`) | 669–745 (77) | M18-A → M18-H | `group-integration-completed` | V27 / `group_integration` / 51 tables |

## Implementation shape

- `modules/company-series` supplies one immutable evidence protocol, four exact program definitions, sequential non-compensating adjudication and deterministic artifact writing.
- Every external gate is represented by a read-only `EvidenceAuthority`. Missing, stale, mismatched, partial, unauthorised or future-dated evidence blocks advancement.
- Every outcome records `external_operation_executed=false`. The module contains no process, HTTP, provider SDK or database execution mechanism.
- Sixteen Draft 2020-12 schemas define program, gate evidence, evidence pack and conformance report contracts.
- V24–V27 use dedicated PostgreSQL schemas so canonical company terms do not collide with the earlier technical-engine tables. Every table has organization-scoped forced RLS; designated evidence histories are append-only.
- Four source manifests bind generated Skill inventories to SHA-256 digests of the supplied authority texts.

## Evidence boundary

Repository completeness proves source reconciliation, deterministic evaluation, schema integrity, path safety, tenant persistence controls and fail-closed behavior. It does not prove a real company is governed, an Agent may act autonomously, an industry edition complies with law, or an M&A integration has completed. Every field checklist row remains `NOT_RUN` until the relevant external owner and system of record provide current evidence.

## Deliverables

- Batch 15: `agent-skills/company-operating-system`, `contracts/company-operating-system-schema`, `company-operating-system/` artifacts.
- Batch 16: `agent-skills/agent-workforce`, `contracts/agent-workforce-schema`, `ai-native-company/` artifacts.
- Batch 17: `agent-skills/vertical-solutions`, `contracts/vertical-solution-schema`, `vertical-solution-factory/` artifacts.
- Batch 18: `agent-skills/group-integration`, `contracts/group-integration-schema`, `group-integration-factory/` artifacts.
