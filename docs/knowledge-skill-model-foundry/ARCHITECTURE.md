# Architecture & Domain Design

## Six Asset Layers Separation

1. **Knowledge Objects**: Facts, source documents, repository specifications with immutable content hashes and training consent tags.
2. **Skill Contracts**: Declarative method signatures with pre/post-conditions, input/output JSON schemas, and compensatory rollback policies.
3. **Experience Episodes**: Complete agent execution trajectories with privacy-preserving token/secret sanitization and reward attribution.
4. **Dataset Items**: Curated training records partitioned into train/val/holdout splits with consent verification and quarantine support.
5. **Model Releases**: Immutable bundles comprising base models, private LoRA/QLoRA adapters, toolchain images, and policy packages.
6. **Evidence Bundles**: WORM Merkle tree proofs, cryptographic signatures, and E0–E5 quality gate receipts.

## Lifecycle Pipelines

- `knowledge-to-skill`: Ingests specification documents and synthesizes testable skill contracts.
- `experience-to-dataset`: Extracts successful high-reward trajectories and calibrates balanced training datasets.
- `train-certify-deploy`: Fine-tunes model adapters, performs offline evaluations, shadow canary testing, and certified deployment.
- `customer-private-adapter`: Tenant-scoped end-to-end adapter customization with strict zero-leakage guarantees.
