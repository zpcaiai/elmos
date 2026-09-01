# 用户操作日志、自动诊断与生产运营管理端

## 双层操作记录

Web 根布局的隐私安全采集器记录页面访问、显式标注 `data-operation-id` 的语义
操作、同源 API 成败/耗时、浏览器错误和页面加载/FCP。它不采集字段变更、输入值
或通用点击。采集器使用 20 条批次、2 秒刷新和 200 条有界重试队列；用户可以关闭
并清空尚未发送的匿名性能数据。

浏览器开关不影响安全审计。Web BFF 的 `withBusinessAudit` 在项目生成、语言翻译
和 Spring 迁移的有副作用入口执行前追加 `BUSINESS_ATTEMPT`，并在返回后追加
`BUSINESS_OPERATION`；control-plane 拦截器对全部 `/api/v1/**` 与
`/api/webhooks/**` 记录执行前事件和完成结果/耗时。它们只保存稳定路由模板，
不保存资源 ID 或查询字符串。生产前置审计失败时业务失败关闭；若副作用已经完成
但完成日志失败，响应明确返回 `operationMayHaveCompleted=true`，禁止盲目重试。

## 数据生命周期与隐私

V51 将产品性能遥测写入强制 RLS 的 `product_telemetry_events`。V9/V50 的
`audit_events` 继续作为不可 UPDATE/DELETE 的安全与业务审计链。两者在管理查询
中形成统一只读视图，但生命周期严格分离：

- 产品遥测可由获批的 7–365 天保留任务清理；
- 清理前按业务线记录数量和首末时间聚合；
- 执行人、请求、cutoff、删除数和聚合证据写入追加式保留运行记录；
- 保留任务永不删除 `audit_events`。

允许内容限于随机事件 ID、HMAC 会话、稳定动作/业务线/路由/控件类型、发生时间、
耗时、结果、稳定错误码、allow-list 性能指标和最多 8 个短技术维度。严禁输入值、
项目/仓库/提示词内容、请求/响应体、Bearer/API Token、Cookie、查询参数、
错误原文/堆栈、原始 IP/User-Agent 和自由文本。

详细数据流、威胁与控制见 `telemetry/DATA_FLOW_AND_THREAT_MODEL.md`；版本化策略、
Schema 和指标分别见 `telemetry/policy.json`、`events.schema.json` 与
`metric-definitions.json`。

## 管理端与 RBAC

`/admin` 查询 1 小时、24 小时、7 天或 30 天的事件量、活跃会话、失败率、P95、
所有业务线、高频错误和最近操作，并管理 18 条业务线 SLO、告警、事件、负责人、
通知 outbox、快修提案、保留运行及外部证据状态。

管理端只接受已验证邮箱精确等于 `zpchoney@gmail.com` 的企业 OIDC 会话，并将
所选租户和真实 Actor 传给 control-plane。其他邮箱携带的管理角色会在服务端被
移除，浏览器也不接受共享 Bearer 管理令牌。所有状态变更要求 `expectedVersion`；陈旧/
并发写入返回 409。审批和执行者权限分离，未配置或过期凭证、身份绑定不一致、
权限不足或 control-plane 不可用均明确失败，不以空数据伪装健康。

## 自动性能优化与 Bug 快修边界

周期或人工 SLO 评估按每条业务线 15 分钟窗口计算失败率基点和 P95。达到最小事件
数且越界时，系统使用稳定指纹幂等创建/更新：

1. 带负责人、runbook、严重级别和预算差异的告警；
2. 与告警一一对应、可接手/解决的事件；
3. 通知 outbox（目的地未配置时为 `CONFIGURATION_REQUIRED`）；
4. `STABLE_ERROR_DIAGNOSTIC_V1` 或 `LATENCY_BUDGET_DIAGNOSTIC_V1` 提案。

提案绑定前置条件 SHA-256、预期诊断变化、必跑测试、补丁预览和回滚计划。系统
自动完成检测、诊断和提案，但不自行修改源码、测试、安全边界、事务、金额、Schema、
公开 API 或部署。`APPROVER` 批准后只能生成摘要绑定的 `READY_FOR_SCM` 计划；
真实补丁、测试、PR、部署、验证和回滚必须由相应授权系统执行并回填证据。
计划状态不得解释为 Bug 已修复或生产已发布。

快修版本化 Profile 与 recipe 清单见 `quick-fix/profile.json` 和
`quick-fix/registry.json`。

## 运行配置

Web 与 control-plane 共享：

- `ELMOS_OPERATIONS_API_KEY`：至少 24 字符的内部服务租约；
- `ELMOS_OPERATIONS_API_KEY_EXPIRES_AT`：未来且不超过 24 小时；
- `ELMOS_OPERATIONS_TENANT_ID`、`ELMOS_OPERATIONS_ACTOR_ID`：可信绑定；
- `ELMOS_CONTROL_PLANE_BASE_URL`：内部 control-plane 地址；
- `ELMOS_BUSINESS_AUDIT_REQUIRED`：本地/测试可显式设为 `true` 验证失败关闭；
  生产无论该变量取值如何都强制要求业务审计。

管理端：

- 企业 OIDC 配置与会话密钥见账户登录文档/对应 `ELMOS_OIDC_*`、
  `ELMOS_SESSION_SECRET` 环境；
- `ELMOS_ADMIN_LOGIN_NOTIFICATIONS_ENABLED=true`；
- `ELMOS_ADMIN_LOGIN_EMAIL_FROM`；
- `ELMOS_RESEND_API_KEY_FILE`（推荐）或 `ELMOS_RESEND_API_KEY`，二选一。

自动化与保留：

- `ELMOS_OPERATIONS_AUTOMATION_ENABLED`，默认 `false`；
- `ELMOS_OPERATIONS_EVALUATION_INTERVAL_MS`，默认 300000；
- `ELMOS_OPERATIONS_RETENTION_ENABLED`，默认 `false`；
- `ELMOS_OPERATIONS_RETENTION_DAYS`，默认 30，范围 7–365；
- `ELMOS_OPERATIONS_RETENTION_INTERVAL_MS`，默认 86400000。

生产部署、轮换和验收步骤见 `docs/PRODUCTION_OPERATIONS_ADMIN.md`。

## 证据边界

仓库实现和本地测试能证明 Schema、RLS、状态机、版本冲突、隐私过滤、双存储、
SLO 计算和界面契约；不能证明真实外部告警已收到、值班人员已响应、真实 SCM
改动/测试/部署已完成、生产容量与成本达标、隐私评审通过或故障演练完成。这些项
在真实授权环境产生证据前保持 `NOT_RUN`。
