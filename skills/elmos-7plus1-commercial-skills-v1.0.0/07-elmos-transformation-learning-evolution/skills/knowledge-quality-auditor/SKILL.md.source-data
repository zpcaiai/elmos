---
name: elmos-knowledge-quality-auditor
description: 检查重复、冲突、过期、毒化、证据缺失、覆盖盲区和异常推广。
license: Proprietary
compatibility: Elmos 7+1 package contracts v1.0.0
metadata:
  parent_package: P07
  version: 1.0.0
  maturity: commercial-product-blueprint
---

# 知识质量审计

## 目标

检查重复、冲突、过期、毒化、证据缺失、覆盖盲区和异常推广。

## 调用条件

- P07 主 Skill 或上游 Task DAG 指定该能力。
- 输入绑定 immutable revision、tenant/project policy 和验收标准。
- 所有依赖 Schema/服务 readiness 通过。

## 输入

- task/workflow contract 与关联 requirement/capability IDs。
- source/target/config/policy/model/tool/environment revisions。
- 权限、预算、系统 ETA、数据分类、允许的副作用和 evidence policy。

## 步骤

1. 扫描条目与 evidence graph
2. 识别冲突/重复/stale
3. 检测异常成功率和来源
4. 隔离可疑知识
5. 创建修复/回归任务
6. 发布健康报告

## 产出

- knowledge health report

每个产出必须携带 provenance、revision、correlation id、状态和 evidence refs。

## 完成门

- [ ] Critical 可疑知识立即 quarantine
- [ ] 审计结果可追溯

- [ ] 输出通过本包和根目录共享 Schema。
- [ ] 定向测试与影响闭包回归通过。
- [ ] P05 Gate 接受证据，或返回明确 blocker/failure。

## 失败与恢复

- 输入不完整：生成 blocker 与所需证据，不猜测关键事实。
- 验证失败：保留失败证据，创建最小修复任务并重跑影响闭包。
- 权限/隐私/沙箱不满足：fail closed，不改用更宽 Provider/权限。

## 安全

- 使用 P01 action×resource 权限、审批与沙箱；不直接持有长期凭据。
- 不把租户私有资产写入全局知识；P07 沉淀前必须 scope/consent/evidence 检查。
- 不以降低验收标准、删除测试或隐藏 gap 的方式获得 pass。
