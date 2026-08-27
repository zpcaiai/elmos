# 行为等价验证模型

## 1. 等价不是一个布尔值

报告应分维度：

```yaml
route:
protocol:
view:
binding:
validation:
navigation:
session:
security:
transaction:
database:
externalEffects:
concurrency:
performance:
operability:
```

每个维度包含：

- denominator；
- verified；
- equivalent；
- normalizedEquivalent；
- mismatch；
- unknown；
- confidence；
- evidenceRefs。

总分不能掩盖关键路径失败。关键 security/session/transaction/DB/effect 使用 hard gate。

## 2. 三种模式

### STRICT

除非协议/规范允许，不接受差异。

### NORMALIZED

允许显式 normalizer 去除非业务差异，例如：

- trace/request id；
- 无序 JSON object key；
- 合成时间戳；
- 随机 nonce；
- HTML 非语义空白。

### HARDENED

目标系统可有安全增强，但必须：

- 记录 deliberate delta；
- 单独批准；
- 不计入“等价”；
- 验证新策略不会破坏允许业务流程；
- 提供回滚/兼容说明。

## 3. Observation Model

```yaml
observation:
  scenarioId:
  sequenceStep:
  request:
  dispatch:
  response:
  requestStateBefore:
  requestStateAfter:
  sessionBefore:
  sessionAfter:
  dbBefore:
  dbAfter:
  effects:
  securityDecision:
  transaction:
  trace:
  resources:
```

Legacy 与 target 观察使用同一 schema。

## 4. HTTP/视图 Oracle

比较：

- status；
- header multimap；
- `Set-Cookie` 属性；
- content type/charset；
- body bytes；
- JSON/XML 结构；
- HTML DOM、表单字段、链接、错误消息；
- redirect chain；
- forward/include/error dispatch；
- response commit；
- streaming checksum/length。

## 5. Session Oracle

对 session object 使用稳定序列化，不依赖 JVM identity。比较：

- key 集合；
- value 语义；
- creation/invalidation；
- timeout；
- cookie/session id 行为；
- request sequence；
- cluster serialization；
- concurrent mutation。

敏感字段只保存 hash/token。

## 6. 数据库与事务 Oracle

比较：

- 受影响表/行；
- before/after values；
- insert/update/delete count；
- generated key；
- sequence；
- trigger/procedure effect；
- transaction begin/commit/rollback；
- isolation-visible behavior；
- deadlock/retry；
- audit columns。

必要时使用 transaction log、CDC、SQL proxy 或 testcontainer snapshot。

## 7. External Effect Oracle

为 JMS、Kafka、HTTP、file、mail、cache、audit 建立统一 envelope：

```yaml
effect:
  kind:
  destination:
  operation:
  key:
  payloadDigest:
  headers:
  order:
  count:
  idempotencyKey:
  committed:
```

真实外部系统不可重复调用时使用 effect capture/sandbox double。

## 8. Sequence Testing

测试对象是状态机：

```text
S0 --GET form--> S1
S1 --POST invalid--> S1(error)
S1 --POST valid--> S2
S2 --redirect--> S3
S3 --refresh--> S3(no duplicate write)
```

每一步比较 response、session、DB 和 effects。支持：

- 中断；
- 重试；
- 并发 tab；
- session expiration；
- duplicate submit；
- backward navigation；
- exception recovery。

## 9. 并发与性能

等价验证至少覆盖：

- singleton mutable state；
- ThreadLocal cleanup；
- parallel requests on same session；
- async dispatch；
- streaming/client disconnect；
- connection pool exhaustion；
- external timeout；
- redeploy/session restore。

性能比较需要同等数据、配额、warmup 和 observability overhead。

## 10. First-Divergence Diagnosis

不要只记录最终 body 不同。Trace correlation 应定位：

```text
first different pipeline step
first different state mutation
first different SQL/effect
first different navigation decision
```

Repair Agent 只围绕 first divergence 生成最小 patch。

## 11. 认证门建议

### E4

- route coverage = 100%；
- critical endpoint scenario coverage = 100%；
- critical security/session/transaction/DB/effect mismatch = 0；
- critical unknown = 0；
- HTTP behavioral equivalence ≥ 99.9% 或策略定义；
- 其余差异均有 accepted delta。

### E5

在 E4 基础上：

- 性能/容量门通过；
- SBOM/CVE/security scan 通过；
- readiness/liveness/metrics/version/runbook 完成；
- canary/rollback 演练通过；
- 数据迁移/备份恢复通过；
- 证据包可重放；
- 生产环境配置假设已验证。
