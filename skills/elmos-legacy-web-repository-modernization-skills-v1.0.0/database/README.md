# Database

`postgres-schema.sql` 保存控制面与可查询证据索引。

生产实现必须：

- 使用对象存储保存大 artifact；
- 对所有 tenant 表启用 RLS 或等价强隔离；
- 使用事务和 fencing token 防止过期 executor 发布；
- 为 event/audit/cost 表规划分区；
- 对 trace/observation 大数据只保存摘要和 artifact URI；
- 对认证证据设置不可变保留策略；
- 为删除、归档和 GDPR/隐私要求设计单独保留流程。
