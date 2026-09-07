# Execution profiles

## smoke

四个离线 fixture，验证 Runner、JSON 差分、进程双执行、生成项目验收与 SQLite 状态差分。它证明测试基础设施可用，不证明 Elmos 产品已就绪。

## pr

运行 smoke、受影响业务线 P0 micro/fixture、历史事故回归。目标是在短反馈窗口内阻止明显语义退化。

## nightly

增加 P1、属性/变形、故障注入、mutation sampling、多 seed。缓存必须按 source/target/toolchain/model/skill/test digest 完整键控。

## weekly

公共真实仓库、较大语言/SQL 矩阵、长稳、性能和 fuzz campaign。

## release

全矩阵、许可证、安全、证据、重复构建、hidden tests、统计报告和所有硬门。

## golden

固定客户/大型仓库、生产相似数据、影子环境、业务负责人验收。Golden Route 结果不能用公共 benchmark 的成功率替代。

## exhaustive

全组合、长时间 fuzz、mutation、并发调度探索和形式化/模型检查，面向算法与平台专项认证。
