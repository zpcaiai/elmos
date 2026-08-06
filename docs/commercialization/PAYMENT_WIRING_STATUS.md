# 支付回调接线：本轮做完了什么，以及在真环境里发现的三个 bug

日期：2026-07-29（第六轮）
关联：[`PAYMENT_ADAPTER_STATUS.md`](PAYMENT_ADAPTER_STATUS.md)、[`CALLBACK_ENDPOINT_TESTS.md`](CALLBACK_ENDPOINT_TESTS.md)、[`PAYMENT_PERSISTENCE_STATUS.md`](PAYMENT_PERSISTENCE_STATUS.md)

---

## 0. 先说最重要的一件事

本轮拿到了**真实的依赖**，于是很多"上一轮验不了"的东西这一轮验了——
并且验出了三个会让支付**完全收不到钱**的 bug。它们的共同点是：
**都不会报错，都不会在日志里留下异常，症状全是"静默地什么都没发生"。**

真实依赖是从 `apps/commercial-api/target/elmos-commercial-api-0.1.0-SNAPSHOT-exec.jar`
里取出来的 —— 那个 fat jar 的 `BOOT-INF/lib/` 就是一整套 Spring 6.2.8 /
Boot 3.5.3 / Security 6.5.1 / Jackson 2.19.1。Maven Central 被代理拦着，
但需要的 jar 本来就在仓库里躺着。

---

## 1. Bug 一：控制器的请求映射根本不会建立

### 症状

两个回调路径一律 **404**。Bean 注册成功，Security 放行成功，应用启动无异常，
日志干净。提供方持续重发，直到有人去翻 Nginx 访问日志。

### 原因

上一轮的控制器刻意不加 stereotype 注解，只留类型级 `@RequestMapping`，
依据是"`RequestMappingHandlerMapping.isHandler()` 认 `@Controller` **或**
`@RequestMapping`"。这个依据在 Spring Framework 6.2 上**已经不成立**：

```java
// spring-webmvc 6.2.8，反编译自 jar
protected boolean isHandler(Class<?> beanType) {
    return AnnotatedElementUtils.hasAnnotation(beanType, Controller.class);
}
```

`@RequestMapping` 那一支被移除了。

### 怎么发现的

`SpringWiringSelfTest` 用真实的 `RequestMappingHandlerMapping` 跑出
`handlerMethods = 0`，再反编译确认。**纯读文档不会发现**——这个变更在
迁移说明里的位置并不显眼，而"@RequestMapping 就够了"是流传很广的说法。

### 修法

控制器改成正常的、被组件扫描的 `@RestController`。随之而来的问题是
"它会被无条件注册，而端口 Bean 只在配了数据库时才有"——解法是把六个依赖
收成一个 `PaymentCallbackPorts`，控制器注入 `ObjectProvider<PaymentCallbackPorts>`：

| 环境 | 行为 |
|---|---|
| 配了 `ELMOS_COMMERCIAL_DATABASE_URL` | 正常走管线 |
| 没配 | 端点存在、映射建立，调用返回 **503** |

比原计划的"没配就没有端点"更好：404 会让人以为路径写错了，503 说的是
"这台机器没配置收款"。两者都不会让应用启动失败。

---

## 2. Bug 二：订单查询在真库上永远返回 0 行

### 症状

**每一笔回调都判成 `ORDER_UNKNOWN`**，全部落进 `payment_unmatched_callbacks`，
一个订阅都不会开通。回调端点返回 400，提供方无限重发。
同样没有异常——`ORDER_UNKNOWN` 是管线的正常分支。

### 原因

V49 第 419 行起的租户表清单里包含 `payment_checkout_sessions`：

```sql
ALTER TABLE payment_checkout_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_checkout_sessions FORCE  ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON payment_checkout_sessions
    USING (organization_id = current_setting('app.organization_id', true));
```

而回调到达时**组织是未知的**——组织正是要靠 `out_trade_no` 查订单才能确定。
设不了 `app.organization_id`，策略就求值成 `organization_id = NULL`，恒为 NULL。

`JdbcOrderPorts` 的注释里其实写着"若该表启用了强制 RLS，本查询必须以专用角色执行"。
它**确实**已经启用了。那句话被写成了条件句，而它是个事实。

### 修法：V62 订单目录

不给运行角色开 `BYPASSRLS`（那等于对整张表关掉租户隔离，而那张表带
`actor_id`、`idempotency_key`、`request_hash`）。改为单列一张
**只含解析所必需最小列**的无 RLS 目录表，由触发器自动维护：

```
订单号 → (组织, 套餐, 金额, 状态)
```

跨租户可读的信息被压缩成这一个映射，没有别的。而订单号本来就是我们发给
支付提供方、再由提供方回传的东西。

回填那一段用"同事务内临时摘掉 FORCE → 回填 → 立刻装回 → 断言已装回"，
不用 `SET row_security = off`（那在 FORCE RLS 表上会直接报错，除非角色带 BYPASSRLS）。

### 证据

`tooling/payment-db-verify/verify_order_directory.sh`，19 条断言，PostgreSQL 16.13 全通过。
其中第 2 节**先复现故障**再验修复：

```
== 2. 复现故障：无租户上下文时直接查订单表 ==
  [PASS] 无上下文直查 payment_checkout_sessions 返回 0 行
```

> 这个脚本第一次跑的时候是"失败"的——因为我用 `postgres` 超级用户执行，
> 超级用户绕过 RLS，故障复现不出来。**不是实现对了，是测试把要验的东西验没了。**
> 现在脚本自己建一个非超级用户的 `elmos_billing_runtime` 角色并 `SET ROLE`。

---

## 3. Bug 三：写事件与开对账案件同样会被 RLS 拒绝

`payment_provider_events` 和 `payment_reconciliation_cases` 也在同一份强制 RLS 清单里。

- `providerEventStore` 原先签名是 `(DataSource, String organizationId)`，
  把组织**固定在 Bean 上**。多租户下所有租户的支付事件会记到同一个组织名下；
  而且它没设租户上下文，`WITH CHECK` 会直接拒绝插入。
- `insertCase`（金额不符时开案件）同样没设上下文，于是金额不符时不但不开案件，
  还会抛异常——把一个"应当留痕并人工介入"的情形变成"回调处理失败、提供方无限重发"。

修法：`ProviderEventStore.record` 增加 `LocalOrder` 参数（管线第 3 步已经解析出订单，
不需要额外查询），两处写入都改为在同一事务内先 `set_config('app.organization_id', ..., true)`。

---

## 4. 顺带补上的两个业务缺口

这两个不是"接线"问题，是原设计里缺的一环。

### 4.1 关单/退款通知会被当成付款成功

同一笔订单会收到多次通知：`WAIT_BUYER_PAY` → `TRADE_SUCCESS` → 可能还有
`TRADE_CLOSED`（超时关闭或已全额退款）；微信侧还有 `REFUND`。

这些通知**签名都是真的**、事件 ID 都是新的、金额字段都和订单一致——
**验签、幂等、金额比对，没有一道拦得住它们**。

管线因此新增一步：事件落库之后、动订阅之前判定
`ProviderAdapter.indicatesPaymentSuccess`，非成功事件返回 `NOT_A_PAYMENT_SUCCESS`
并对提供方回 200（我们确实正确处理了这条通知，只是不该激活订阅）。

### 4.2 别的商户的合法通知，在我们这里验签能过

支付宝的异步通知由**支付宝的私钥**签名，公钥是所有商户共用的同一把；
微信的平台证书同理。也就是说，发给别的商户的一份**完全合法**的通知，
拿到我们这里验签**照样通过**。

唯一的归属凭据是支付宝的 `app_id` / 微信的 `mchid`。两个适配器都在验签前
先比对归属（字符串比较比 RSA 便宜，而且归属不符时根本不需要知道签名对不对）。

`CallbackAdapterSelfTest` 里对这条有正反两组断言——只有反例不够，
"什么都验不过"也能让反例通过：

```
[PASS] 支付宝：签名真实但 app_id 是别人的 -> 拒绝
[PASS] 支付宝：换回自家 app_id 并重签 -> 通过
```

---

## 5. 重放防护接线了

`CallbackReplayGuard` 上一轮实现了但没接。现在作为管线的**第 0 步**：

- 微信读 `Wechatpay-Timestamp`（Unix 秒）
- 支付宝读 `notify_time`，按 **Asia/Shanghai** 解析（报文里不带时区；
  误按 UTC 解析会偏 8 小时，把每一条通知都判成陈旧）

放在验签**之前**看起来违反"不信任未验签数据"，区别在方向：
**只用它拒绝，从不用它放行。** 基于伪造输入拒绝是安全的（最坏是拒了本来就该被
验签拒掉的东西）；基于伪造输入放行才危险。换来的是伪造报文在做 RSA 之前就出局。

容差默认 5 分钟，可配但有硬上限：`CallbackReplayGuard` 的构造函数拒绝超过 1 小时的值，
因为**容差就是重放窗口**。`SpringWiringSelfTest` 里有一条断言专门盯这个：
配成 6 小时时上下文必须起不来。

---

## 6. 前端：跳转与扫码是两种交互

`BillingActions.tsx` 原先写死 `hostname.endsWith(".stripe.com")` 并对所有用户显示
"跳转至 Stripe 安全结账"。现在按通道分流：

| 通道 | 交互 | 可信域 |
|---|---|---|
| `STRIPE_CHECKOUT` | 跳转 | `stripe.com` / `*.stripe.com` |
| `ALIPAY_CHECKOUT` | 跳转 | `openapi.alipay.com`、`openapi.alipaydev.com`（沙箱） |
| `WECHAT_PAY_NATIVE` | **本地渲染二维码** | 不跳转 |

微信 Native 的 `code_url` 形如 `weixin://wxpay/bizpayurl?pr=...`。
`window.location.assign` 过去在桌面浏览器上**什么也不会发生**，用户只看到页面卡住。

`checkout/route.ts` 不再原样透传成功响应，而是先确认它**恰好**是
`checkoutUrl` 或 `qrCodeUrl` 之一。两个都没有、或两个都有，一律 502 + 明确错误码。
透传意味着上游一旦返回一个两者皆无的"成功"响应，前端只会显示一个什么都不做的按钮。

### 6.1 二维码是自己编的，而且验过

没有装 `qrcode` 这个 npm 包——加运行时依赖是仓库主人的决定。
`app/lib/qrCode.ts` 是一个**范围严格收窄**的实现：只有字节模式、只有纠错级别 M、
只有版本 1–10。超出范围一律抛错，不做静默降级。

**一张画错的二维码肉眼分辨不出来，而用户会去扫它。** 所以验证用两种互相独立的判据：

```
A. 逐模块比对参考实现：200/200 一致      (25 段文本 × 8 个掩码，版本 1–10)
B. OpenCV 解码回原文：25/25 通过
C. SVG 渲染约束：7/7 通过
```

A 用 Python `qrcode` 库做参考，**强制掩码**后逐位比对——把"掩码选择"这个纯启发式
的差异排除掉，验的是编码、纠错、分块交错、模块布局、格式信息。
B 用真实扫描器，验"扫得出来"。只有 A 不够（两边可能一起错），只有 B 也不够
（检测器对某些掩码有识别局限，通过不代表编码对）。

写的过程中踩了两个坑，都记在代码注释里：

1. **列对跳过第 6 列时必须改写循环变量本身**。只在本轮换个列号，
   下一轮的列对就从 `(3,2)` 变成 `(4,3)`，左半边数据位全部错位。
   表现是码画得出来、结构全对、只有左侧十几个模块不同——肉眼完全看不出来。
2. **格式信息的坐标序**。常被引用的 nayuki 参考实现那段是 `setFunctionModule(8, i, bit)`，
   而那个方法签名是 `(x, y)` 不是 `(row, col)`。照字面抄会把格式信息整体转置，
   于是扫描器读到的纠错级别与掩码号是错的，整张码解不出来——而它看上去就是一张正常的二维码。

---

## 7. 本轮的证据清单

| 验证 | 数量 | 环境 | 结果 |
|---|---|---|---|
| `SpringWiringSelfTest` | 29 | **真实 Spring 6.2.8 / Boot 3.5.3** | 通过 |
| `CallbackAdapterSelfTest` | 43 | 真实 RSA + AES-256-GCM | 通过 |
| `PaymentPipelineSelfTest` | 47 | JDK | 通过 |
| `PaymentCryptoSelfTest` | 46 | 真实密钥 | 通过 |
| `CheckoutGatewaySelfTest` | 33 | 真实签名 | 通过 |
| `ReplayGuardSelfTest` | 28 | JDK | 通过 |
| `JdbcPortsSelfTest` / `OrderPortsSelfTest` | 18 | JDK | 通过 |
| `CatalogContractSelfTest` | 12 | 真实目录 JSON | 通过 |
| `verify_order_directory.sh` | 19 | **真实 PostgreSQL 16.13** | 通过 |
| `verify_payment_callbacks.sh` | 19 | 真实 PostgreSQL 16.13 | 通过（上一轮） |
| `verify_subscription_activation.sh` | 19 | 真实 PostgreSQL 16.13 | 通过（上一轮） |
| `qrCode.verify.mjs` | 232 | 参考实现 + OpenCV | 通过 |
| **合计** | **345** | | **0 失败** |

---

## 8. 仍然没做 / 仍然验不了

### 8.1 外部依赖，一步没动

营业执照 / 对公账户 / ICP 备案 / 支付宝与微信商户号 / 独立安全评审 /
沙箱全链路 / 真实交易 / 真实退款：全部 `NOT_RUN`。

**没有营业执照，这条链一步都启动不了。** 代码写得再完整也收不到钱。

### 8.2 D-04 仍然是最急的非工程项

16 个成本输入还没填，`costValidationStatus` 还是 `NOT_RUN`，
定价目录还是 `DRAFT`。毛利未知的情况下，上面这些工程工作决定的只是
"能不能收钱"，不是"该不该按这个价收"。

---

## 9. 合入前请做的四件事

1. `mvn -pl apps/commercial-api -am test` —— 让那两个 MockMvc 测试真正跑一次
2. `mvn verify` 全量 —— 本轮改了管线接口（`ProviderEventStore.record` 增参），
   `PaymentPipelineSelfTest` 已同步，但仓库里可能还有别的实现
3. `python3 scripts/commercial/append_ci_gates.py` —— 追加两个 CI job（幂等，可重复运行）
4. 在 PostgreSQL 17.5 上复跑三个 `verify_*.sh` —— 上面那个 CI job 会自动做，
   但第一次最好手动看一眼

---

## 10. 第七轮补记：结账端点已改完，Security 也实跑了

### 10.1 我上一轮拒绝改结账端点的理由是错的

原话是"那个方法被现有测试覆盖，改一个我无法验证的支付主路径不合适"。
**这个判断我没有核实就下了。** 实际情况：

```
$ grep -rln "SelfServiceBillingController" apps/commercial-api/src/test/ modules/
（无输出）
```

没有任何测试实例化过它。唯一沾边的 `SelfServiceBillingApiLiveTest` 用
`@EnabledIfEnvironmentVariable(named = "ELMOS_COMMERCIAL_DATABASE_URL", ...)` 门控，
常规 CI 里直接跳过，而且它也没打 `/checkout`。

改动风险远低于我说的。**先核实再判断，不要把谨慎当成结论。**

### 10.2 结账端点现在按通道分流

```java
PaymentProvider provider = paymentRouter.active();
assertChannelConfigured(provider);
...
if (provider == PaymentProvider.STRIPE_CHECKOUT) {
    return stripeCheckout(principal, request, exactKey);
}
return chinaCheckout(principal, request, exactKey, checkoutSessionId, provider, prepared);
```

Stripe 分支的代码**逐字保持原样**——新通道出问题不该连累既有路径。

四个要点：

1. **`out_trade_no` 就是 `checkout_session_id`。** 原实现把
   `"checkout-" + UUID.randomUUID()` 内联生成后就丢掉了；现在必须留住并传给网关，
   因为回调回来是靠它反查订单的（`JdbcOrderPorts.orderLookup`）。
   两边不一致 = 每一笔付款都变成无主回调。有专门的断言盯这一条。

2. **金额从目录取，不接受客户端传入。**
   `plan.price().amount().movePointRight(2).longValueExact()`——
   用 `longValueExact` 而不是 `longValue`，出现小数时抛异常而不是悄悄截断。

3. **下单失败怎么记账，取决于"有没有发出过请求"。**
   为此在 `CheckoutGateway` 上加了 `contactsProviderDuringPrepare()`：
   - 支付宝 `false`（纯本地签名）→ 失败就标记 `FAILED`，结果是确定的
   - 微信 `true`（发过 HTTPS）→ 结果未知，必须进对账；
     标记 `FAILED` 等于单方面认定"对面没建单"，那正是产生挂账的方式

   写成接口方法而不是在调用方按通道名 if-else：新增通道时作者**必须**回答这个问题。

4. **响应新增 `CheckoutHandoffResponse`**，带 `paymentProvider` +
   互斥的 `checkoutUrl` / `qrCodeUrl`，与前端 `checkout/route.ts` 的校验对齐。

### 10.3 怎么验的

`CheckoutRoutingSelfTest` 跑两遍，**两个 JVM**（目录是 `static final`，一次性加载）：

| 轮次 | 目录 | 断言 |
|---|---|---|
| 1 | 仓库里的真实目录（DRAFT） | 三种通道全部 503 `PRICING_CATALOG_NOT_ORDERABLE`，一张订单都没建 —— 6 条 |
| 2 | 状态位改成已配置的副本 | 分流、金额、订单号、两种失败记账、未配置通道、Stripe 分支、live 开关 —— 26 条 |

第 2 轮把 `catalogVersion` 保持不变（改了加载时就会被拒），只翻四个状态位，
放在 classpath 更前面。这样测的是**真正的入口方法**，包含 `requireOrderable()` 本身，
而不是绕过它去调私有方法。第 1 轮的存在是为了保证"把门打开"这个做法
没有掩盖真实行为。

### 10.4 Security 放行实跑了

上一轮说"spring-test 是 test scope，拿不到"。这轮从 `~/.m2` 取到了
spring-test 6.2.8 / JUnit 5.12.2 / hamcrest（就在这台机器上，只是之前没去拿）。

**`PaymentCallbackBindingTest` 6 个用例真跑，全过。** 不是"对桩编译通过"——
form 参数注入、微信原始体逐字节保留、缺签名头时 Spring 直接 400 且管线不被调用，
全是真实的 `RequestMappingHandlerAdapter` 与真实参数解析器给出的结果。

`SecurityFilterChainSelfTest` 用 `AnnotationConfigWebApplicationContext` +
`MockServletContext` 装配 `CommercialSecurityConfiguration` 里那**同一个真实的
`SecurityFilterChain` Bean**，再用 `DelegatingFilterProxy` 打请求：

```
[PASS] 支付宝回调被放行（状态 503，只要不是 401）
[PASS] 微信回调被放行（状态 503，只要不是 401）
[PASS] /commercial/v1/billing/callbacks/paypal 被拦下（状态 401）
[PASS] /commercial/v1/billing/callbacks/alipay/refund 被拦下（状态 401）
[PASS] /commercial/v1/billing/callbacks 被拦下（状态 401）
[PASS] /billing/usage/reservations 需要认证（状态 401）
[PASS] 定价目录仍然公开（状态 404，不是 401）
```

两点值得记下来：

- 回调路径返回 **503** 而不是 200/400，因为这个上下文里没注册
  `PaymentCallbackPorts`。这恰好在真实过滤器链上端到端印证了
  "没配数据库 → 端点在、放行、失败关闭"这条设计。
- `denyAll()` 与 `authenticated()` 对匿名请求**都返回 401**。
  这解答了 `CALLBACK_ENDPOINT_TESTS.md` 第 5 节列的第 3 号风险——
  仓库里 `PaymentCallbackSecurityTest` 断言 `isUnauthorized()` 是对的，不用改。

### 10.5 自检现在可以一条命令复跑

`tooling/payment-crypto-selftest/run_selftests.sh`：自己从
`apps/commercial-api/target/*-exec.jar` 的 `BOOT-INF/lib` 取依赖，
不联网、不需要 Maven Central，编译并依次跑完 12 组。
前置条件不满足时退出码 3 并打印 `NOT_RUN`，不会伪装成通过。

---

## 11. 证据总账（第六 + 第七轮）

| 验证 | 数量 | 环境 |
|---|---|---|
| `PaymentCryptoSelfTest` | 46 | 真实 RSA / AES 密钥 |
| `CheckoutGatewaySelfTest` | 33 | 真实签名 |
| `JdbcPortsSelfTest` / `OrderPortsSelfTest` | 18 | JDK |
| `ReplayGuardSelfTest` | 28 | JDK |
| `PaymentPipelineSelfTest` | 47 | JDK |
| `CallbackAdapterSelfTest` | 43 | 真实 RSA + AES-256-GCM |
| `CatalogContractSelfTest` | 12 | 真实目录 JSON |
| `SpringWiringSelfTest` | 29 | **真实 Spring 6.2.8 / Boot 3.5.3** |
| `SecurityFilterChainSelfTest` | 10 | **真实 Security 6.5.1 过滤器链** |
| `CheckoutRoutingSelfTest`（两轮） | 32 | 真实控制器 + 真实目录加载 |
| `PaymentCallbackBindingTest` | 6 | **真实 JUnit 5.12.2 + spring-test 6.2.8** |
| `verify_order_directory.sh` | 19 | **真实 PostgreSQL 16.13** |
| `verify_payment_callbacks.sh` | 19 | 真实 PostgreSQL 16.13 |
| `verify_subscription_activation.sh` | 19 | 真实 PostgreSQL 16.13 |
| `qrCode.verify.mjs` | 232 | Python `qrcode` 参考实现 + OpenCV 解码 |
| **合计** | **593** | **0 失败** |

### 仍然只能靠 `mvn verify` 的

`PaymentCallbackSecurityTest` 用的是 `@SpringBootTest`，需要 spring-boot-test
（我没有为它再申请一次目录授权——`SecurityFilterChainSelfTest` 已经把同一批
放行规则在真实过滤器链上验过了，边际收益不足以再打扰一次）。

全量 `mvn verify` 也还没跑过。本轮改了两个公开签名：

- `PaymentCallbackPipeline.ProviderEventStore.record` 增加 `LocalOrder` 参数
- `PaymentProviderRouter.CheckoutGateway` 增加 `contactsProviderDuringPrepare()`
- `SelfServiceBillingController` 构造函数增加 `PaymentProviderRouter`

仓库内已知的实现都同步了，但只有全量构建能确认没有遗漏。
