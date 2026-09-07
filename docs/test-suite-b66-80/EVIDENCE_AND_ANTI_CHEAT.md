# Evidence 与防作弊规则

1. 结果绑定Source、Environment、Fixture、Artifact和原始日志Hash。
2. 通过结果至少有两个独立Evidence对象和Replay命令。
3. 被测生成器不能同时充当唯一Oracle。
4. 禁止手改`passed/certified`、吞Exit Code、删测试、扩大Tolerance、自动更新Golden或把Skipped算Pass。
5. Source Commit、依赖、工具链或Environment变化后旧Evidence为stale。
6. Provider、Browser、Simulator、Device、Cluster、Cloud、Signing和Runtime声明必须有对应真实执行记录。
