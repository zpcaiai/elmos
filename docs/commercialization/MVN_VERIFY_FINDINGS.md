# `mvn verify` 结果分析与本轮修复

日期：2026-07-28（第四轮）
输入：用户在本机执行的完整 `mvn verify`（Java 21.0.11，72 个模块）

---

## 1. 结论先说

**72 个模块里 71 个 SUCCESS，只有 `elmos-architecture-tests` FAILURE。**

失败的是 `BatchOneToThirteenAssuranceTest.batchMigrationsAreContinuousAndUnique`，
**与本轮支付相关改动无关**，而且**在 V54 出现之前就已经是红的**（第 3 节有证明）。

本轮新增的全部 Java 代码在真实 reactor 中编译通过：

```
elmos-commercial-api ... Compiling 23 source files ... SUCCESS [10.799 s]
  StripeCheckoutGatewayTest / CommercialControllerTest / CommercialPrincipalTest
  BillingApiErrorAdviceTest / CommercialSecurityConfigurationTest
  Tests run: 14, Failures: 0, Errors: 0, Skipped: 1
```

跳过的 1 个是 `SelfServiceBillingApiLiveTest`——需要真实数据库环境变量，
未设置时跳过属预期。

这一条把上一轮的"对桩注解编译通过"升级成了**真实 Maven reactor 编译通过**。

---

## 2. 顺带被抓出来的一个真 bug：桩注解掩盖了 API 不匹配

上一轮我用桩注解编译 `PaymentCallbackController`，桩里写的是：

```java
public static <T> ResponseEntity<T> badRequest(T body);   // ← 我的桩，错的
```

**真实 Spring 的 `ResponseEntity.badRequest()` 不接受参数**，它返回 `BodyBuilder`，
必须再调 `.body(...)`。桩写宽了，于是控制器里的
`ResponseEntity.badRequest("fail")` 编译通过——但放进真实 reactor 必然报错。

把桩改成与真实 API 同形状后立刻暴露：

```
error: method badRequest in class ResponseEntity<T> cannot be applied to given types;
  required: no arguments
  found:    String
```

已修正为 `ResponseEntity.badRequest().body("fail")`，两处。

**教训**：用桩替身验证时，桩必须按真实 API 的**约束**建，而不是按"能编过"建。
桩比真货宽松，等于把编译期检查关掉。这也是我没把这个控制器放进 `apps/` 的原因
——那个判断事后看是对的。

---

## 3. 迁移编号断言：失败早于 V54

### 3.1 失败的断言

```java
Set<String> expected = IntStream.rangeClosed(1, 50)   // ← 上限写死
        .mapToObj(v -> "V" + v).collect(Collectors.toSet());
assertEquals(expected, actual);
```

期望值**硬编码为 V1–V50**。而迁移目录里早已有 V51、V53。

### 3.2 证明它与 V54 无关

| 事实 | 依据 |
|---|---|
| V51 在 git 索引中（早于本次会话） | `git ls-files --error-unmatch` 命中 |
| V53 是工作区未跟踪文件（早于本次会话） | 同上，且非本会话创建 |
| V52 从未存在过 | `git log --all --diff-filter=A -- 'V52*'` 无输出 |

用测试的原始逻辑在**不含 V54** 的迁移目录上复算：

```
目录中: 52 个版本；多出来的: ['V51', 'V53']
assertEquals 结果: 失败
```

**去掉 V54 之后断言依然失败。** 这个测试变红的时点是有人加了 V51/V53 而没同步上限。

### 3.3 为什么它会退化成"计数器"

上限写死意味着：每一次**正常**新增迁移都会让它变红。于是它不再是
"迁移编号是否连续唯一"的守卫，而是"迁移数量是否等于 50"的冻结器。
守卫一旦这样退化，通常的下场是被人 `@Disabled` 掉——那才是真正的损失。

### 3.4 修复：自适应上限 + 显式声明的空缺号

```java
private static final Set<Integer> PERMANENTLY_SKIPPED_MIGRATIONS = Set.of(52);
```

新实现做四件事：

1. **重号仍然失败**——文件名列表与去重集合大小必须相等（Flyway 会因校验和冲突挂掉）
2. **意外缺号仍然失败**——1..max 中除已声明空缺外必须全部存在
3. **已声明的空缺被填上也失败**——声明不会变成陈旧的免死金牌
4. **上限自适应**——正常新增迁移不必再改测试

V52 之所以要永久留空：Flyway 默认禁止乱序，在 V53 已应用的库上插入 V52 会直接失败。
这个理由写进了常量的 Javadoc，而不是只存在于某个人的记忆里。

### 3.5 修复本身的验证

修补后的测试文件**对 JUnit 桩编译通过**（桩这次按真实 API 形状建）。
断言逻辑另用一份独立复刻在合成目录上跑了 7 个场景：

| 场景 | 期望 | 实测 |
|---|---|---|
| 当前版本集（V1–V51, V53, V54，无 V52） | 通过 | PASS |
| **去掉 V54 也通过** | 通过 | PASS |
| 意外删掉 V30 | 失败 | PASS（缺号=[30]） |
| 同一版本号出现两次 | 失败 | PASS |
| 有人补上 V52 | 失败 | PASS（多余=[52]） |
| 正常新增 V55 | 通过 | PASS |
| 连续两个缺号 V40/V41 | 失败 | PASS（缺号=[40,41]） |

第二行是关键：**修复不是为了迁就 V54**。去掉 V54 断言照样通过，
说明改的是"上限写死"这个缺陷本身。第三到第七行说明守卫没有被削弱。

---

## 4. 本轮另外两项

### 4.1 存储函数调用路径：已在真实 schema 上跑通

把仓库的 **53 个迁移（V1–V51、V53）+ V54 全部应用到真实 PostgreSQL**，
得到 1368 张表和真正的 `elmos_activate_subscription_period`，
然后按 `SubscriptionActivator` 的实际语句序列跑端到端。

`tooling/payment-db-verify/verify_subscription_activation.sh`，**19 项断言全过**：

- 首次激活：订阅 ACTIVE、通道 ALIPAY_CHECKOUT、价格 12900、期末正确；
  额度分配取自目录（2000 万 token / 600 Credit）；订阅事件 1 条；订单已关闭
- **重放**：额度分配、订阅事件、订阅行数都不增加（不会重复发额度）
- **续费**：同一订阅 ID 期间被推后，组织下仍只有 1 条订阅，新期间产生新额度分配
- 失败关闭：期末早于期初 → `BILLING_PERIOD_INVALID`；
  免费体验套餐 → `PAID_PLAN_INVALID`（付款不能激活试用）；未知套餐 → 同样拒绝
- **未设 `app.organization_id` → `TENANT_CONTEXT_REQUIRED`**，
  证明必须与关单同事务设置租户上下文
- **事务性**：EXPIRED 订单关单失败后回滚，订阅数不变，没有孤儿订阅

V54 能干净地叠在完整迁移链之上，这一点也顺带验证了。

### 4.2 回调时间戳偏差校验：已实现

`CallbackReplayGuard`，28 项断言全过。

**验签不防重放**：攻击者原样重发一个合法回调，签名依然有效。
幂等台账挡得住窗口内的重复，挡不住台账清理后的旧报文重放。
两者是独立的两道，不能互相替代。

两个方向都卡：过旧拒绝很直观；**过新同样拒绝**——时间戳落在未来意味着
时钟不同步或报文被构造，放行未来时间戳等于把重放窗口延长到"未来那一刻+容差"，
攻击者只要把时间戳往后写就能延长有效期。

容差本身也受约束：0、负数、超过 1 小时一律在构造时拒绝。
**容差就是重放窗口**，把它放大到 1 小时以上等于关掉这道校验。

---

## 5. 仍未验证

- **`PaymentCallbackController` 的 Spring 实际装配与 Security 放行**。
  这一项在本环境无法验证（拿不到 Spring 依赖，Maven Central 被代理拦截）。
  控制器已按真实 API 形状的桩重新编译通过，但参数绑定、
  尤其支付宝表单参数注入的实际行为，只能在能跑 Spring 的环境里测。
  建议做法：加一个 `@WebMvcTest` 用 MockMvc 打两个回调端点，
  断言 form 参数确实注入、微信原始体未被重新序列化、Security 放行范围仅限这两条路径。
- 沙箱全链路、真实交易、真实退款：`NOT_RUN`
- 契约剩余 3 处：`PricingPlanCatalogTest`、`BillingActions.tsx`、`checkout/route.ts`
- PostgreSQL 版本：本轮仍是 16.13；17.5 复跑靠 CI 片段挂进
  `commercial-billing-integration` job

---

## 6. 断言总量

| 套件 | 断言 | 环境 |
|---|---|---|
| `PaymentCryptoSelfTest` | 46 | javac/java 21 |
| `PaymentPipelineSelfTest` | 47 | 同上 |
| `CheckoutGatewaySelfTest` | 33 | 同上 |
| `JdbcPortsSelfTest` | 10 | 同上 |
| `OrderPortsSelfTest` | 8 | 同上 |
| `ReplayGuardSelfTest` | 28 | 同上 |
| `verify_payment_callbacks.sh` | 19 | 真实 PostgreSQL 16.13 |
| `verify_subscription_activation.sh` | 19 | 真实 PostgreSQL 16.13 + 完整迁移链 |
| 迁移编号规则复刻 | 7 | 合成目录 |
| **合计** | **217** | **0 失败** |
