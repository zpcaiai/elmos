# Batch 03 Implementation Checklist

## G0 规格与契约

- [ ] 根目录与逐 Skill 规范均纳入版本控制
- [ ] Schema、状态机、证书和事件契约完成评审
- [ ] Tenant、权限、数据分类和审计边界明确
- [ ] 所有 Non-objective 与禁止性断言进入测试计划

## G1 核心领域模型

- [ ] 实现核心实体、值对象和持久化模型
- [ ] 实现稳定 ID、Digest、Version 与 Provenance
- [ ] 实现 Unknown、Partial、Stale、Conflict 状态
- [ ] 实现 Schema Validation 和兼容性测试

## G2 工作流与幂等

- [ ] 实现状态机、检查点、暂停、恢复与取消
- [ ] 实现稳定 Idempotency Key
- [ ] 实现部分失败隔离和重试上限
- [ ] 实现 Snapshot/Version 变化失效

## G3 Adapter 与执行安全

- [ ] 所有 Adapter 使用最小权限
- [ ] 外部工具、插件或模型在隔离边界运行
- [ ] 网络、文件、Secret 和进程权限显式声明
- [ ] 超时、资源限制和熔断已测试

## G4 验证与证据

- [ ] 高影响结论或变更均有 EvidenceRef
- [ ] Blocking Gate 无法判定时不得自动通过
- [ ] 验证器与生成器保持独立
- [ ] Waiver 有批准者、理由、范围和有效期

## G5 UI、API 与运维

- [ ] API/事件契约可查询并可审计
- [ ] Console 显示覆盖率分母、Unknown 和限制
- [ ] OpenTelemetry Trace、Metrics、Logs 可关联
- [ ] Runbook、备份、恢复与撤销流程完成

## G6 认证与发布

- [ ] 综合场景全部运行并保存证据
- [ ] 安全、性能、幂等和回滚测试通过
- [ ] 证书范围与实际验证等级一致
- [ ] 未实现范围未被隐藏，发布状态准确

## Batch 专项检查

- [ ] Round Trip、Encoding 和 Comment Preservation 已测试。
- [ ] 多 Build Context 不会共享错误语义。
- [ ] Unknown、Any、Dynamic 和 Opaque 明确区分。
- [ ] 异常、资源清理、并发和事务进入分析图。
- [ ] Proof Obligation 不会被描述为已完成证明。

## 发布签字

```yaml
release:
  engineering: pending
  security: pending
  architecture: pending
  product: pending
  audit: pending
```
