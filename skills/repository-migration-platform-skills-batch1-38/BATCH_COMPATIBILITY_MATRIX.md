# Batch Compatibility Matrix

| Batch | Required predecessors | Primary output | Gate |
|---:|---|---|---|
| 01 | — | Migration Constitution与Source Executable Specification artifacts | B01 Source Baseline Gate |
| 02 | 1 | Differential Execution Harness与Deterministic Environment artifacts | B02 Differential Gate |
| 03 | 1, 2 | 10-Language Semantic Frontend与Unified Semantic IR artifacts | B03 Semantic Frontend Gate |
| 04 | 3 | 90 Directional Semantic Rule、Mutation、Test与Certification Packs artifacts | DP1–DP5 |
| 05 | 3, 4 | Framework Adapter与Framework Combination Matrix artifacts | FA1–FA5 |
| 06 | 1, 3, 4, 5 | Dependency、Native、License与Supply-Chain Graph artifacts | DA/DR Certification |
| 07 | 3, 4, 5, 6 | Database、Cache、Search、Object Storage与Messaging Migration artifacts | DI1–DI5 |
| 08 | 3, 4, 5, 6, 7 | API、RPC、Serialization、Schema、Gateway与Service Mesh Migration artifacts | CI1–CI5 |
| 09 | 2, 3, 4, 5, 6 | Concurrency、Async、Memory、Lifetime与Native Semantics artifacts | CM1–CM5 |
| 10 | 2, 3, 4, 5, 6, 7, 8, 9 | Test Generation、Mutation、Fuzz、Property、Concurrency与Fault Platform artifacts | TQ1–TQ5 |
| 11 | 7, 8, 9, 10 | Domain Packs与Full-Stack Journey Verification artifacts | DV1–DV5 |
| 12 | 7, 8, 9, 10, 11 | Shadow、Strangler、Canary、Rollback与E1–E5 artifacts | E1–E5 |
| 13 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 | Evidence Graph、独立裁判、红队与持续认证 artifacts | EA1–EA5 |
| 14 | 3, 4, 7, 8, 9, 10, 11, 13 | Formal Verification与Proof-Carrying Migration artifacts | F1–F5 |
| 15 | 10, 13, 14 | Counterexample-Guided Repair与自演进验证 artifacts | CR1–CR5 |
| 16 | 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 | Target Architecture Search与Migration Planning artifacts | AP1–AP5 |
| 17 | 12, 13, 14, 15, 16 | Migration Execution OS artifacts | MX1–MX5 |
| 18 | 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17 | Complete Project Generation Standard artifacts | CP1–CP5 |
| 19 | 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 17, 18 | 90路径Executable Generator Packs artifacts | GP1–GP5 |
| 20 | 13, 17, 18, 19 | Skill SDK、Runtime、Registry与产品化封装 artifacts | SC1–SC5 |
| 21 | 1, 11, 18 | System Capability Closure Registry artifacts | Capability Closure Gate |
| 22 | 11, 21 | Business-Line Functional Closure Packs artifacts | Business-Line Closure Gate |
| 23 | 22, 7, 8, 10, 11 | Cross-Business Journey、Saga与逻辑闭环 artifacts | Cross-Business Journey Gate |
| 24 | 7, 8, 11, 21 | End-to-End Data Flow、Lineage与Completeness artifacts | Data Flow Closure Gate |
| 25 | 24, 7, 11, 13, 15 | Data Quality、Reconciliation与Accounting Integrity artifacts | Data Integrity Gate |
| 26 | 21, 22, 23, 27 | Management Console与Control Plane Functional Closure artifacts | Admin Closure Gate |
| 27 | 8, 13, 20, 21, 26 | Identity、Authorization、Approval与Audit Closure artifacts | Identity & Authorization Gate |
| 28 | 21, 22, 23, 26, 27 | Functional Usability与Operational Usability artifacts | Usability Closure Gate |
| 29 | 10, 13, 15, 18, 21, 22, 23, 24, 25, 26, 27, 28 | System-Wide Regression与Change Impact Assurance artifacts | System Regression Gate |
| 30 | 7, 8, 12, 17, 18, 29 | High Availability、Resilience与Disaster Recovery artifacts | Resilience & DR Gate |
| 31 | 7, 9, 10, 14, 15, 29, 30 | Concurrency、Idempotency与Transaction Correctness artifacts | Concurrency & Transaction Gate |
| 32 | 9, 10, 12, 16, 18, 29, 30, 31 | Performance、Capacity、Scalability与Cost Assurance artifacts | Performance & Capacity Gate |
| 33 | 12, 13, 17, 20, 24, 25, 27, 29 | Migration Security与Data Protection Assurance artifacts | Migration Security Gate |
| 34 | 7, 8, 10, 11, 12, 23, 25, 29, 30, 32, 33 | External Integration与Provider Reliability Closure artifacts | Provider Reliability Gate |
| 35 | 18, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34 | Release、Go-Live与Production Acceptance artifacts | Production Acceptance Gate |
| 36 | 30, 32, 34, 35 | Production Operations、Support与Service Management artifacts | Production Operations Gate |
| 37 | 12, 24, 25, 29, 30, 34, 35, 36 | Post-Migration Stabilization与Source Retirement Closure artifacts | Source Retirement Gate |
| 38 | 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37 | Final System Assurance与SA1–SA5 Certification artifacts | SA1–SA5 |
