# 支付适配器骨架：已落地的部分

日期：2026-07-28
关联：D-01（中国大陆主体 + 支付宝/微信）、[`PAYMENT_CN_ADAPTER_SPEC.md`](PAYMENT_CN_ADAPTER_SPEC.md)

本轮先做**加密与金额换算内核**——适配器里"错了会直接造成资损或长期挂账"的那部分。
选它先做有两个原因：它只依赖 JDK，可以脱离 Spring 上下文真编译真测试；
而它一旦写错，症状是"验签失败"或"金额对不上"，排查成本极高。

---

## 1. 已实现且已验证

位置：`apps/commercial-api/src/main/java/io/elmos/commercialadapter/payment/`

| 类 | 职责 | 依赖 |
|---|---|---|
| `MoneyConversion` | 分 ↔ 支付宝元字符串 ↔ 微信分，回调金额比对 | 无（纯整数运算） |
| `AlipaySignatureVerifier` | 支付宝异步通知 RSA2 验签 + 待验签串规范化 | JDK `java.security` |
| `WechatPayCallbackCipher` | 微信 APIv3 回调验签 + AES-256-GCM 解密 | JDK `java.security` / `javax.crypto` |

自检：`tooling/payment-crypto-selftest/PaymentCryptoSelfTest.java`

```bash
javac -encoding UTF-8 -Xlint:all -d /tmp/payment-selftest \
  apps/commercial-api/src/main/java/io/elmos/commercialadapter/payment/*.java \
  tooling/payment-crypto-selftest/PaymentCryptoSelfTest.java
java -Dstdout.encoding=UTF-8 -cp /tmp/payment-selftest PaymentCryptoSelfTest
```

**实测结果：46 项断言全部通过**（javac/java 21.0.10），已接入 CI 的 `commercial-gates` job。

### 覆盖的断言

**金额（21 项）**：129.00 / 1290.00 / 0.01 / 0.99 / 1.00 边界；
`105 分 → 1.05` 而不是 `1.5`；0、负数、超上限被拒；
回调解析拒绝三位小数、一位小数、前导空白、科学计数法、负号；
**1–9999 分逐个往返一致 + 大额抽查**——浮点实现会在这里挂；
金额差一分即判定不匹配。

**支付宝（11 项）**：待验签串按参数名升序、空值参数剔除、`sign_type` 剔除；
合法签名通过；金额被篡改验签失败；参数顺序变化不影响结果；
缺签名 / 签名非 Base64 / `sign_type=RSA`(SHA1) / 换公钥 / `null` 入参一律拒绝，
且**非 Base64 时返回 false 而不是抛异常**（异常会被上层误当作系统故障重试）。

**微信支付（14 项）**：`timestamp\nnonce\nbody\n` 三段串验签；
body 改一个字符、timestamp 改、nonce 改、换平台公钥均失败；
AES-256-GCM 解密还原明文；AAD 不匹配 / 密文篡改 / nonce 长度错 / 非 Base64 /
APIv3 密钥错**一律抛异常而不是返回空串**（返回空串会让调用方以为"业务数据为空"，
走进错误分支）；APIv3 密钥长度非 32 在构造时就拒绝。

---

## 2. 写在代码里的三条硬约束

**金额只用整数运算。** 引入 `double` 会出现 `12900 / 100.0 * 100 != 12900`，
一分钱偏差就会导致签名比对失败或对账长期挂账。往返测试专门守这一点。

**验签失败一律 false，不区分"临时故障"。** 上层不得对验签失败做重试——
重试一个伪造回调仍然是伪造回调。

**微信必须先验签再解密。** 顺序反了等于接受任何人构造的报文。
另外验签**不能防重放**：调用方仍需校验 `timestamp` 偏差（建议 ≤5 分钟）
并对 `id` 做幂等去重。这两条写在 `WechatPayCallbackCipher` 的类注释里。

---

## 3. 尚未实现（不要误读为可以收款）

| 项 | 状态 |
|---|---|
| `AlipayCheckoutGateway` / `WechatPayNativeGateway`（下单调用） | 未实现 |
| `PaymentProviderRouter`（按目录选网关，未知即失败关闭） | 未实现 |
| 两个回调 HTTP 端点 | 未实现 |
| 幂等键去重、对账案件写入 | 未实现（复用既有模型，未接线） |
| `paymentProvider` 从 `const` 扩为 `enum`（8 处契约） | 未改 |
| 沙箱全链路 / 真实交易 / 真实退款 | `NOT_RUN` |
| 发票能力 | 未实现 |

**当前状态下系统仍然收不了钱**，这是预期的：商户号还没申请，
定价目录也还是 `DRAFT`。

---

## 4. 下一步的建议顺序

1. `PaymentProviderRouter` + 目录 `paymentProvider` 扩 enum（8 处同批次改完）
2. 下单网关（先做一家，建议支付宝电脑网站支付，前端形态最简单）
3. 回调端点：验签 → 幂等去重 → **金额比对** → 写 provider event → 才更新订阅
4. 沙箱全链路 + 第 7 节的负向验证
5. 另一家提供方

第 3 步的顺序不能调换。特别是**金额比对必须在更新订阅之前**——
`MoneyConversion.matchesExpected` 就是为这一步准备的。
