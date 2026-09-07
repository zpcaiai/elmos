# ETGB v1.1 Coverage Model

## 1. 覆盖边界

“全覆盖”表示对本包声明的 ETGB v1.1 capability model 完整覆盖，不表示未来未知语言、框架和数据库自动获得覆盖。覆盖单元由能力矩阵确定，必须同时具备用例、执行档、Oracle、证据要求和发布优先级。

## 2. 物化规模

| 测试域 | 用例数 | 唯一能力 ID |
|---|---:|---:|
| Spring 老项目现代化 | 3,117 | 222 |
| 全库跨语言转换 | 29,535 | 174 |
| 多语言项目生成 | 1,451 | 91 |
| SQL 方言与 Routine 转换 | 11,761 | 207 |
| 横切生产质量 | 800 | 100 |
| **总计** | **46,664** | **794** |

四条领域线各含一条离线 smoke；因此物化用例数比 capability Cartesian cells 多 4。

## 3. 覆盖维度

### Spring Modernization

`source-archetype × capability × target-profile × validation-mode`，覆盖 Servlet/JSP、Spring XML MVC、Struts 1/2、混合仓库以及 Boot 1/2/3 到 Spring Boot 4 的迁移。

### Cross-Language

`source-language × target-language × capability × repository-profile`，并包含前端到小程序、Objective-C/Swift 与 Android/iOS 的专门路径。禁止用函数级翻译结果替代仓库级构建、依赖、状态和部署验证。

### Project Generation

`requirement-scenario × target-stack × deployment-profile`，另加演化序列、模糊/冲突需求、恶意输入和非功能约束。

### SQL Conversion

`source-dialect × target-dialect × capability × execution-profile`，普通 SQL 与 Routine/Trigger/Package 分开建模，并使用双数据库结果、状态、副作用和事务 Oracle。

### Cross-Cutting

`business-line × scenario × fault-position`：4 × 100 × 2 = 800。两个 fault position 分别代表副作用前和副作用后/提交后，确保恢复、幂等、补偿和计费不只在理想路径验证。

## 4. 强制技术覆盖

每次 coverage check 都必须看到以下技术：

- example-based；
- property-based；
- differential；
- metamorphic；
- fuzz；
- mutation；
- fault-injection；
- temporal-hidden。

缺少任一技术，或缺少任一声明 capability cell，`etgb coverage` 返回非零。

## 5. 优先级与执行档

| 档位 | 目的 | 典型触发 |
|---|---|---|
| smoke | 包与本地 Adapter 自检 | 每次提交 |
| pr | 影响分析 + 风险选择 + 随机对照 | Pull Request |
| nightly | P0/P1 回归、Fuzz、Mutation | 每夜 |
| weekly | 全量公开语料、多 seed、性能 | 每周 |
| release | 冻结候选与全部硬门 | 发布候选 |
| golden | 大型仓库/客户验收 | 商业认证 |
| exhaustive | 全矩阵与扩展生成 | 基准集群 |

PR 选择不得只依赖文件名映射；计划包含强制 smoke、受影响 P0、历史失败、覆盖缺口、模型不确定性以及固定 seed 的未受影响随机对照。Diff 不可用时必须 fail-safe 扩大，而不是返回空计划。

## 6. 完整性判定

覆盖完成要求：

1. 所有矩阵 cell 至少有一个 materialized case；
2. 用例 ID 唯一且可稳定重建；
3. capability ID、优先级、技术和 profiles 可追溯；
4. public corpus 固定 commit；
5. hidden tests 与生成执行环境隔离；
6. release candidate、plan、Oracle、normalization、镜像均冻结 digest；
7. 任何 excluded、unavailable 或 skipped 均显式计入报告。

当前包执行 `etgb coverage` 的期望结果是：`missing_case_count=0`、`unexpected_case_count=0`、五个测试域 coverage 均为 `1.0`。
