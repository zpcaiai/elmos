# 01 — FDE Daily Work → Elmos Product Capability

## Personas

| Persona | Primary responsibility |
|---|---|
| Customer executive sponsor | Outcome, risk, investment, escalation and acceptance |
| Business/process owner | Workflow truth, rules, baseline and adoption |
| Forward Deployed Engineer | Discovery, scope, architecture, implementation, communication and handoff |
| Solution/enterprise architect | System boundaries, standards, target architecture and ADRs |
| Repository maintainer | Source intent, ownership, review and operability |
| Security/privacy/compliance | Access, threat, data use, controls, waivers and evidence |
| Data/database owner | Schema, semantics, migration, lineage and reconciliation |
| QA/test architect | Oracles, coverage, regression and verification |
| SRE/platform engineer | Runtime, SLO, rollout, recovery and incidents |
| Product manager | Scope, acceptance, adoption, feedback and roadmap |
| Procurement/legal/finance | Questionnaires, terms, cost, licensing and commercial readiness |
| End user/champion | Critical journey, trust, training, feedback and value |
| Independent assurer | Evidence freshness, counterexamples, blockers and readiness decision |

## End-to-end activity map

| Stage | Elmos must support |
|---|---|
| Pre-engagement | Qualification, technical discovery, access feasibility, security/procurement, value hypothesis |
| Discovery | Stakeholders, workflows, decisions, pain, baseline, data, constraints, unknowns |
| Scope | PoC/pilot/production boundaries, SOW, acceptance, risks, dependencies, change control |
| Technical intake | Custody, RevisionSet, assets, toolchains, dependencies, environments, build |
| Understanding | System graph, business mapping, runtime evidence, history and ownership |
| Assessment | All issue domains, root causes, blast radius, business impact, coverage and unknowns |
| Design | Invariants, alternatives, ADR, target state, migration and rollback |
| Implementation | Atomic transformation, result interception, provenance, review and commit |
| Verification | Static, test, differential, mutation, performance, security, formal and readiness |
| Release preparation | Shadow, dual-run, canary, SLO, reconciliation, rollback rehearsal |
| Operations | Status, incident, support, diagnostics, corrective action and evidence |
| Adoption/handoff | Training, champions, usage, value, ownership, runbooks and support |
| Productization | Reusable recipes, adapters, fixtures, portfolio patterns and roadmap feedback |

## Anti-pattern

A generic chat window is not an FDE operating system. Every activity above needs a typed state model, role/approval boundary, durable workflow, evidence projection, collaboration surface and API/connector contract.
