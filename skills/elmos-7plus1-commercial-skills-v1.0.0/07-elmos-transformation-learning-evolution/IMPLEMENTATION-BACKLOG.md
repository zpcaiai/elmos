# P07 实施 Backlog

## 使用规则

- 每项任务必须进入 P04 Task DAG，并绑定 owner、依赖、预算、系统 ETA、验收和证据。
- “完成”列由 P05 Gate 更新；人工/Agent 不直接设置。
- 发现新范围时新增任务，不把任务描述无限扩张。

| Task ID | Capability | 阶段 | 任务 | 初始状态 | Done evidence |
| --- | --- | --- | --- | --- | --- |
| P07-T001 | P07-C01 | Contract | 定义 Transformation Knowledge Base 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P07-T002 | P07-C01 | MVP | 实现 Transformation Knowledge Base 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P07-T003 | P07-C01 | Reliability | 为 Transformation Knowledge Base 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P07-T004 | P07-C01 | GA | 完成 Transformation Knowledge Base 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P07-T005 | P07-C02 | Contract | 定义 Project Archetype Knowledge Base 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P07-T006 | P07-C02 | MVP | 实现 Project Archetype Knowledge Base 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P07-T007 | P07-C02 | Reliability | 为 Project Archetype Knowledge Base 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P07-T008 | P07-C02 | GA | 完成 Project Archetype Knowledge Base 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P07-T009 | P07-C03 | Contract | 定义 Failure & Repair Corpus 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P07-T010 | P07-C03 | MVP | 实现 Failure & Repair Corpus 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P07-T011 | P07-C03 | Reliability | 为 Failure & Repair Corpus 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P07-T012 | P07-C03 | GA | 完成 Failure & Repair Corpus 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P07-T013 | P07-C04 | Contract | 定义 Rule Promotion & Governance 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P07-T014 | P07-C04 | MVP | 实现 Rule Promotion & Governance 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P07-T015 | P07-C04 | Reliability | 为 Rule Promotion & Governance 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P07-T016 | P07-C04 | GA | 完成 Rule Promotion & Governance 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P07-T017 | P07-C05 | Contract | 定义 Benchmark Corpus 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P07-T018 | P07-C05 | MVP | 实现 Benchmark Corpus 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P07-T019 | P07-C05 | Reliability | 为 Benchmark Corpus 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P07-T020 | P07-C05 | GA | 完成 Benchmark Corpus 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P07-T021 | P07-C06 | Contract | 定义 Evidence Corpus 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P07-T022 | P07-C06 | MVP | 实现 Evidence Corpus 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P07-T023 | P07-C06 | Reliability | 为 Evidence Corpus 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P07-T024 | P07-C06 | GA | 完成 Evidence Corpus 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P07-T025 | P07-C07 | Contract | 定义 Retrieval & Repair Ranker 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P07-T026 | P07-C07 | MVP | 实现 Retrieval & Repair Ranker 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P07-T027 | P07-C07 | Reliability | 为 Retrieval & Repair Ranker 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P07-T028 | P07-C07 | GA | 完成 Retrieval & Repair Ranker 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P07-T029 | P07-C08 | Contract | 定义 Drift & Regression Detector 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P07-T030 | P07-C08 | MVP | 实现 Drift & Regression Detector 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P07-T031 | P07-C08 | Reliability | 为 Drift & Regression Detector 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P07-T032 | P07-C08 | GA | 完成 Drift & Regression Detector 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P07-T033 | P07-C09 | Contract | 定义 Active Learning Queue 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P07-T034 | P07-C09 | MVP | 实现 Active Learning Queue 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P07-T035 | P07-C09 | Reliability | 为 Active Learning Queue 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P07-T036 | P07-C09 | GA | 完成 Active Learning Queue 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P07-T037 | P07-C10 | Contract | 定义 Specialized Model Pipeline 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P07-T038 | P07-C10 | MVP | 实现 Specialized Model Pipeline 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P07-T039 | P07-C10 | Reliability | 为 Specialized Model Pipeline 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P07-T040 | P07-C10 | GA | 完成 Specialized Model Pipeline 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P07-T041 | P07-C11 | Contract | 定义 Tenant/IP Isolation & Consent 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P07-T042 | P07-C11 | MVP | 实现 Tenant/IP Isolation & Consent 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P07-T043 | P07-C11 | Reliability | 为 Tenant/IP Isolation & Consent 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P07-T044 | P07-C11 | GA | 完成 Tenant/IP Isolation & Consent 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P07-T045 | P07-C12 | Contract | 定义 Knowledge Quality Auditor 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P07-T046 | P07-C12 | MVP | 实现 Knowledge Quality Auditor 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P07-T047 | P07-C12 | Reliability | 为 Knowledge Quality Auditor 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P07-T048 | P07-C12 | GA | 完成 Knowledge Quality Auditor 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |

## 优先级

1. Contract/Schema/Benchmark/Security baseline。
2. 一个真实 Vertical Slice 的端到端证据闭环。
3. 失败恢复、并发、多租户与成本治理。
4. 技术矩阵扩展、性能优化和商业 GA。
