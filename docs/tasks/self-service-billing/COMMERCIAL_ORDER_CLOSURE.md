# Credit 与单项目订单闭环

## 结论

目录、订单、支付下单/回调、Credit 账户、单项目权益、生成预留/结算/释放、
逐用户 Token 事件历史和 Web/BFF 已在仓库内闭环。目录仍为 `DRAFT`，
`ELMOS_BILLING_LIVE_ENABLED` 默认关闭；在真实商户、法务、税务、开票、成本、
生产迁移和独立验收证据齐全前不得改为 `PUBLISHED`，也不得宣称上线认证。

## 需求追踪

| 需求 | 实现 | 可执行证据 | 状态 |
|---|---|---|---|
| 购买 Credit | `elmos-credit-500`，¥99 / 500 Credits，365 天 FIFO 批次 | 真实 PostgreSQL 订单履约、重复回调、余额和账本测试 | `DONE_LOCAL` |
| 单项目一次性支付 | `elmos-project-generation-once`，¥39，项目绑定且只消费一次 | 项目错配拒绝、一次性权益 hold/consume 测试 | `DONE_LOCAL` |
| 用户 Token 消耗 | reservation/event/ledger 带 actor/project/job/model，并合并生产 `billing.token_usage_events` | SELF/ORGANIZATION 隔离、INPUT/CACHE_READ/OUTPUT/REASONING、聚合和 provider receipt 测试 | `DONE_LOCAL` |
| 真实支付代码路径 | 支付宝电脑网站支付、微信 Native 下单及双方验签回调 | 真实密钥加解密向量、金额/币种、回放、路由和 Spring 装配自检 | `DONE_LOCAL` |
| 回调故障恢复 | PROCESSING/FAILED/COMPLETED claim；原始事件同事实幂等 | 履约首试失败后二试成功、完成后拒绝重放 | `DONE_LOCAL` |
| 租户和操作者隔离 | JWT scope、委托 scope、FORCE RLS、SECURITY DEFINER 白名单 | 最小权限角色、跨租户/跨 actor 负向测试 | `DONE_LOCAL` |
| 用户充值可见闭环 | 定价页展示组织 Credit 可用/冻结/总额、本人订单和本人流水；二维码订单轮询终态 | 付款前保持 0、`FULFILLED` 后显示 500 Credit 与 `PURCHASE` 流水的桌面/移动旅程 | `DONE_LOCAL` |
| 生产商户收款 | 商户号、证书、回调域名、真实资金与退款/对账 | 尚无提供方/资金凭证 | `NOT_RUN` |
| 法务税务开票 | 中国大陆主体、协议、隐私、发票、税率 | 尚无责任人签核证据 | `NOT_RUN` |
| 生产发布 | 生产数据库迁移、密钥注入、域名、监控、回滚演练 | 尚未获得部署授权 | `NOT_RUN` |
| 独立认证 | 独立人员/机构复验真实资金闭环 | 无独立证据 | `NOT_CERTIFIED` |

## 失败关闭规则

1. 金额只从服务端不可变目录快照进入订单，客户端不能提交价格或数量。
2. 相同幂等键只能重放完全相同的 actor、SKU、project 和请求摘要。
3. 支付回调先校验时间窗与签名，再领取回调、核单、核金额并保存事实，最后履约。
4. 履约失败将回调 claim 标为 `FAILED`；提供方重发可重领。已写的同事实 provider event
   可幂等读取，载荷、金额、组织或订单事实变化则拒绝。
5. 微信下单发生网络异常时状态为 `RECONCILIATION_REQUIRED`，禁止盲目重下单；
   支付宝签名/参数构造失败在未联系提供方时标为 `FAILED`。
6. 已过本地 TTL 才确认的付款不自动发 Credit/权益，记录
   `PAYMENT_AFTER_LOCAL_EXPIRY` 并进入对账。
7. Credit 只允许通过购买、预留、结算、释放函数变更；账本追加写，余额不允许直接改。
8. SELF 历史只返回当前 actor；组织视图必须具备管理 scope。
9. 浏览器返回页、二维码和 `PAID` 状态不增加余额；只有 `FULFILLED` 与服务端账本才显示到账。
10. `RECONCILIATION_REQUIRED` 停止自动购买重试并提示用户不要重复付款。

## 发布门禁

只有以下项目全部具有不可变证据引用后，才可新建一个 `PUBLISHED` 目录版本：

- 支付宝或微信支付生产商户已配置，真实 ¥0.01/退款/重复通知/延迟通知客户旅程通过；
- 回调 HTTPS 域名、备案、证书轮换和网络准入通过；
- 法务、隐私、税务、退款、服务条款和电子发票责任人签核；
- 单位经济成本样本通过，价格/额度不会造成未批准的亏损风险；
- 生产 PostgreSQL 备份、V1–V95 validate/migrate/validate、监控和回滚演练通过；
- 独立验证者复核订单、资金、provider receipt、Credit/权益和 Token 历史逐笔一致。

仓库门禁 `scripts/commercial/validate_pricing_catalog_publication.py --check-publishable`
在上述证据缺失时必须返回非零；不得通过关闭门禁或伪造状态上线。
