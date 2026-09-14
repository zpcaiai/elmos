# 自助计费修改历史

## 2026-09-14 — 订单创建并发与 ELMPay 托管收银台闭环

- 新增 V88：钱包账户行锁串行化充值日限额，过期未付款订单释放日限额但保留晚到付款对账路径；充值幂等重放绑定 actor/金额/provider；
  商业订单按 tenant/idempotency 事务锁收敛并发创建。
- ELMOS 后端严格绑定 ELMPay 公共收银台基址、响应 session、fragment token 与有效期；
  前端/BFF 通过 `checkoutSurface` 区分底层收单通道和 ELMPay 托管页面。
- Credit/一次性订单和充值订单在本地 TTL 到期后不再调用支付提供方；客户端清理已过期幂等键；已完成/已付款的幂等重放不再要求新的付款入口。
- ELMPay 公共收银台配置禁止 credentials/query/fragment，避免 token 进入 HTTP 请求和日志。
- V1→V88 与并发用例仅为本地自证；受保护生产数据库仍停在已有 V87 证据，V88 生产迁移、
  真实商户付款/退款、银行结算和独立认证保持 `NOT_RUN` / `NOT_CERTIFIED`。

## 2026-09-13 — Credit 双分录、outbox 与投影恢复

- 新增 V87 不可变 Credit journal transaction/posting 和提交时借贷守恒约束。
- 对已有余额生成 opening transaction；之后购买、预留、结算、释放和到期均自动记双分录。
- 新增与 journal 同事务写入的 outbox，独立 publisher 以租约领取、同 event ID 失败重试并完成发布。
- 新增只读对账 API，以及 reconciler 角色限定、actor/reason/idempotency 绑定的投影重建审计。
- 新增真实 PostgreSQL 17.5 全迁移、1000 并发不超支、不平衡提交拒绝、outbox 重试与重建测试。
- 主线合并后 `commercial-production` run `34713508064` 在批准的 Neon PostgreSQL 17.11
  完成 V86→V87、前后 Flyway 校验和最小权限运行角色授权。
- 促销/退款分类、双人人工调整、真实 provider/bank 结算、生产迁移和独立认证仍保持
  `PARTIAL` / `MISSING` / `NOT_RUN` / `NOT_CERTIFIED`。

## 2026-09-08 — Credit、一次性项目订单与用户 Token 历史

- 新增目录 `2026-09-08.1`：500 Credits（¥99）和单项目生成一次（¥39）。
- 新增 V83 商品订单、Credit 账户/FIFO 批次/追加账本、项目权益和生成资金预留。
- 支付回调扩展到 Credit/一次性订单；增加可重试 callback claim、同事实事件幂等、
  订单交接状态、结果未知对账和过期后付款保护。
- 注册支付宝电脑网站支付与微信 Native 真实下单网关配置，保持 CNY/大陆通道约束。
- Token 用量增加 actor/project/job/model 和原始事件历史；SELF 默认隔离，组织视图需管理 scope。
- Web BFF、定价页、Credit/订单/账本/Token 历史界面及生成/翻译 producer 完成接线。
- 目录继续为 `DRAFT`、live billing 默认关闭；真实商户、法务税务、生产迁移和独立认证
  仍为 `NOT_RUN` / `NOT_CERTIFIED`。

## 2026-07-28 — P0/P1 完整实现

### 套餐与计量

- 建立人民币单一权威目录 `2026-07-28.2`：14 天免费体验、¥129/月、¥1,290/年。
- 设置每档 Token/Credit、项目数、并发数和证据保留期。
- 定义输入、输出、缓存读、缓存写 Token 分类及五种平台 Credit 费率。
- 实现预留、结算、释放、到期、硬停止、提供方 receipt 和追加式纠正。

### 身份与数据

- 以 OIDC JWT issuer/JWK/audience 和 scope 保护计费路由。
- 组织 ID 只来自认证身份；PostgreSQL 事务设置租户上下文并强制 RLS。
- 新增 V49 类型化订阅、额度、试用、支付、对账与告警 Schema。
- 实现一组织/一验证身份一次试用、自动到期和转付费关闭。

### 支付

- 实现服务端 Stripe Checkout、CNY Price ID 映射、签名 Webhook 和取消续费。
- Checkout 改为本地准备、提供方调用、本地完成的两阶段状态。
- 未知提供方结果自动进入待对账；新增管理员列表和追加式结案审计。
- 目录未发布或外部配置缺失时保持不可购买。

### 实时用量与运营

- 套餐页显示已用、预留、剩余、基点进度、历史、预测、告警和 CSV。
- 套餐页接通免费体验、当前订阅、付费结账和两步确认取消；DRAFT 目录下付费入口禁用。
- 新增同源 Cookie 写请求保护、BFF 请求白名单和不含支付提供商引用的客户订阅摘要。
- 生成/翻译 Runner 接入 Credit 预留及实际分钟结算，模型调用接入 Token receipt。
- 新增数据库 readiness 和低基数 Micrometer 计费指标。
- 新增严格 Neon Flyway 工作流、运行手册、本地 PostgreSQL 集成测试和 Chromium 客户旅程。

### 保留的外部门槛

- Neon 生产迁移、真实 OIDC、Stripe 商户与 Webhook、邮件发送、税务/开票、法务与成本验证
  均没有外部凭证或授权，保持 `NOT_RUN` / `NOT_CONFIGURED`。
