# ELMOS 商业化上线执行手册

生成日期：2026-07-28
适用范围：第一版商业化上线（首发范围见 `MINIMUM_COMMERCIAL_TOPOLOGY.md` 第 2 节）

**本手册是待执行的步骤清单，不是执行记录。** 每一步的"完成"只在真实动作发生后由执行人
签收，并写入对应的证据文件。任何步骤未执行时，其状态保持 `NOT_RUN`，不得由本手册的存在
推断为已完成。仓库的失败关闭规则（`docs/BUSINESS_LINE_CLOSURE_MATRIX.md` 末节）继续适用。

图例：`[ ]` 待执行　`[!]` 需要外部方（律师/银行/供应商/独立评审）　`[$]` 需要预算

---

## 阶段 0 —— 立即启动（日历最长，与工程并行）

- `[x]` **0.1 决定经营主体与收款通道** —— **已决 2026-07-28：中国大陆主体 +
  支付宝/微信支付**（D-01）。交付形态已决为 **SaaS 多租户托管**（D-03）。
  记录见 `docs/commercialization/DECISIONS.md`。
- `[!]` **0.2 启动营业执照注册与对公账户开立** —— **关键路径起点，不做则后面全部阻塞**
- `[!]` **0.3 税务登记与税率认定**，`taxPresentation` 定为 `TAX_INCLUSIVE`
      （大陆 B2C 标价含税；需财务确认后写入目录）
- `[!]` **0.3b 购买域名并启动 ICP 备案**（2–4 周；备案需主体，域名可先买）
- `[ ]` **0.3c 选定境内云厂商**（阿里云 / 腾讯云 / 华为云）——
      大陆经营要求服务器落境内，境外托管不可用
- `[!][$]` **0.4 委托律师起草**服务条款、隐私政策、DPA、SLA
- `[ ]` **0.5 单位经济性核算**
  - 目标：把 `costValidationStatus` 从 `NOT_RUN` 变为有真实数据支撑
  - 输入：模型推理、Runner 机时、存储、出网、人工支持的实际单价
  - 判定：¥129/月 ÷ 2,000 万 token + 600 Credit 的**贡献毛利是否为正**
  - 若为负：先调价或调额度，**不要带着未知毛利上线**
- `[ ]` **0.6 对外能力声明收敛**
  - 按 A/B/C 档重写官网与文档的能力表述
  - 删除或降级所有基于 `NOT_RUN` Skill 的宣传（含"1,824 个 Skill""20 个引擎"类表述）

---

## 阶段 1 —— 身份与账号

> 登录链路已实现：`apps/web-console/app/lib/server/accountSession.ts` 已包含完整 OIDC 授权码
> 流程、`__Host-` 密封 Cookie、JWKS 校验、令牌刷新/撤销、租户切换和 6 角色 × 15 权限 RBAC。
> 本阶段主要是**配置**，不是重写。

- `[ ]` **1.1 选定 IdP** 并创建生产租户
- `[ ]` **1.2 注册 Web 客户端并配置 OIDC**（Web Console 侧，12 项）：
  ```
  ELMOS_OIDC_CLIENT_ID=            ELMOS_OIDC_CLIENT_SECRET=
  ELMOS_OIDC_ISSUER_URI=           ELMOS_OIDC_JWKS_URI=
  ELMOS_OIDC_AUTHORIZATION_ENDPOINT=  ELMOS_OIDC_TOKEN_ENDPOINT=
  ELMOS_OIDC_USERINFO_ENDPOINT=    ELMOS_OIDC_END_SESSION_ENDPOINT=
  ELMOS_OIDC_REVOCATION_ENDPOINT=  ELMOS_OIDC_REDIRECT_URI=
  ELMOS_OIDC_SCOPES=               ELMOS_PUBLIC_ORIGIN=
  ELMOS_SESSION_SECRET=            # openssl rand -base64 48
  ```
- `[ ]` **1.2b 配置 Commercial API 侧 OIDC**（变量名不同，勿混用）：
  ```
  ELMOS_OIDC_ISSUER_URI=  ELMOS_OIDC_JWK_SET_URI=  ELMOS_OIDC_AUDIENCE=
  ```
- `[ ]` **1.3 定义 scope 与角色 claim**，至少包含 `commercial:billing:admin`，
      并确认 IdP 能下发租户成员关系 claim（≤32 个）
- `[ ]` **1.4 生成试用 pepper**（≥32 字节随机，不入版本库）
  ```bash
  openssl rand -base64 48   # 写入 ELMOS_TRIAL_IDENTITY_PEPPER
  ```
- `[ ]` **1.5 跑通登录回归**：`pnpm exec playwright test e2e/account-session-ui.spec.ts`
- `[ ]` **1.6 实现组织自服务**：注册后建组织、成员邀请、角色分配、组织切换 UI
      —— **当前仓库无对应实现，新客户组织只能手工开通**
- `[ ]` **1.7 移除单租户假设**：`ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID`
      当前把 Spring 代理绑死到一个组织，多租户上线前必须改造
- `[ ]` **1.8 定义"已验证组织"**：`trialEligibilityPolicy=ONE_PER_VERIFIED_ORGANIZATION`
      需要一个可执行的验证判据（邮箱域？实名？支付方式预授权？），否则试用会被批量薅

---

## 阶段 2 —— 生产数据库

- `[ ]` **2.1 创建生产 PostgreSQL 17 实例**（Neon 或等价托管），确认支持 PITR
- `[ ]` **2.2 创建迁移身份（owner）与运行身份**
  - 运行身份必须 `NOSUPERUSER NOBYPASSRLS`，且**不得复用**迁移 owner
  - 参考 `scripts/commercial/configure_billing_runtime_role.sh`
- `[ ]` **2.3 配置 GitHub `commercial-production` Environment**，开启审批保护
  | 类型 | 名称 |
  |---|---|
  | Secret | `ELMOS_COMMERCIAL_DATABASE_URL` |
  | Secret | `ELMOS_COMMERCIAL_DATABASE_MIGRATION_USERNAME` |
  | Secret | `ELMOS_COMMERCIAL_DATABASE_MIGRATION_PASSWORD` |
  | Variable | `ELMOS_COMMERCIAL_DATABASE_EXPECTED_HOST` |
  | Variable | `ELMOS_COMMERCIAL_DATABASE_EXPECTED_DATABASE` |
  | Variable | `ELMOS_COMMERCIAL_DATABASE_RUNTIME_USERNAME` |
  - URL 不得内嵌凭据，必须 `sslmode=require` 或 `verify-full`
- `[ ]` **2.4 执行迁移**：触发 `.github/workflows/commercial-billing-neon.yml`
      （`Flyway validate → migrate → validate`）
  - 空库且托管环境只允许 psql 时，可一次性使用
    `scripts/commercial/bootstrap_empty_neon_via_psql.py`
    （需 `ELMOS_COMMERCIAL_DATABASE_EMPTY_BOOTSTRAP_CONFIRMED=true`，且该通道**拒绝非空库**）
- `[ ]` **2.5 验证** V1–V50 全部应用、checksum 一致、RLS 生效
- `[ ]` **2.6 跨租户负向验证**：用运行身份尝试读取他租户数据，必须失败

---

## 阶段 3 —— 执行面（Runner）

- `[ ]` **3.1 准备 Runner 主机**，与应用主机网络隔离
- `[ ]` **3.2 安装 rootless podman/docker**，记录绝对路径
- `[ ]` **3.3 创建 Runner 专用根目录**
      （不得为文件系统根、仓库根或仓库祖先目录）
- `[ ]` **3.4 构建并发布不可变工具链镜像**，按 `name@sha256:<64hex>` 固定
- `[ ]` **3.5 配置生产执行器**
  ```
  ELMOS_LOCAL_RUNNER_ENABLED=true
  ELMOS_LOCAL_RUNNER_EXECUTOR=ROOTLESS_CONTAINER   # 生产唯一允许值
  ELMOS_LOCAL_RUNNER_ROOT=/srv/elmos/runner
  ELMOS_LOCAL_RUNNER_CONTAINER_ENGINE=/usr/bin/podman
  ELMOS_UV_PATH=/usr/local/bin/uv
  ELMOS_REPOSITORY_ROOT=/srv/elmos/repo
  ```
- `[ ]` **3.6 令牌模型改造**（阻塞多租户）
  - 现状：`ELMOS_LOCAL_RUNNER_AUTH_TOKEN` + `_TENANT_ID` + `_ACTOR_ID` + `_EXPIRES_AT`
    把令牌**唯一绑定到一个租户和一个 actor**，有效期 ≤ 24 小时
  - 目标：由服务端按作业签发短期令牌，租户/actor 从认证身份派生
  - **此项未完成前，产品只能服务单个组织**
- `[ ]` **3.7 隔离断言**：非 root、只读根、删除全部 capability、`no-new-privileges`、
      默认拒绝网络、CPU/内存/PID 限额 —— 逐项产出真实证据
- `[ ]` **3.8 产物保留期实现**：按套餐 7 / 30 / 90 天自动清理
- `[ ]` **3.9 备份与静默期**：确认 `scripts/operations/generation_runner_backup.py quiesce`
      在生产流程中被正确调用（备份前必须阻断新写入并排空活动任务）

---

## 阶段 4 —— 部署

- `[ ]` **4.1 确定拓扑**（见 `MINIMUM_COMMERCIAL_TOPOLOGY.md`），Tier 1 六个服务 + Runner 池
- `[ ]` **4.2 建立 staging 环境**，与生产同拓扑不同规模
- `[ ]` **4.3 编写生产部署编排**（K8s manifests/Helm 或 systemd+compose）
- `[ ]` **4.4 配置反向代理 / TLS / 域名**
- `[ ]` **4.5 Web Console 部署**：Vercel Root Directory 保持 `apps/web-console`
- `[ ]` **4.6 健康检查**
  ```
  /api/health?probe=liveness
  /api/health?probe=readiness
  ```
- `[ ]` **4.7 升级 / 回滚 / 混版演练**（在 staging 执行，关闭 RISK-DEPLOY-001）
- `[ ]` **4.8 确认 Actuator metrics 不对公网开放**

---

## 阶段 5 —— 支付接入（依赖阶段 0 完成）

> **D-01 已决：走支付宝/微信。** 实现细节见
> `docs/commercialization/PAYMENT_CN_ADAPTER_SPEC.md`。
> Stripe 路径的代码保留但不启用，相关环境变量保持为空。

- `[ ]` **5.1 申请商户号**（支付宝商家 / 微信支付商户）——需营业执照 + 对公账户，
      审核 2–6 周。首发建议**先接一家**，另一家二期
- `[ ]` **5.2 扩展 `paymentProvider` 从 const 到 enum** —— 8 处同批次改完
      （Schema、目录、Java 常量、`PricingPlanCatalogTest`、`pricingCatalog.ts`、
      `BillingActions.tsx`、`checkout/route.ts`；发布门禁脚本**已支持**）
- `[ ]` **5.3 实现支付适配器**：复用 `SelfServiceBillingPort` 两阶段状态机、
      幂等、对账案件；只替换"调用提供方"与"验签"两段
- `[ ]` **5.4 金额单位转换**：目录是分，支付宝要元（两位小数字符串），微信要分。
      **纯整数运算，禁止浮点**；边界值 0 / 1 / 99 / 100 / 12900 / 129000 要有单元测试
- `[ ]` **5.5 配置回调地址**（必须是**已备案域名**下的 HTTPS 地址）
- `[ ]` **5.6 沙箱全链路**：下单 → 支付 → 回调 → 订阅生效 → 额度可用 → 退款 → 对账
- `[ ]` **5.7 负向验证**：伪造签名被拒且不创建订阅、回调重放只生效一次、
      金额被篡改被拒、提供方超时进对账且不自动重试
- `[ ]` **5.8 发票能力**：电子发票服务商或先走人工开票流程
- `[ ]` **5.9 生产模式小额真实交易 + 一次真实退款**
- `[ ]` **5.10 续费方式确认**：首发建议「手动续费 + 到期提醒」，
      与 `overagePolicy=HARD_STOP_NO_AUTOMATIC_CHARGE` 一致，省一轮平台审核；
      要做自动续费需单独签约周期扣款（+2–3 人周，日历不可控）

### 共同

- `[ ]` **5.11 目录转正**：在主体/税务/支付/成本四项全部完成后，把
      `contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json` 的
      `status` 由 `DRAFT` 改为 `PUBLISHED`，并同步
      `sellerLegalEntityStatus` / `taxStatus` / `paymentStatus` / `costValidationStatus`
      与 `taxPresentation=TAX_INCLUSIVE`、`paymentProvider`
  - 用门禁确认，而不是靠人眼：
    ```bash
    python3 scripts/commercial/validate_pricing_catalog_publication.py \
      --check-publishable \
      --commercial-evidence <含 icpFiling 与 invoiceCapability 的证据文件>
    ```
    期望 `DECISION=READY_TO_PUBLISH`，退出码 0。任何 `PUBLICATION_BLOCKED` 都不得手工绕过
  - **在此之前付费按钮保持禁用属于预期行为**

---

## 阶段 6 —— 可观测与运维

- `[ ]` **6.1 部署指标采集**（Micrometer 已埋点，需采集端）
- `[ ]` **6.2 配置告警**，最少覆盖运行手册已列的四个计费指标：
  | 指标 | 告警条件 |
  |---|---|
  | `elmos.billing.usage.reservations` | `denied` 比例突增 |
  | `elmos.billing.checkout.requests` | `provider_error > 0` |
  | `elmos.billing.webhook.events` | `reconciliation` 持续增长 |
  | `elmos.billing.api.errors` | database/provider 错误持续增长 |
- `[ ]` **6.3 日志聚合与错误追踪**
- `[ ]` **6.4 定义 SLO** 与服务信用政策（与 SLA 文本一致）
- `[ ]` **6.5 值班与升级路径**
- `[ ]` **6.6 备份 → 真实恢复演练**（关闭 RISK-DATA-001；**备份成功不算，恢复成功才算**）
- `[ ]` **6.7 负载 / Soak / 容量测试**（关闭 RISK-SRE-001）
- `[ ]` **6.8 日常检查表落地**（见 `docs/tasks/self-service-billing/OPERATIONS_RUNBOOK.md`）：
      readiness、对账案件年龄、过期 `RESERVED` 租约、`PENDING` 计量事件

---

## 阶段 7 —— 安全与合规

- `[ ]` **7.1 内部安全自查**：认证、授权、RLS、Secret、出网、依赖漏洞
- `[!][$]` **7.2 独立渗透测试**（关闭 RISK-SECURITY-001）
- `[!]` **7.3 独立租户隔离评审**
- `[ ]` **7.4 完整传递依赖 SBOM 与签名**
- `[ ]` **7.5 生产 Secret 管理选型**与轮换演练
- `[!]` **7.6 ICP 备案 / 等保定级**（仅中国大陆经营）

---

## 阶段 8 —— 产品运营

- `[ ]` **8.1 邮件通道**：供应商 + SPF/DKIM/DMARC；开启
      `ELMOS_USAGE_EMAIL_ALERTS_ENABLED=true` **之前**必须完成退订、频控、地址验证、
      供应商回执、失败重试、隐私评审
- `[ ]` **8.2 新用户 Onboarding**：首次任务引导 + 示例仓库
- `[ ]` **8.3 帮助文档与公开能力支持矩阵**（严格对应 A/B/C 档）
- `[ ]` **8.4 客服工单入口**
- `[ ]` **8.5 状态页**
- `[ ]` **8.6 管理后台补全**：客户查询、配额调整、退款、封禁

---

## 阶段 9 —— 客户验证与开售

- `[ ]` **9.1 招募 ≥2 个设计伙伴**，签署试用协议
- `[ ]` **9.2 在客户真实仓库跑通端到端**，记录缺陷与修复
- `[ ]` **9.3 客户验收记录 + 独立验证者签署**（关闭 RISK-EXTERNAL-001）
- `[ ]` **9.4 开售前最终检查**
  - 七项 residual risk 中三项 critical 是否已闭合或已被明确接受并向客户披露
  - 定价目录 `PUBLISHED` 且四项状态齐全
  - 备份恢复演练完成
  - 对外能力声明与证据一致
- `[ ]` **9.5 正式开售**

---

## 附：不可绕过的失败关闭规则

以下情形一律**不得**解释为成功（引自 `docs/BUSINESS_LINE_CLOSURE_MATRIX.md`）：

> `UNKNOWN`、`INCONCLUSIVE`、`NOT_RUN`、缺失或过期证据、执行者与验证者相同、
> 未授权的外部操作、未绑定精确产物摘要、局部/稀疏工作区被当作完整工作区，
> 以及只通过静态检查却声称真实运行、生产就绪或认证。

上线压力**不构成**放宽上述规则的理由。如果某项证据来不及产生，正确做法是
**缩小对外承诺范围**，而不是把 `NOT_RUN` 当作通过。
