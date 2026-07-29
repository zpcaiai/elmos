# 支付宝 / 微信支付适配器实现规格

生成日期：2026-07-28
触发决策：**D-01 = 方案 B（中国大陆主体 + 支付宝/微信支付）**
状态：**规格，未实现**。本文不产生任何实现或验证证据。

---

## 1. 好消息：状态机不用重写

`SelfServiceBillingPort` 与既有 `StripeCheckoutGateway` 已经把正确的形状定下来了，
新适配器**复用**这套结构，不是另起炉灶：

```
本地准备（PREPARING）
    → 调用提供方（PROVIDER_CALLED）
    → 本地完成（COMPLETED / FAILED）
    → 结果未知一律进入待对账（RECONCILIATION_REQUIRED）
```

以及已经存在、必须原样保留的四条规则：

1. **价格由服务端决定**，客户端只能提交 planId，不能提交金额
2. **回调必须验签**，签名不通过一律拒绝且不创建订阅
3. **幂等**：同一幂等键只能对同一案件、同一决定、同一外部引用重放
4. **结果未知不重试**：进对账案件，等人工核对提供方后台后结案

新适配器要做的是把"调用提供方"和"验签"两段换成支付宝/微信的实现。

---

## 2. 两个提供方的关键差异（会影响接口形状）

| 维度 | 支付宝 | 微信支付 v3 |
|---|---|---|
| 建议接入方式 | 电脑网站支付 `alipay.trade.page.pay` | Native 支付（扫码）`/v3/pay/transactions/native` |
| 前端形态 | 跳转支付宝页面 | 返回 `code_url`，前端渲染二维码 |
| 签名 | RSA2（SHA256withRSA），应用私钥 + 支付宝公钥 | 请求 `Authorization` 头签名 + 回调 AES-256-GCM 解密 |
| 回调验签 | 支付宝公钥验签 | 平台证书验签 + APIv3 密钥解密 |
| 金额单位 | **元**，字符串两位小数 | **分**，整数 |
| 订阅/自动续费 | 需单独签约「周期扣款」协议 | 需单独申请「委托代扣」 |
| 退款 | `alipay.trade.refund` | `/v3/refund/domestic/refunds` |

**金额单位差异是最容易出事的地方**：目录里是 `priceFen`（分）。
支付宝分支必须做一次分→元的精确转换，且**只能用整数运算**，
禁止浮点：`f"{fen // 100}.{fen % 100:02d}"`。

---

## 3. 订阅模式的取舍（需要产品决定）

大陆两家的"自动续费"都需要额外签约，审核周期比普通收单长。两条路：

### 3.1 先做「手动续费」（推荐首发）

- 用户每期主动付款，付款成功后延长订阅到期日
- 到期前 7/3/1 天发提醒（邮件通道，`ELMOS_USAGE_EMAIL_ALERTS_ENABLED`）
- 到期未续则降级到只读，额度停发，**不自动扣款**
- 与目录已声明的 `overagePolicy=HARD_STOP_NO_AUTOMATIC_CHARGE` 完全一致
- 工作量：**3–4 人周**

### 3.2 做「周期扣款签约」

- 需要额外资质审核，日历不可控
- 需要新增签约状态机（签约、解约、扣款失败重试、协议过期）
- 工作量：**+2–3 人周**，且强依赖平台审核结果

> 建议首发走 3.1。年付本来就是一次性付款，月付用手动续费也能跑通商业闭环；
> 等有真实续费数据后再决定值不值得做自动续费。

---

## 4. 实现清单

### 4.1 新增文件（`apps/commercial-api`）

```
AlipayCheckoutGateway.java          与 StripeCheckoutGateway 同层，实现同一 Port
AlipaySignatureVerifier.java        RSA2 验签，公钥来自配置，不落库
WechatPayNativeGateway.java
WechatPaySignatureVerifier.java     平台证书验签 + APIv3 回调解密
PaymentProviderRouter.java          按目录 paymentProvider 选择网关，未知即失败关闭
MoneyConversion.java                priceFen ↔ 各提供方金额格式，纯整数运算
```

### 4.2 新增回调端点

```
POST /commercial/v1/billing/callbacks/alipay      （form-urlencoded）
POST /commercial/v1/billing/callbacks/wechat      （JSON + 加密报文）
```

两者都必须：验签 → 幂等键去重 → 金额与币种比对本地订单 → 写 `payment_provider_events`
→ 才更新订阅。**任何一步不通过都不得更新订阅状态。**

### 4.3 数据库

V49 的 `payment_provider_events` / `payment_reconciliation_cases` 结构可复用，
但需要确认 `provider` 列的取值域是否为受限枚举。若是，需要一条新迁移扩展枚举
（**forward-only**，不得改写既有迁移）。

### 4.4 环境变量（已加入 `elmos-commercial.env.example`）

```
ELMOS_PAYMENT_PROVIDER=ALIPAY_CHECKOUT | WECHAT_PAY_NATIVE

# 支付宝
ELMOS_ALIPAY_APP_ID=
ELMOS_ALIPAY_PRIVATE_KEY_FILE=          # 0600，绝不入版本库
ELMOS_ALIPAY_PUBLIC_KEY_FILE=           # 支付宝公钥，用于验签
ELMOS_ALIPAY_GATEWAY_URL=
ELMOS_ALIPAY_NOTIFY_URL=
ELMOS_ALIPAY_RETURN_URL=

# 微信支付
ELMOS_WECHATPAY_MCHID=
ELMOS_WECHATPAY_APIV3_KEY_FILE=         # 0600
ELMOS_WECHATPAY_CERT_SERIAL_NO=
ELMOS_WECHATPAY_PRIVATE_KEY_FILE=       # 0600
ELMOS_WECHATPAY_PLATFORM_CERT_FILE=
ELMOS_WECHATPAY_NOTIFY_URL=
```

私钥一律用 `_FILE` 形式（owner-only、非符号链接、绝对路径），
与仓库既有的令牌文件约定一致，不放进环境变量值。

---

## 5. `paymentProvider` 从 const 扩为 enum 的影响面

目录 Schema 现在是：

```json
"paymentProvider": { "const": "STRIPE_CHECKOUT" }
```

改成 enum 会牵连以下位置，**必须同批次改完，否则前后端契约会裂**：

| 位置 | 需要的改动 |
|---|---|
| `contracts/pricing-catalog-schema/elmos-pricing-catalog.schema.json` | `const` → `enum: [STRIPE_CHECKOUT, ALIPAY_CHECKOUT, WECHAT_PAY_NATIVE]` |
| `contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json` | 值改为 `ALIPAY_CHECKOUT` 或 `WECHAT_PAY_NATIVE` |
| `modules/commercial-operations` 的目录常量 | 同步枚举 |
| `PricingPlanCatalogTest` | 增加各 provider 的正向/负向用例 |
| `apps/web-console/app/lib/pricingCatalog.ts` | 前端类型同步 |
| `apps/web-console/app/pricing/BillingActions.tsx` | 支付宝跳转 vs 微信二维码，两种前端形态 |
| `apps/web-console/app/api/billing/checkout/route.ts` | 响应体多一种形态（`code_url`） |
| `scripts/commercial/validate_pricing_catalog_publication.py` | **已支持**（本轮已实现并实测） |

**目录 Schema 本轮没有改动**——改它会让 Java/TS 契约测试同时失败，
而本环境无法编译验证。这是刻意留给你在能跑构建的环境里一次性完成的。

---

## 6. 验收标准（每条都要有证据）

| # | 验收点 | 证据形态 |
|---|---|---|
| 1 | 沙箱下单 → 支付 → 回调 → 订阅生效 → 额度可用 | 全链路日志 + 数据库状态 |
| 2 | 伪造签名的回调被拒绝，且**不创建订阅** | 负向测试 |
| 3 | 同一回调重放 N 次，订阅只生效一次 | 幂等测试 |
| 4 | 金额被篡改的回调被拒绝 | 负向测试 |
| 5 | 提供方超时/结果未知 → 进对账案件，**不自动重试** | 故障注入 |
| 6 | 管理员结案需要外部证据引用，且写入不可改写审计 | 审计记录 |
| 7 | 真实小额交易 + 真实退款 | 生产环境流水 |
| 8 | 分→元转换在边界值上精确（0、1、99、100、12900、129000） | 单元测试 |

第 7 项在真实商户开通前保持 `NOT_RUN`。前 6 项和第 8 项可以在沙箱完成。

---

## 7. 不在本规格范围内

- 增值税发票开具（单独工作项，2–3 人周或先人工）
- 企业对公转账 / 银行汇款（B 端客户常见诉求，需要人工核销流程）
- 分账、代付、跨境结算
- 自动续费签约（见第 3.2 节，建议延后）
