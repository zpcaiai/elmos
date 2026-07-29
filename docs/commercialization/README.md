# ELMOS 商业化文档集

生成日期：2026-07-28 · 对应仓库 HEAD `23fd7fa6`

本目录回答一个问题：**这个项目要商业化运营，还差多少工作量。**

本目录的所有文档都是**规划与清单**，不是执行记录。它们不产生任何证据，
不改变仓库中任何 `NOT_RUN` / `NOT_CONFIGURED` / `BLOCKED` 状态。
`docs/BUSINESS_LINE_CLOSURE_MATRIX.md` 末节的失败关闭规则继续适用。

| 文档 | 回答什么 |
|---|---|
| [COMMERCIALIZATION_GAP_ASSESSMENT.md](COMMERCIALIZATION_GAP_ASSESSMENT.md) | 缺口在哪、多少人周、什么顺序 |
| [EXTERNAL_DEPENDENCIES.md](EXTERNAL_DEPENDENCIES.md) | 需要哪些外部账户、凭据、资质，各自阻塞什么 |
| [MINIMUM_COMMERCIAL_TOPOLOGY.md](MINIMUM_COMMERCIAL_TOPOLOGY.md) | 24 个服务里第一版实际要部署哪几个 |
| [GO_LIVE_RUNBOOK.md](GO_LIVE_RUNBOOK.md) | 从今天到开售的逐步执行清单 |
| [DECISIONS.md](DECISIONS.md) | 工程无法代决、必须由人拍板的 6 件事（D-01/D-03 已决） |
| [CAPABILITY_SUPPORT_MATRIX.md](CAPABILITY_SUPPORT_MATRIX.md) | 对外能力口径，销售材料唯一依据 |
| [PAYMENT_CN_ADAPTER_SPEC.md](PAYMENT_CN_ADAPTER_SPEC.md) | 支付宝/微信适配器实现规格（D-01 后必做） |
| [RUNNER_AGENT_SPEC.md](RUNNER_AGENT_SPEC.md) | Runner Agent 实现规格（D-03 后必做） |
| `deploy/production/` | 生产编排、Runner 基线、告警规则、恢复演练、环境变量模板 |

## 三十秒版本

- 代码侧能卖的东西基本齐了。卡点是**没有托管执行面、没有生产部署与 SRE、没有收款主体**。
- 身份链路是好消息：OIDC 授权码流程、会话、6 角色 × 15 权限 RBAC **已实现**，
  只差配置 IdP 和组织自服务。
- **2026-07-28 已决**：D-01 中国大陆主体 + 支付宝/微信；D-03 SaaS 多租户托管。
  这两个选择同时去掉了两条捷径（Stripe 零改动、先单租户跑起来），工作量因此上修。
- 最小可运营版（只卖 `/generation`）：**24–32 人周**，日历 14–20 周。
- 完整商业化运营：**36–52 人周**，日历 6–9 个月。
- 关键路径不在代码里：营业执照 → 对公账户 → ICP 备案（2–4 周）
  ‖ 支付商户审核（2–6 周）→ 目录 `PUBLISHED` → 开售，日历 **8–14 周**。
  **没有营业执照，这条链一步都启动不了。**
- 三条 `critical` 风险（生产身份、备份恢复、独立安全评审）未闭合前，
  不应对付费客户承诺 SLA。多租户 SaaS 让"独立安全评审"从加分项变成必需项。
