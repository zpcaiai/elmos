# ELMOS 商业化外部依赖矩阵

生成日期：2026-07-28
用途：把"还差什么"从抽象状态变成一张**可逐项签收的采购/配置清单**。

本文只登记依赖与其当前状态。登记本身**不改变**任何 `NOT_RUN` / `NOT_CONFIGURED` 状态；
状态只能在真实动作发生后由对应的门禁或运行手册更新。

---

## 1. 经营与法务（无代码，日历时间最长，最先启动）

| # | 依赖 | 当前状态 | 阻塞什么 | 预计日历 |
|---|---|---|---|---|
| L1 | 经营主体（公司注册） | `NOT_CONFIGURED`（`sellerLegalEntityStatus`） | 全部收款 | 2–6 周 |
| L2 | 对公银行账户 | 未开始 | 结算 | 1–4 周 |
| L3 | 税务登记与税率认定 | `NOT_CONFIGURED`（`taxStatus`） | 定价目录 `PUBLISHED` | 1–3 周 |
| L4 | 开票能力（发票 / Invoice） | 未实现 | 企业客户付款 | 1–3 周 |
| L5 | 服务条款 / 隐私政策 / DPA / SLA 文本 | 未编写 | 注册页上线 | 1–2 周（需律师） |
| L6 | **ICP 备案** | 未开始 | **域名对外服务（D-01 后为硬前置）** | 2–4 周 |
| L7 | 商标 / 域名 | 未确认 | 品牌与邮件域、ICP 备案 | 1–2 周 |
| L8 | 等保定级备案（视规模与数据类型） | 未评估 | 企业客户采购问卷 | 4–12 周 |

**关键路径（D-01 决定后）：**

```
营业执照 → 对公账户 → 税务登记
              ↘ 域名 + ICP 备案（2–4 周）
              ↘ 支付宝/微信商户审核（2–6 周）
                        ↘ 沙箱全链路 → 目录 PUBLISHED → 真实交易 → 开售
```

日历合计 **8–14 周**。**没有营业执照，这条链一步都启动不了。**

---

## 2. 支付（★ 存在结构性决策）

定价目录 `contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json` 当前：

```
status = DRAFT   currency = CNY   paymentProvider = STRIPE_CHECKOUT
sellerLegalEntityStatus = NOT_CONFIGURED
taxStatus = NOT_CONFIGURED
paymentStatus = NOT_CONFIGURED
costValidationStatus = NOT_RUN
```

**D-01 已决（2026-07-28）：中国大陆主体 + 支付宝/微信支付。**
Stripe 路径不再启用，`STRIPE_CHECKOUT` 与 `currency=CNY` 的组合会被发布门禁指出。
实现规格见 [`PAYMENT_CN_ADAPTER_SPEC.md`](PAYMENT_CN_ADAPTER_SPEC.md)。

| # | 依赖 | 状态 | 说明 |
|---|---|---|---|
| P1 | 支付宝商家号 / 微信支付商户号 | 未申请 | 需 L1+L2 先完成；审核日历 2–6 周 |
| P2 | 支付适配器实现 | **未实现** | 复用既有两阶段状态机，约 3–4 人周 |
| P3 | 签名与回调验签、幂等、对账案件 | 未实现 | 与既有 Stripe 路径等价 |
| P4 | 增值税发票能力 | 未实现 | 电子发票服务商或先走人工，2–3 人周 |
| P5 | 目录 `paymentProvider` 从 const 扩为 enum | 未改 | 影响 8 处，见规格第 5 节 |
| P6 | 沙箱全链路 + 真实小额交易 + 真实退款 | `NOT_RUN` | 开售前硬门槛 |

需要的凭据（均用 `_FILE` 形式，0600，不入版本库）：

```
支付宝：ELMOS_ALIPAY_APP_ID / _PRIVATE_KEY_FILE / _PUBLIC_KEY_FILE
        _GATEWAY_URL / _NOTIFY_URL / _RETURN_URL
微信：  ELMOS_WECHATPAY_MCHID / _APIV3_KEY_FILE / _CERT_SERIAL_NO
        _PRIVATE_KEY_FILE / _PLATFORM_CERT_FILE / _NOTIFY_URL
```

**两个容易漏的点**：

1. **金额单位不一致**——目录是分，支付宝要元（两位小数字符串），微信要分。
   转换必须纯整数运算，禁止浮点。
2. **自动续费要单独签约**。建议首发走「手动续费 + 到期提醒」，与目录已声明的
   `overagePolicy=HARD_STOP_NO_AUTOMATIC_CHARGE` 天然一致，省掉一轮平台审核。

---

## 3. 数据库

| # | 依赖 | 状态 | 配置项 |
|---|---|---|---|
| D1 | 生产 PostgreSQL（Neon 或等价托管 PG 17） | `NOT_RUN` | `ELMOS_COMMERCIAL_DATABASE_URL` |
| D2 | 迁移身份（owner） | 未创建 | `ELMOS_COMMERCIAL_DATABASE_MIGRATION_USERNAME` / `_PASSWORD` |
| D3 | 运行身份（`NOSUPERUSER NOBYPASSRLS` 最小权限） | 未创建 | `ELMOS_COMMERCIAL_DATABASE_USERNAME` / `_PASSWORD` |
| D4 | 目标校验变量 | 未设置 | `ELMOS_COMMERCIAL_DATABASE_EXPECTED_HOST` / `_EXPECTED_DATABASE` / `_RUNTIME_USERNAME` |
| D5 | GitHub `commercial-production` Environment（含审批保护） | 未配置 | 承载 D1–D4 的 Secret/Variable |
| D6 | 备份 / PITR / 恢复演练 | `NOT_RUN`（RISK-DATA-001） | —— |

要求：URL 不得内嵌凭据，必须 `sslmode=require` 或 `verify-full`；迁移身份与运行身份必须分离。
迁移由 `.github/workflows/commercial-billing-neon.yml` 执行
`Flyway validate → migrate → validate`，任何 checksum drift 或目标不匹配都会阻断。

---

## 4. 身份提供方（IdP）

Web Console 侧（`apps/web-console/app/lib/server/accountSession.ts`，授权码流程已实现）：

| # | 依赖 | 状态 | 配置项 |
|---|---|---|---|
| I1 | OIDC 客户端注册（Web） | `NOT_CONFIGURED` | `ELMOS_OIDC_CLIENT_ID` / `ELMOS_OIDC_CLIENT_SECRET` |
| I2 | Issuer | `NOT_CONFIGURED` | `ELMOS_OIDC_ISSUER_URI` |
| I3 | 授权 / 令牌 / UserInfo / JWKS 端点 | `NOT_CONFIGURED` | `ELMOS_OIDC_AUTHORIZATION_ENDPOINT` / `_TOKEN_ENDPOINT` / `_USERINFO_ENDPOINT` / `_JWKS_URI` |
| I4 | 登出与撤销端点 | `NOT_CONFIGURED` | `ELMOS_OIDC_END_SESSION_ENDPOINT` / `_REVOCATION_ENDPOINT` |
| I5 | 回调地址与 Scope | `NOT_CONFIGURED` | `ELMOS_OIDC_REDIRECT_URI` / `ELMOS_OIDC_SCOPES` |
| I6 | 会话密封密钥、公开 Origin | 未生成 | `ELMOS_SESSION_SECRET` / `ELMOS_PUBLIC_ORIGIN` |

Commercial API 侧（Java，变量名与 Web 不同，注意不要混用）：

| # | 依赖 | 状态 | 配置项 |
|---|---|---|---|
| I7 | Issuer / JWK Set / Audience | `NOT_CONFIGURED` | `ELMOS_OIDC_ISSUER_URI` / `ELMOS_OIDC_JWK_SET_URI` / `ELMOS_OIDC_AUDIENCE` |
| I8 | Scope 定义（含 `commercial:billing:admin`） | 未定义 | IdP 侧配置 |
| I9 | 试用身份 pepper（≥32 字节随机） | 未生成 | `ELMOS_TRIAL_IDENTITY_PEPPER` |

**已实现，不必重做**：登录页、授权码流程、`__Host-` 密封 Cookie、JWKS 校验、
令牌刷新与撤销、租户切换（≤32 个成员关系）、同源写保护，以及
6 角色 × 15 权限的 RBAC。

**仍缺**：**组织自服务**。租户成员关系来自 JWT claims，仓库内没有组织创建、
成员邀请、角色分配的实现——新客户组织目前只能手工开通（见评估文档 G2.3）。

---

## 5. 执行面（Runner）

| # | 依赖 | 状态 | 配置项 |
|---|---|---|---|
| R1 | rootless Podman/Docker 主机或集群 | 未部署 | `ELMOS_LOCAL_RUNNER_CONTAINER_ENGINE`（绝对路径） |
| R2 | Runner 专用根目录（不得为文件系统根 / 仓库根 / 仓库祖先） | 未创建 | `ELMOS_LOCAL_RUNNER_ROOT` |
| R3 | 不可变工具链镜像 `name@sha256:<64hex>` | 未构建发布 | `ELMOS_TRANSLATION_RUNNER_IMAGE` |
| R4 | 精确 `uv` 可执行文件 | 依环境 | `ELMOS_UV_PATH` |
| R5 | 作业令牌签发（当前为单 tenant/actor 长期变量，需改造） | 需改造 | `ELMOS_LOCAL_RUNNER_AUTH_TOKEN*` |
| R6 | 产物对象存储 + 按套餐保留期清理（7/30/90 天） | 未部署 | —— |

生产模式只允许 `ELMOS_LOCAL_RUNNER_EXECUTOR=ROOTLESS_CONTAINER`；
`HOST_DEVELOPMENT` 在 `NODE_ENV=production` 下被拒绝。

---

## 6. 通知与支持

| # | 依赖 | 状态 | 配置项 |
|---|---|---|---|
| N0 | 管理员登录安全通知（Resend 固定 API） | `PREPARED_NOT_CONFIGURED` | `ELMOS_ADMIN_LOGIN_NOTIFICATIONS_ENABLED` / `ELMOS_ADMIN_LOGIN_EMAIL_FROM` / `ELMOS_RESEND_API_KEY_FILE`；未获接受回执时管理员登录失败关闭 |
| N1 | 邮件发送服务商（SES / Resend / 阿里云邮推等） | `PREPARED_NOT_CONFIGURED` | `ELMOS_USAGE_EMAIL_ALERTS_ENABLED` |
| N2 | 发件域名与 SPF/DKIM/DMARC | 未配置 | —— |
| N3 | 退订、频控、地址验证、回执、失败重试、隐私评审 | 未完成 | 开启邮件前的硬前置 |
| N4 | 客服工单入口 | 未搭建 | —— |
| N5 | 状态页 | 未搭建 | —— |

---

## 7. 可观测与 SRE

| # | 依赖 | 状态 |
|---|---|---|
| O1 | 指标采集端（Micrometer 已埋点，无采集端） | 未部署 |
| O2 | 告警路由与值班排班 | `NOT_RUN`（RISK-SRE-001） |
| O3 | 日志聚合 / 错误追踪 | 未部署 |
| O4 | SLO 定义与服务信用政策 | 未定义 |
| O5 | 负载 / Soak / 容量 / 故障注入 | `NOT_RUN` |

Actuator metrics **不得**对公网开放（见 `docs/tasks/self-service-billing/OPERATIONS_RUNBOOK.md`）。

---

## 8. 安全与供应链

| # | 依赖 | 状态 |
|---|---|---|
| S1 | 独立安全 / 隐私 / 租户隔离评审 | `NOT_RUN`（RISK-SECURITY-001，critical） |
| S2 | 渗透测试（外部供应商） | 未采购 |
| S3 | 完整传递依赖 SBOM 与签名 | `NOT_RUN` |
| S4 | 生产 Secret 管理（当前为环境变量 / 0600 文件） | 未选型 |
| S5 | 凭据轮换流程 | `NOT_RUN` |

---

## 9. 成本估算（月，最小可运营版，仅供规划）

| 项 | 估算 |
|---|---|
| 托管 PostgreSQL | $25–100 |
| Runner 主机（2 台中等规格） | $80–250 |
| 对象存储 + 出网 | $20–100 |
| Web 托管（Vercel 或等价） | $0–20 |
| IdP（Auth0/Logto 起步档） | $0–70 |
| 邮件服务 | $0–20 |
| 监控 | $0–50 |
| **月度合计** | **$125–610** |
| 一次性：渗透测试 | $3,000–15,000 |
| 一次性：主体注册 + 法务文本 | $1,000–5,000 |

模型推理成本未计入——它随用量线性增长，是 `costValidationStatus` 必须先跑通的原因：
¥129/月对应 2,000 万 token，**毛利是正是负目前未知**。
