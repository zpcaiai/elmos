# P03 Benchmark 与评测计划

## 1. 原则

- Benchmark 必须可复现，固定源码、目标、工具、模型策略、环境、seed 和数据版本。
- 公开 benchmark 是先验；Elmos 最终用 P05 verified outcome 衡量真实产品质量。
- 按场景/规模/难度报告平均值、分位数、失败分布和置信区间。
- 保留 holdout 与客户私有回归集，防止对公开 fixture 过拟合。

## 2. 本包重点评测

- 建立项目生成基准：SaaS/支付/电商/工业/大数据，检查完整生产能力而非页面骨架。
- 建立语言/框架转换矩阵，覆盖类型、泛型、异常、事务、并发、MQ、缓存和权限。
- 对规则执行 property tests：幂等、稳定、版本前置条件和 source map 可逆追踪。
- 对前端/小程序转换执行路由、状态、表单、网络、权限、平台 API 和 UI 行为测试。
- 对 Strangler/shadow/cutover 进行故障注入和数据对账。
- 统计 TODO/stub/unsupported/unknown gap，并验证不能越过完成门。

## 3. 通用场景矩阵

| 维度 | 最小覆盖 |
| --- | --- |
| 仓库规模 | <10K / 10–100K / 100K–1M / >1M LOC |
| 语言 | Java/Kotlin/Python/C#/Go/Rust/C++/PHP/TS/JS/Swift/ObjC/Flutter |
| 框架 | Spring/.NET/FastAPI/Django/Gin/Axum/NestJS/Vue/React/Flutter/小程序 |
| 平台能力 | API/DB/MQ/cache/cron/auth/file/RPC/batch/CI/CD/observability |
| 风险 | 普通 / 金融交易 / 权限安全 / 高并发 / 数据迁移 / 实时控制 |
| 任务 | 新项目生成 / 整库转换 / 局部现代化 / 前端迁移 / 自动修复 |

## 4. 核心指标

- Accuracy：经行为/契约验证的正确能力比例。
- Completeness：源/需求能力的 closure；必须单列 unknown/unsupported/blocked。
- Behavioral equivalence：差分场景 pass、Critical mismatch、side-effect equivalence。
- Executability：install/build/migrate/start/test/deploy 成功率。
- Repair：自动修复成功率、轮次、回归副作用、人工介入。
- Economics：总 token/cost、系统墙钟 ETA、缓存、并行利用率、单位 verified capability 成本。

## 5. 反作弊

- 失败测试不得删除或改弱；验收标准变更需要独立审批和历史对比。
- 不允许只报告成功子集；所有 attempted cases 都进入分母。
- 不允许用模型自评分替代测试/差分/证据。
- 报告所有 unsupported、timeout、budget exhausted、human blocked 和环境失败。
