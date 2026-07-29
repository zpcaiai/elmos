# 支付适配器实现状态

日期：2026-07-28（第二轮）
关联：D-01（大陆主体 + 支付宝/微信）、[`PAYMENT_CN_ADAPTER_SPEC.md`](PAYMENT_CN_ADAPTER_SPEC.md)

---

## 1. 本轮新增

| 类 | 职责 | 验证方式 |
|---|---|---|
| `PaymentProvider` | 通道枚举 + 严格解析 + 币种相容性 | 自检 |
| `PaymentCallbackPipeline` | **五步顺序管线**（本轮核心） | 自检，断言调用顺序 |
| `PaymentProviderRouter` | 按目录选网关/适配器，失败关闭 | 自检 |
| `AlipayCheckoutGateway` | 支付宝下单：参数构造 + RSA2 签名 + 跳转 URL | 自检 |
| `WechatPayNativeGateway` | 微信 Native 下单：请求体 + APIv3 签名 + code_url | 自检 |
| `PaymentCallbackController` | 两个回调端点（薄壳） | 对桩注解编译通过 |

**自检总量：124 项断言，0 失败**（javac/java 21.0.10）

```
PaymentCryptoSelfTest    46 通过    金额换算、支付宝验签、微信验签与解密
PaymentPipelineSelfTest  45 通过    五步顺序、幂等、金额比对、路由器失败关闭
CheckoutGatewaySelfTest  33 通过    两家下单的参数构造与签名
```

---

## 2. 顺序是被断言过的，不是靠注释保证的

用户强调的那条链——**验签 → 幂等去重 → 金额比对 → 写 provider event → 更新订阅**——
在 `PaymentPipelineSelfTest` 里是逐条断言的，用一组会记录调用顺序的测试替身：

| 断言 | 说明 |
|---|---|
| 正常路径调用序列恰好是 `verify → normalize → registerIfAbsent → findByOutTradeNo → record → activate` | 顺序本身被固定 |
| **验签失败时只调用了 verify，连 normalize 都没做** | 未验签的报文不该被解析 |
| **验签失败不登记幂等键** | 否则伪造回调会挡掉后续合法回调 |
| 重发回调只走到 `registerIfAbsent`，订阅只激活一次、事件只写一次 | 幂等真实生效 |
| **金额不符时既不写事件也不更新订阅**，但开对账案件 | 篡改金额拿不到订阅，原始事实不丢 |
| 订单未知时同样开案件、不写事件 | 不静默丢弃 |
| 幂等键 = 通道 + 提供方事件 ID | 同订单的退款事件不会被误判为重复 |
| 缺事件 ID 抛异常，不退化成订单号 | 退化会让退款事件全被吞掉 |

最后两条值得单独说：**幂等键不能用 `out_trade_no`**。同一订单会有支付成功、退款、
关单多个事件，用订单号做键会把后续事件全部当成重复丢弃——这个 bug 上线后
表现为"退款回调收不到"，极难定位。

---

## 3. 契约扩展：8 处

| # | 位置 | 状态 | 验证 |
|---|---|---|---|
| 1 | `contracts/pricing-catalog-schema/elmos-pricing-catalog.schema.json` | ✅ `const` → `enum` | `jsonschema` 校验 schema 自身合法；`PAYPAL` 被拒 |
| 2 | `contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json` | ✅ → `ALIPAY_CHECKOUT` | 目录通过 schema 校验 |
| 3 | `apps/web-console/app/lib/pricingCatalog.ts` | ✅ 联合类型扩展 | `tsc --strict` 通过 |
| 4 | Java 通道常量 | ✅ 新增 `PaymentProvider` 枚举 | 自检 |
| 5 | `scripts/commercial/validate_pricing_catalog_publication.py` | ✅ 上一轮已支持 | 12 用例 |
| 6 | `PricingPlanCatalogTest` | ⬜ **未改** | 需要 Maven reactor |
| 7 | `apps/web-console/app/pricing/BillingActions.tsx` | ⬜ **未改** | 需要两种前端形态（跳转 / 二维码） |
| 8 | `apps/web-console/app/api/billing/checkout/route.ts` | ⬜ **未改** | 响应体需支持 `qrCodeUrl` |

第 6/7/8 项需要在能跑 `mvn` / `pnpm` 的环境里完成。第 7 项不是简单改类型：
支付宝是**跳转**、微信是**渲染二维码**，前端要按 `provider` 分支两种交互。

### 顺带修掉的一个既有缺陷

`pricingCatalog.ts` 里的 `exactCatalog` 原本是：

```ts
function exactCatalog(value: typeof rawPricingCatalog): PricingCatalog {
  return value as PricingCatalog;
}
```

这是一个**无条件类型断言**。JSON 导入会把字面量放宽成 `string`，所以编译期不会报错——
把目录里的 `paymentProvider` 改成 `PAYPAL` 也照样通过。"精确目录"名不副实。

编译期无法约束放宽后的 JSON，因此改为**加载时失败关闭**：取值域漂移会在应用启动时
立刻抛 `PRICING_CATALOG_INVALID`，而不是等用户点了付费按钮才暴露。
`tsc --strict` 通过，运行时行为 8 项验证通过（`PAYPAL` / 空串 / 小写 / null / 数字全部被拒）。

---

## 4. 仍未完成

| 项 | 状态 |
|---|---|
| 商户号申请 | 未申请（需营业执照 + 对公账户） |
| 回调端点的 Spring Security 放行配置 | **未配置**——上线前必须显式放行且只放行这两个路径 |
| 端口实现（`ProcessedEventLog` 等 5 个接口的数据库实现） | 未实现 |
| `ProcessedEventLog` 的原子性 | 实现时**必须用唯一约束**，不能"先查后插" |
| 时间戳偏差校验（防重放） | 未实现，见 `WechatPayCallbackCipher` 类注释 |
| 沙箱全链路 / 真实交易 / 真实退款 | `NOT_RUN` |
| 发票能力 | 未实现 |
| 退款、关单、对账定时任务 | 未实现 |

**系统仍然收不了钱**，这是预期的。

---

## 5. 验证边界（不要越级引用）

- 124 项断言是**单元级**验证，用的是测试替身，没有连过任何真实提供方。
- `PaymentCallbackController` 只对**桩注解**编译通过，Spring 的实际装配、
  参数绑定（尤其是支付宝的表单参数注入）、Security 放行**全部未验证**。
- 五个端口接口都还没有数据库实现，管线目前接不到真实数据。
- 本轮未运行 `mvn verify`——本环境没有完整 reactor 依赖。
  **合入前必须在能跑 Maven 的环境里跑一次全量构建。**
