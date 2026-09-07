# Skill Dependency Graph

```mermaid
graph TD
  ORCH["ORCH: elmos-infrastructure-program-orchestrator"]
  ARCH["ARCH: elmos-architecture-contract-governance"]
  SEC["SEC: elmos-identity-tenant-security"]
  WF["WF: elmos-temporal-task-reliability"]
  SNAP["SNAP: elmos-repository-snapshot-workspace"]
  CAS["CAS: elmos-content-addressed-cache"]
  STAGE["STAGE: elmos-staging-snapshot-promotion"]
  TOOL["TOOL: elmos-reproducible-toolchain"]
  INC["INC: elmos-incremental-semantic-index"]
  RUN["RUN: elmos-runner-scheduler-execution"]
  SBX["SBX: elmos-secure-sandbox-runtime"]
  IR["IR: elmos-semantic-ir-compiler-platform"]
  LLM["LLM: elmos-model-gateway-agent-runtime"]
  VER["VER: elmos-verification-fabric"]
  EVD["EVD: elmos-evidence-pack-offline-verification"]
  POL["POL: elmos-policy-supply-chain-signing"]
  OBS["OBS: elmos-observability-finops"]
  REL["REL: elmos-progressive-delivery"]
  DR["DR: elmos-backup-recovery-replay"]
  BENCH["BENCH: elmos-scale-benchmark-certification"]
  JAVA["JAVA: elmos-java-migration-production-loop"]
  READY["READY: elmos-production-readiness-gate"]
  ORCH --> ARCH
  ARCH --> SEC
  ARCH --> WF
  SEC --> WF
  SEC --> SNAP
  WF --> SNAP
  ARCH --> CAS
  SNAP --> CAS
  CAS --> STAGE
  WF --> STAGE
  CAS --> TOOL
  SEC --> TOOL
  SNAP --> INC
  CAS --> INC
  TOOL --> INC
  WF --> RUN
  CAS --> RUN
  TOOL --> RUN
  SEC --> RUN
  SEC --> SBX
  RUN --> SBX
  TOOL --> SBX
  INC --> IR
  TOOL --> IR
  CAS --> IR
  SEC --> LLM
  CAS --> LLM
  INC --> LLM
  IR --> LLM
  SBX --> LLM
  TOOL --> VER
  IR --> VER
  SBX --> VER
  LLM --> VER
  CAS --> EVD
  VER --> EVD
  STAGE --> EVD
  POL --> EVD
  SEC --> POL
  TOOL --> POL
  SBX --> POL
  WF --> OBS
  RUN --> OBS
  LLM --> OBS
  EVD --> OBS
  VER --> REL
  OBS --> REL
  POL --> REL
  WF --> DR
  CAS --> DR
  EVD --> DR
  OBS --> DR
  OBS --> BENCH
  REL --> BENCH
  DR --> BENCH
  POL --> BENCH
  SEC --> JAVA
  WF --> JAVA
  SNAP --> JAVA
  CAS --> JAVA
  STAGE --> JAVA
  TOOL --> JAVA
  SBX --> JAVA
  VER --> JAVA
  EVD --> JAVA
  ORCH --> READY
  JAVA --> READY
  BENCH --> READY
```

## Topological execution order

1. `elmos-infrastructure-program-orchestrator`
2. `elmos-architecture-contract-governance`
3. `elmos-identity-tenant-security`
4. `elmos-temporal-task-reliability`
5. `elmos-repository-snapshot-workspace`
6. `elmos-content-addressed-cache`
7. `elmos-reproducible-toolchain`
8. `elmos-staging-snapshot-promotion`
9. `elmos-incremental-semantic-index`
10. `elmos-runner-scheduler-execution`
11. `elmos-semantic-ir-compiler-platform`
12. `elmos-secure-sandbox-runtime`
13. `elmos-model-gateway-agent-runtime`
14. `elmos-policy-supply-chain-signing`
15. `elmos-verification-fabric`
16. `elmos-evidence-pack-offline-verification`
17. `elmos-java-migration-production-loop`
18. `elmos-observability-finops`
19. `elmos-backup-recovery-replay`
20. `elmos-progressive-delivery`
21. `elmos-scale-benchmark-certification`
22. `elmos-production-readiness-gate`
