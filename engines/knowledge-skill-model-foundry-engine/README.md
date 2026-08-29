# Elmos Knowledge–Skill–Model Foundry Engine (v2.0.0)

Production-grade runtime engine for the **Knowledge–Skill–Model Foundry v2.0.0** skill package within the *Elmos Proof-Driven Agentic Harness / Repository Semantic Compiler v3*.

## Key Capabilities

1. **Asset Separation**: Strict isolation and governance across 6 asset layers:
   - Knowledge Objects
   - Skill Contracts & Handlers
   - Experience Episodes
   - Dataset Items
   - Model / Adapter Releases
   - Verifiable Evidence Bundles
2. **Hierarchical Meta-First Skill Discovery**:
   - 17 Top-level Meta-Skills
   - 458 Domain-specific Atomic Skills across 17 Capability Packs
3. **Automated Lifecycle Pipelines**:
   - `knowledge-to-skill`: Synthesize executable and verifiable skills from repository knowledge.
   - `experience-to-dataset`: Process, sanitize, and calibrate task episodes into training datasets.
   - `train-certify-deploy`: Orchestrate training, offline evaluation, shadow canary, and immutable release.
   - `customer-private-adapter`: Tenant-isolated private LoRA/QLoRA adapter training and deployment.
4. **Policy-as-Code & Gate Evaluation**:
   - Training Eligibility Policy
   - Skill Execution Policy
   - Model Promotion Policy
   - E0–E5 Certification Gates with Merkle Evidence Proofs
5. **Multi-Tenant Persistence & RLS**:
   - PostgreSQL 16+ DDL schema with 25 core tables
   - SQLite in-memory emulation for hermetic unit and integration testing
