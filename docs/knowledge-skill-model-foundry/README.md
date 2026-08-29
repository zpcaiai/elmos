# Elmos Knowledge–Skill–Model Foundry (v2.0.0)

Commercial production-grade Skills Package and Runtime Engine for continuous repository learning, skill synthesis, dataset curation, private adapter fine-tuning, and Merkle evidence certification.

## Package Architecture Overview

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      17 Hierarchical Meta-Skills                       │
 │  (elmos-00-foundation-contracts ... elmos-16-self-evolution-release)   │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │ Router Discovery
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                 458 Domain Atomic Skill Contracts & Handlers            │
 │ (Preconditions, Postconditions, Schema Envelopes, Rollback Boundaries) │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         ▼                           ▼                           ▼
 ┌───────────────┐           ┌───────────────┐           ┌───────────────┐
 │   Knowledge   │           │  Experience   │           │    Dataset    │
 │    Objects    │           │    Memory     │           │    Foundry    │
 └───────┬───────┘           └───────┬───────┘           └───────┬───────┘
         │                           │                           │
         └───────────────────────────┼───────────────────────────┘
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                    Policy-as-Code & E0-E5 Gates                        │
 │  (Training Eligibility, Skill Execution, Model Promotion, Merkle Proof)│
 └───────────────────────────────────┬────────────────────────────────────┘
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                Private Model Foundry & Serving Gateway                 │
 │       (LoRA/QLoRA, KV Prefix Cache, Fallback Circuit Breaker)          │
 └────────────────────────────────────────────────────────────────────────┘
```

## Core Statistics

- **Meta-Skills**: 17 (Top-level entry points)
- **Atomic Skills**: 458 (Domain-specific executable contracts)
- **Capability Packs**: 17
- **Database Schema**: 25 PostgreSQL 16+ tables with RLS and multi-tenancy
- **Schemas**: 5 JSON Schemas
- **Policies**: 3 Rego / Embedded Policy engines
- **Pipelines**: 4 automated lifecycle pipelines
