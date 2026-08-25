# Commercial GA Checklist

## 产品与合同

- [ ] 7+1 包公共 API/SPI/Schema 冻结并有兼容策略
- [ ] 客户场景、非目标、支持矩阵和认证等级清晰
- [ ] 所有目标指标区分 target/observed/certified

## 结果质量

- [ ] Requirement/Capability Ledger 可审计
- [ ] Critical unknown gap=0
- [ ] 差分/E2E/非功能 Gate 通过
- [ ] 假完成红队通过

## 运行可靠性

- [ ] Session/Task 可恢复
- [ ] 副作用幂等与补偿
- [ ] Adapter conformance
- [ ] 多租户并发与公平调度
- [ ] 容量与降级演练

## 安全与隐私

- [ ] SSO/RBAC/SCIM（适用）
- [ ] 凭据 Broker 与 child env scrub
- [ ] sandbox/permission/approval fail closed
- [ ] ZDR/BYOK/区域/数据保留
- [ ] 供应链/SBOM/Secret/漏洞 Gate

## 商业运营

- [ ] 成本/收入/账单可对账
- [ ] 系统机器 ETA 与实际持续校准
- [ ] 套餐/quota/overage/支持等级
- [ ] SLA/错误预算/客户 Dashboard

## 部署与灾备

- [ ] 私有云/本地/托管拓扑
- [ ] 备份/恢复/多区/灾难演练
- [ ] 升级/回滚/数据迁移
- [ ] kill switch 与 last-known-good

## 知识治理

- [ ] 默认 tenant-private
- [ ] scope/consent/删除
- [ ] 规则晋升与降级
- [ ] Benchmark holdout 与数据泄漏防护

## 支持与审计

- [ ] Runbook/On-call/Incident
- [ ] 客户证据报告
- [ ] 审计导出与 WORM 选项
- [ ] 许可证与第三方 NOTICE 审核

## GA 判定

所有 Critical 项完成，P05 E4/E5 Gate 通过，canary 与 rollback 演练成功，残余风险有正式 owner 与客户可见说明。
