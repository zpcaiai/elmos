# ELMPay 支付对接

状态：`DONE_LOCAL`。生产商户、真实付款、外部回执与独立验证仍为 `NOT_RUN`，整体为
`NOT_CERTIFIED`。

## 边界与数据流

1. ELMOS 继续按定价目录选择底层通道（`ALIPAY_CHECKOUT` 或
   `WECHAT_PAY_NATIVE`），服务端确定 CNY 分值和本地订单号。
2. 启用 `ELMOS_ELMPAY_ENABLED=true` 后，当前通道的下单出口改为调用 ELMPay
   `POST /v1/checkout-sessions`。ELMOS 不接受浏览器自报金额。
3. ELMPay 返回托管收银台 URL、checkout session ID 和 payment intent ID；用户在
   ELMPay 收银台完成底层支付宝/微信支付。
4. ELMPay 将已提交的 `payment_intent.captured` v1 事件扇出到项目 webhook outbox，
   持久重试并以 `HMAC-SHA256(timestamp + "." + raw_body)` 签名。
5. ELMOS 的 `POST /commercial/v1/billing/callbacks/elmpay` 验证时间窗、key ID、
   原始体签名、tenant/project、事件版本、provider、币种与金额，再用
   `business_order_digest` 查询 V84 的索引目录，最后沿既有幂等回调管线履约。

ELMPay 不向 webhook 暴露原始业务订单号。ELMOS 为订阅、钱包充值、Credit 包和一次性
项目订单分别维护 SHA-256 索引，避免跨租户扫描或削弱源表 RLS。

## ELMOS 配置

必须配置：

- `ELMOS_ELMPAY_BASE_URL`、`ELMOS_ELMPAY_TENANT_ID`、`ELMOS_ELMPAY_PROJECT_ID`
- `ELMOS_ELMPAY_API_TOKEN_FILE`（短期、项目绑定 token 的 0400 挂载文件）
- `ELMOS_ELMPAY_WEBHOOK_KEY_ID`、`ELMOS_ELMPAY_WEBHOOK_SECRET_FILE`
- `ELMOS_ELMPAY_RETURN_ROUTE_ID`

生产 HTTPS 还必须配置 PKCS12 双向 TLS：

- `ELMOS_ELMPAY_TLS_KEY_STORE_FILE`、`ELMOS_ELMPAY_TLS_KEY_STORE_PASSWORD_FILE`
- `ELMOS_ELMPAY_TLS_TRUST_STORE_FILE`、`ELMOS_ELMPAY_TLS_TRUST_STORE_PASSWORD_FILE`

仅本机 ELMPay 沙箱可设置 `ELMOS_ELMPAY_ALLOW_HTTP_LOCAL_SANDBOX=true`；代码只允许
`localhost`/loopback HTTP。配置与迁移完成后才设置 `ELMOS_ELMPAY_ENABLED=true`。

## ELMPay 侧要求

- API 主体的 tenant/project/merchant 与 ELMOS 配置完全一致，并具备 checkout 写权限。
- 为同一 tenant/project 注册状态为 `ACTIVE` 的 ELMOS HTTPS webhook endpoint。
- 为该 project 注册有效的 signing key；ELMOS 挂载的是同一 key ID 对应的 32..128
  字节 secret，轮换时保留重叠窗口。
- worker 运行角色需要 `webhook_endpoint:SELECT` 以及
  `webhook_delivery_outbox:SELECT,INSERT,UPDATE`；secret 仍通过既有受信租约解析器取得。

## 切换、观察与回滚

切换前在隔离环境执行 Flyway 到 V94，并验证 V84 的三个
`business_order_sha256` 唯一索引和 V94 的函数 schema 修复。
用真实小额订单检查：创建收银台、底层支付、captured 事件、首次履约、重复事件幂等、
金额不符对账和超时未知结果。保存 ELMPay/渠道原始 receipt。

回滚时先关闭 `ELMOS_ELMPAY_ENABLED` 和新的购买入口。原生支付宝/微信回调适配器仍在，
可处理切换前在途订单；不得删除 V84 摘要列、V94 函数修复、订单、事件、Credit lot
或对账事实。
