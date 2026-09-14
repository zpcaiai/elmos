# 订单与支付遗漏复核（2026-09-14）

| 缺口 | 修复 | 本地证据 | 外部状态 |
|---|---|---|---|
| ELMPay 返回托管 URL，但前端按支付宝域名判断而拒绝 | 增加 `checkoutSurface=ELMPAY_HOSTED`；后端绑定公开基址/session/token/有效期，BFF 与三个购买入口统一校验 | API 34/34、Web policy 57/57、TypeScript PASS、ELMPay payment-core 与 checkout-web PASS | 真实商户旅程 `NOT_RUN` |
| 本地订单 TTL 已过仍可再次调用支付方 | Credit/一次性订单和钱包充值在网关调用前严格检查 `expiresAt > now`；客户端收到过期码或轮询到 EXPIRED 后换新幂等键 | `OrderExpiryGuardTest` PASS | 生产部署 `NOT_RUN` |
| 充值同幂等键可改变金额/actor/provider | V88 对重放事实做 `IS DISTINCT FROM` 精确校验 | PostgreSQL 17.5 live PASS | V88 生产迁移 `NOT_RUN` |
| 充值日限额为先查后插，可被并发穿透 | V88 在钱包账户行锁内完成日累计检查与订单插入 | 两个并发 ¥6、日限 ¥10：恰好一个成功 | V88 生产迁移 `NOT_RUN` |
| 过期未付款充值单永久占用当日限额 | V88 的日累计排除 TTL 已结束的 `CREATED/PENDING_PAYMENT`，但不提前改写订单状态，保留晚到付款对账 | PostgreSQL 17.5 live：过期 ¥6 后可再创建 ¥6 | V88 生产迁移 `NOT_RUN` |
| 已入账订单幂等重放被前端误判为缺少付款入口 | Credit/一次性订单 `FULFILLED`、充值 `PAID/CREDITED` 走终态响应，不再生成或要求新付款入口 | TypeScript + wallet policy 终态负向检查 PASS | 浏览器代表性旅程 `NOT_RUN` |
| 钱包微信充值只显示 `code_url` 文本，无法扫码 | 共享策略校验微信 Native URI，钱包页面本地生成二维码图像 | TypeScript + wallet policy 负向检查 PASS | 微信真实付款旅程 `NOT_RUN` |
| 商业订单相同幂等键并发创建可能唯一键冲突 | V88 按 tenant/idempotency 事务 advisory lock 收敛 | 两个并发创建返回同一订单、仅一行 | V88 生产迁移 `NOT_RUN` |
| ELMPay public base 可携带 query | ELMPay 拒绝 credentials/query/fragment，防止 checkout token 进入请求日志 | `HostedCheckoutPublicBaseTest` PASS | 部署 `NOT_RUN` |

仍未伪造为已完成的边界：双人人工 Credit 调整、促销/退款分类策略、真实支付费率/FX/净额与
银行结算、生产商户付款退款、V88 生产迁移、独立认证，继续保持 `MISSING` / `PARTIAL` /
`NOT_RUN` / `NOT_CERTIFIED`。
