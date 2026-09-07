# Package Index

Package: `elmos-build-cache-staging-sota` v1.1.0

Total skills: **31**

## Dependency execution order

1. `elmos-cache-system-architecture` — ELMOS Cache System Architecture
2. `elmos-cache-metadata-database` — Cache Metadata Database
3. `elmos-cache-api-cli-contracts` — Cache API and CLI Contracts
4. `elmos-project-snapshot-merkle` — Project Snapshot and Merkle Tree
5. `elmos-content-addressable-storage` — Content Addressable Storage
6. `elmos-cache-key-fingerprinting` — ActionKey and Stage Fingerprinting
7. `elmos-action-cache` — Action Cache
8. `elmos-project-generation-file-staging` — Project Generation File Staging
9. `elmos-atomic-file-write-promotion` — Atomic File Write and Promotion
10. `elmos-sandbox-overlay-workspaces` — Sandbox and Overlay Workspaces
11. `elmos-intermediate-artifact-manifest` — Intermediate Artifact Manifest
12. `elmos-stage-contract-registry` — Stage Contract Registry
13. `elmos-semantic-interface-hashing` — Semantic and Public Interface Hashing
14. `elmos-incremental-conversion-dag` — Incremental Conversion DAG
15. `elmos-run-journal-state-machine` — Run Journal and State Machine
16. `elmos-checkpoint-resume` — Checkpoint and Resume
17. `elmos-generation-conflict-merge` — Generation Conflict and Merge
18. `elmos-remote-shared-cache` — Remote Shared Cache
19. `elmos-native-build-cache-adapters` — Native Build Cache Adapters
20. `elmos-cache-security-provenance` — Cache Security and Provenance
21. `elmos-cache-retention-gc` — Cache Retention and Garbage Collection
22. `elmos-cache-observability-performance` — Cache Observability and Performance
23. `elmos-cache-chaos-certification` — Chaos Testing and Production Certification
24. `elmos-cache-trace-replay-simulator` — Cache Trace Capture and Replay Simulator
25. `elmos-sota-cache-policy-portfolio` — SOTA Cache Policy Portfolio
26. `elmos-dag-aware-cache-prefetch` — DAG-Aware Future-Reuse Prefetch and Placement
27. `elmos-cost-aware-cache-admission` — Cost-Aware Admission, Retention, and Eviction
28. `elmos-adaptive-cache-policy-orchestrator` — Adaptive Cache Policy Orchestrator
29. `elmos-learning-augmented-cache-control` — Learning-Augmented Cache Control Plane
30. `elmos-cache-autotuning-certification` — Cache Autotuning and Production Certification
31. `elmos-cache-rollout-end-to-end` — Rollout and End-to-End Integration

## Skills by phase

## P0-foundation

- `elmos-cache-system-architecture` — ELMOS Cache System Architecture  
  Dependencies: none
- `elmos-cache-metadata-database` — Cache Metadata Database  
  Dependencies: elmos-cache-system-architecture
- `elmos-cache-api-cli-contracts` — Cache API and CLI Contracts  
  Dependencies: elmos-cache-system-architecture, elmos-cache-metadata-database

## P1-local-cache

- `elmos-project-snapshot-merkle` — Project Snapshot and Merkle Tree  
  Dependencies: elmos-cache-system-architecture
- `elmos-content-addressable-storage` — Content Addressable Storage  
  Dependencies: elmos-cache-system-architecture, elmos-cache-metadata-database
- `elmos-cache-key-fingerprinting` — ActionKey and Stage Fingerprinting  
  Dependencies: elmos-project-snapshot-merkle, elmos-cache-system-architecture
- `elmos-action-cache` — Action Cache  
  Dependencies: elmos-content-addressable-storage, elmos-cache-key-fingerprinting, elmos-cache-metadata-database

## P2-staging

- `elmos-project-generation-file-staging` — Project Generation File Staging  
  Dependencies: elmos-cache-system-architecture, elmos-cache-metadata-database, elmos-content-addressable-storage
- `elmos-atomic-file-write-promotion` — Atomic File Write and Promotion  
  Dependencies: elmos-project-generation-file-staging, elmos-content-addressable-storage
- `elmos-sandbox-overlay-workspaces` — Sandbox and Overlay Workspaces  
  Dependencies: elmos-project-generation-file-staging, elmos-atomic-file-write-promotion
- `elmos-intermediate-artifact-manifest` — Intermediate Artifact Manifest  
  Dependencies: elmos-content-addressable-storage, elmos-project-generation-file-staging, elmos-cache-metadata-database

## P3-incremental

- `elmos-stage-contract-registry` — Stage Contract Registry  
  Dependencies: elmos-cache-key-fingerprinting, elmos-intermediate-artifact-manifest
- `elmos-semantic-interface-hashing` — Semantic and Public Interface Hashing  
  Dependencies: elmos-project-snapshot-merkle, elmos-cache-key-fingerprinting, elmos-stage-contract-registry
- `elmos-incremental-conversion-dag` — Incremental Conversion DAG  
  Dependencies: elmos-project-snapshot-merkle, elmos-cache-key-fingerprinting, elmos-semantic-interface-hashing, elmos-stage-contract-registry

## P4-recovery

- `elmos-run-journal-state-machine` — Run Journal and State Machine  
  Dependencies: elmos-cache-metadata-database, elmos-incremental-conversion-dag, elmos-project-generation-file-staging
- `elmos-checkpoint-resume` — Checkpoint and Resume  
  Dependencies: elmos-intermediate-artifact-manifest, elmos-run-journal-state-machine, elmos-content-addressable-storage
- `elmos-generation-conflict-merge` — Generation Conflict and Merge  
  Dependencies: elmos-project-generation-file-staging, elmos-atomic-file-write-promotion, elmos-intermediate-artifact-manifest

## P5-distributed

- `elmos-remote-shared-cache` — Remote Shared Cache  
  Dependencies: elmos-content-addressable-storage, elmos-action-cache, elmos-cache-metadata-database, elmos-cache-api-cli-contracts
- `elmos-native-build-cache-adapters` — Native Build Cache Adapters  
  Dependencies: elmos-action-cache, elmos-cache-key-fingerprinting, elmos-sandbox-overlay-workspaces

## P6-assurance

- `elmos-cache-security-provenance` — Cache Security and Provenance  
  Dependencies: elmos-content-addressable-storage, elmos-action-cache, elmos-project-generation-file-staging, elmos-intermediate-artifact-manifest, elmos-remote-shared-cache
- `elmos-cache-retention-gc` — Cache Retention and Garbage Collection  
  Dependencies: elmos-content-addressable-storage, elmos-cache-metadata-database, elmos-intermediate-artifact-manifest
- `elmos-cache-observability-performance` — Cache Observability and Performance  
  Dependencies: elmos-action-cache, elmos-project-generation-file-staging, elmos-run-journal-state-machine, elmos-remote-shared-cache, elmos-incremental-conversion-dag
- `elmos-cache-chaos-certification` — Chaos Testing and Production Certification  
  Dependencies: elmos-atomic-file-write-promotion, elmos-checkpoint-resume, elmos-cache-security-provenance, elmos-cache-observability-performance

## P6-optimization

- `elmos-cache-trace-replay-simulator` — Cache Trace Capture and Replay Simulator  
  Dependencies: elmos-cache-observability-performance, elmos-action-cache, elmos-incremental-conversion-dag
- `elmos-sota-cache-policy-portfolio` — SOTA Cache Policy Portfolio  
  Dependencies: elmos-cache-trace-replay-simulator, elmos-content-addressable-storage, elmos-action-cache
- `elmos-dag-aware-cache-prefetch` — DAG-Aware Future-Reuse Prefetch and Placement  
  Dependencies: elmos-sota-cache-policy-portfolio, elmos-incremental-conversion-dag, elmos-remote-shared-cache, elmos-project-generation-file-staging
- `elmos-cost-aware-cache-admission` — Cost-Aware Admission, Retention, and Eviction  
  Dependencies: elmos-sota-cache-policy-portfolio, elmos-cache-retention-gc, elmos-cache-observability-performance
- `elmos-adaptive-cache-policy-orchestrator` — Adaptive Cache Policy Orchestrator  
  Dependencies: elmos-sota-cache-policy-portfolio, elmos-cost-aware-cache-admission, elmos-cache-trace-replay-simulator
- `elmos-learning-augmented-cache-control` — Learning-Augmented Cache Control Plane  
  Dependencies: elmos-adaptive-cache-policy-orchestrator, elmos-cache-security-provenance, elmos-cache-trace-replay-simulator
- `elmos-cache-autotuning-certification` — Cache Autotuning and Production Certification  
  Dependencies: elmos-learning-augmented-cache-control, elmos-dag-aware-cache-prefetch, elmos-cache-chaos-certification

## P7-rollout

- `elmos-cache-rollout-end-to-end` — Rollout and End-to-End Integration  
  Dependencies: elmos-cache-api-cli-contracts, elmos-incremental-conversion-dag, elmos-checkpoint-resume, elmos-generation-conflict-merge, elmos-native-build-cache-adapters, elmos-cache-retention-gc, elmos-cache-chaos-certification, elmos-cache-autotuning-certification
