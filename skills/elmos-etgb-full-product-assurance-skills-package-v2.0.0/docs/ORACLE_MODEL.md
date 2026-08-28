# Oracle Model

## Oracle contract

每个 Oracle 输出：`type`、`passed`、`critical`、标准化规则、容差、第一处差异、原始证据 digest。禁止只输出一个布尔值而无定位信息。

## Normalization policy

允许归一化：请求 ID、时间戳、随机端口、无业务含义的对象地址、明确无序集合。禁止忽略：金额、权限、错误码、事务边界、库存、业务时间、序列、消息数量和任何影响客户结果的字段。

每条 ignore rule 必须：

- 有负责人和理由；
- 被 mutation test 验证不会掩盖业务错误；
- 有到期时间；
- 在 evidence 中可见。

## State comparison

数据库比较要区分：

- 有序/无序表；
- surrogate key 映射；
- Decimal/float 容差；
- timezone 和 collation；
- sequence、trigger、materialized view；
- committed/rolled-back 状态。

外部副作用通过 record/replay proxy 或 shadow endpoint 收集，不允许向真实支付、邮件或生产消息系统发出测试调用。

## Trace comparison

Trace 用 logical event 而不是绝对时间比较：

```text
request.start
transaction.begin
inventory.reserve
payment.authorize
transaction.commit
message.publish
request.finish
```

允许并发中满足 partial order 的合法差异；对必须排序的安全/事务事件使用 happens-before constraint。

## Disclosure Oracle

系统输出的 unsupported/manual manifest 必须覆盖所有未自动处理节点。通过静态扫描、删除/空实现检测、API 差分和隐藏测试交叉验证，避免“未报告删除”。
