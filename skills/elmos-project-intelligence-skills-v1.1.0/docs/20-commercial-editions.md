# 商业版本与能力包装

## 1. 建议版本

| 能力 | Community | Professional | Enterprise | Private/Offline |
|---|---|---|---|---|
| 公共/本地项目阅读 | 基础 | 完整 | 完整 | 完整 |
| 私有仓库 | 本地 | SaaS | SaaS/专属 | 内网 |
| 代码/符号图 | 基础 | 完整 | 完整 | 完整 |
| 架构/流程/数据图 | 限量 | 完整 | 完整 | 完整 |
| 文档/PPT | 模板有限 | 完整 | 品牌/审批 | 私有模板 |
| Artifact 锁定 | 基础 | 完整 | 完整 | 完整 |
| Q&A/Impact | 基础额度 | 完整 | 企业额度 | 私有模型 |
| Runtime Trace | 无/本地 | 可选 | 完整 | 内网 |
| 在线调试 | 本地单会话 | P0 Runtime/限额 | 多用户/学习/回放 | 私有 Runtime Pool |
| 分布式与 Source/Target 调试 | 无 | 可选 | 完整 | 内网完整 |
| 架构规则/漂移 | 基础 | 完整 | 企业策略 | 完整 |
| SSO/SCIM/RBAC | 无 | 团队 RBAC | 完整 | 完整 |
| 审计/驻留 | 基础 | 标准 | 企业 | 客户控制 |
| Elmos 转换集成 | 试用 | 完整 | 完整 | 完整 |
| E4/E5 认证 | 无 | E3 | E4 | E4/E5 |
| 支持 | 社区 | 标准 | SLA | 专属 |

## 2. 计量维度

- 活跃项目；
- Frozen revisions；
- 被分析 LOC/文件；
- Analysis run；
- 模型 input/output/cached Token；
- Diagram/Document/PPT generation；
- Runtime Trace GB；
- Debug workspace 分钟、CPU/内存层级、adapter runtime、并发会话；
- Replay/Checkpoint 存储与保留期；
- Learning Mission/Lab 生成与团队席位；
- 并发任务；
- Artifact 存储和保留期；
- 私有 worker/model；
- E4/E5 认证。

## 3. 商业正确性边界

以下能力不能为了收费而关闭：

- Confirmed claim 必须有证据；
- 租户隔离；
- 权限检查；
- Secret/Prompt Injection 基本防护；
- 人工锁定不被静默覆盖；
- 计量幂等和可对账；
- 失败状态与实际一致。

## 4. 商业闭环

```text
免费/试用导入
→ 项目概览和风险发现
→ 团队代码阅读/架构协作
→ 文档/PPT/尽调交付
→ 影响分析/架构治理
→ Elmos 转换与翻新
→ 私有化/认证/持续订阅
```
