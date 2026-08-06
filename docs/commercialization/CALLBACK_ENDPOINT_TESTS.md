# 回调端点：Security 放行与参数绑定测试

日期：2026-07-28（第五轮）
关联：[`PAYMENT_ADAPTER_STATUS.md`](PAYMENT_ADAPTER_STATUS.md)、[`MVN_VERIFY_FINDINGS.md`](MVN_VERIFY_FINDINGS.md)

---

## 1. 先说一个必然会踩的坑

现有安全配置里有这条：

```java
.requestMatchers("/commercial/v1/billing/**").authenticated()
```

两个回调路径 `/commercial/v1/billing/callbacks/{alipay,wechat}` **正好落在它下面**。
不改配置，提供方的回调会被直接 401 —— 而提供方不会带我们的令牌，
永远也拿不到 200，最终表现为"客户付了钱但订阅没开通"，且回调被无限重发。

修改是在 permitAll 列表里**逐条加两个精确路径**（与既有的 Stripe webhook 同一列表，
顺序在 `authenticated()` 之前，先匹配先生效）。

**没有写成 `/commercial/v1/billing/callbacks/**`。** 通配会把将来任何新增的
callbacks 子路径一并变成公网无认证可达，而新增路径未必带验签。
放行范围必须与验签实现一一对应，这条约束由测试守住（见 3.2 最后一个用例）。

---

## 2. 控制器为什么还没有 `@RestController`

`PaymentCallbackController` 的六个构造参数（Router + 五个端口）**目前没有任何 Bean 实现**：
`JdbcCallbackPorts` 与 `JdbcOrderPorts` 是静态工厂，还没有配置类把它们注册成 Bean。

此时加上 `@RestController` 会被组件扫描发现，于是整个 Spring 上下文因缺少构造参数
起不来——**连带把 `CommercialSecurityConfigurationTest` 这些无关测试一起弄挂**。

所以当前形态是：类型级 `@RequestMapping` 已就位，但不带 stereotype 注解，
组件扫描不会注册它。请求映射与参数绑定由 `standaloneSetup` 真实验证；
等端口 Bean 落地，加一行 `@RestController` 即可接入。

---

## 3. 两个测试

### 3.1 `PaymentCallbackBindingTest`（6 个用例，standaloneSetup）

用 `MockMvcBuilders.standaloneSetup` 而不是 `@SpringBootTest`：
它用的是真实的 `RequestMappingHandlerAdapter` 与真实参数解析器，
`@RequestParam Map`、`@RequestBody String`、`@RequestHeader` 都是真跑。
端口全部手写替身，不引 Mockito——替身要记录"收到了什么"，手写比打桩直观。

| 用例 | 断言什么 |
|---|---|
| 支付宝表单参数注入 | 5 个参数一个不少地进入管线，且响应体**恰好**是 `success` |
| 微信原始体未被重新序列化 | 用非规范化 JSON（键顺序、空格、`支` 转义）请求，**逐字节比对** |
| 微信四个头到位 | Timestamp/Nonce/Signature 用于验签，Serial 用于选平台证书 |
| 缺签名头 | Spring 直接 400，**管线不得被调用**（未验签的报文不应进入业务路径） |
| 重复回调 | 仍回 200 `success`，否则提供方无限重发 |
| 失败响应不泄露内部细节 | ORDER_UNKNOWN 时响应体是固定的 `fail`，不含订单号或异常信息 |

第二个用例是重点：微信验签对的是**原始字节对应的文本**，
任何"先反序列化再重新序列化"都会让验签必失败。用 `@RequestBody String`
而不是某个 DTO，就是为了这个；逐字节断言把这个约束固定下来。

### 3.2 `PaymentCallbackSecurityTest`（5 个用例，`@SpringBootTest` + `@AutoConfigureMockMvc`）

沿用仓库既有 `CommercialSecurityConfigurationTest` 的写法（同样的注解与静态导入）。

**放行的判据是「不是 401」，不是某个具体成功码。** 两个理由：

1. 控制器目前没注册，放行后请求穿过过滤器链但找不到处理器，
   落到 Spring Boot 的 `/error` 转发上——而规则末尾是 `anyRequest().denyAll()`，
   错误转发的最终状态码是 404 还是 403，取决于 Security 是否过滤 ERROR dispatch。
   断言具体码会让测试变脆。
2. 等控制器接上 Bean，同样的请求会变成 200/400。
   「不是 401」在两个阶段都成立，不必回来改测试。

反过来，未放行路径的 401 由 `AuthenticationEntryPoint` 直接产生，不经错误转发，
可以稳定断言。

| 用例 | 断言 |
|---|---|
| 支付宝回调无需认证可达 | 状态码 ≠ 401 |
| 微信回调无需认证可达 | 状态码 ≠ 401 |
| Stripe webhook 仍放行 | 400（缺 `Stripe-Signature` 头）——能拿到 400 就说明已穿过 Security 到达处理器 |
| 其余计费路径仍需认证 | `/billing/usage/reservations` → 401 |
| **未列出的 callbacks 路径不放行** | `/callbacks/paypal`、`/callbacks/alipay/refund`、`/callbacks` 三者均 401 |

最后一条是这组测试真正的价值：它把"只放行两条精确路径"变成可回归的约束。

---

## 4. 验证状态

| 项 | 状态 |
|---|---|
| 控制器 + 两个测试文件语法/类型 | ✅ 对**按真实签名建的**桩编译通过 |
| 参数绑定的实际行为 | ⬜ 需 `mvn verify`（本环境拿不到 Spring 依赖） |
| Security 放行的实际行为 | ⬜ 同上 |

桩这次逐个按真实 API 的**约束**建（上一轮就是因为桩比真货宽松，
漏掉了 `ResponseEntity.badRequest()` 不接受参数）。但桩终究不是真货，
**这两个测试的最终判据是你机器上的 `mvn verify`**。

预期风险点，按可能性排序：

1. `stripeWebhookRemainsPermitted` 断言 400。已确认该端点存在且
   `@RequestHeader("Stripe-Signature")` 是必需的，缺头应为 400；
   若实际是 401 就说明放行被我改坏了，若是别的码则按实际调整。
2. `@RequestParam Map<String, String>` 是否捕获全部表单参数——标准行为，但值得看一眼实测。
3. 三条"未列出路径"是否真是 401 而非 403。若是 403，
   说明 `denyAll` 对匿名请求的翻译与既有测试不同，改断言即可，**结论不变**。

---

## 5. 仍未完成

- 端口 Bean 的注册（`JdbcCallbackPorts` / `JdbcOrderPorts` → `@Configuration`），
  完成后才能给控制器加 `@RestController`
- 回调里接入 `CallbackReplayGuard`（时间戳偏差校验已实现，尚未接线）
- 沙箱全链路、真实交易、真实退款：`NOT_RUN`
- 契约剩余 3 处：`PricingPlanCatalogTest`、`BillingActions.tsx`、`checkout/route.ts`
