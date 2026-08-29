# Production Readiness Gate

以下任何一项为否，都不能把“所有测试通过”解释为可以正式上线。

## Identity and isolation
- [ ] 所有知识、数据、Skill、模型、Adapter、工具和 Evidence 有内容身份、Owner 和版本。
- [ ] 所有租户作用域表、对象、向量、缓存、Adapter、Checkpoint 和备份完成隔离测试。
- [ ] Environment/Attachment-owned authority 与远程 Workspace fencing 已落地。

## Data and training
- [ ] 数据用途、许可证、训练授权、地域和保留策略在流水线各阶段强制执行。
- [ ] 评测集与训练、检索、缓存、Prompt 完全隔离。
- [ ] 数据撤回可以定位到受影响 Dataset、Checkpoint、Adapter 和 Release。

## Skill and execution
- [ ] 只暴露 Meta-Skill；原子 Skill 经 Registry、签名和兼容过滤后加载。
- [ ] P0 Skill 具有正负触发测试、过程测试、结果测试、红队和回滚演练。
- [ ] 有副作用操作具备幂等、审批、补偿和断电恢复。

## Model and serving
- [ ] Router、Retriever、Reranker、Verifier 与业务 Adapter 均有冻结基线和回归门。
- [ ] 动态 Adapter 只在隔离可信控制面加载，且验证签名和租户归属。
- [ ] 发布组合可整体固定、灰度、回滚和重放。

## Evidence and operations
- [ ] 确定性验证优先，模型裁判经过校准且不能覆盖硬门。
- [ ] 影子、Canary、负载、长稳、故障注入、备份恢复和安全红队已通过。
- [ ] Wall-clock ETA、Token、GPU、工具成本、收入和毛利可准确归因。
- [ ] 具备客户验收包、支持诊断包、审计导出和事件响应 Runbook。

## Final production gate
- [ ] 目标业务线达到至少 E4；对外宣称 Golden Route 的能力达到 E5。
- [ ] 无 Critical 安全问题、无跨租户泄漏、无未解释的行为回归。
- [ ] 风险 Owner 已签署，自动回滚与人工接管均演练成功。
