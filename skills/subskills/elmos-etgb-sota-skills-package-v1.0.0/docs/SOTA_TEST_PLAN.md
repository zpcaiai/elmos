# Elmos ETGB SOTA 全面测试计划

## 1. 结论

Elmos 的四条业务线都属于**程序变换系统**，其风险不是“代码不好看”，而是目标产物在边界条件、事务、安全、并发、故障恢复或长期演化中产生未被发现的语义偏移。因此，SOTA 测试体系必须从传统的“生成后编译和跑原测试”升级为：

> **能力矩阵驱动 + 多 Oracle + 源/目标双运行 + 状态与副作用差分 + 属性/变形/模糊/变异 + 故障注入 + 时间切分隐藏测试 + 可审计发布证据。**

ETGB v1.0 把这个原则落实为 46,376 条具体用例，覆盖 694 个业务能力 ID，另以横切矩阵验证恢复、安全、隔离、成本、缓存、审计和基准治理。

## 2. 测试目标与非目标

### 2.1 目标

1. 证明 Elmos 声称成功的转换或生成满足可观察行为契约。
2. 把静默语义错误压缩到 P0 为零。
3. 在不能等价转换时，验证系统能正确识别、解释、隔离并升级人工处理。
4. 对模型、Prompt、Skill、工具链、依赖和执行环境变更提供稳定回归信号。
5. 产出客户可验收、审计可复现、发布可追责的 evidence bundle。
6. 直接测量机器 wall-clock、token、credit、缓存命中和重试成本。

### 2.2 非目标

- 不用文本相似度代替语义正确性。
- 不把“编译通过”当作最终成功。
- 不把另一个 LLM 的主观评分当作唯一 Oracle。
- 不追求所有目标代码与人工实现同构；允许架构适配，但必须证明契约等价并公开差异。
- 不宣称覆盖未来未知技术；“全覆盖”严格限定为声明的 ETGB v1.0 capability model。

## 3. Benchmark Pyramid

| 层级 | 内容 | 主要用途 | 典型 Oracle |
|---|---|---|---|
| L0 | 单语义点、SQL 构造、API 映射 | 快速定位回归 | 属性、AST、编译、微分执行 |
| L1 | 组合 Fixture | 验证框架与运行时组合 | HTTP、DB 状态、事务、UI |
| L2 | 小/中型真实仓库 | 依赖、配置、资源与构建 | 原测试、隐藏测试、双运行 |
| L3 | 演化序列与中型 Golden Route | 增量修改、回滚、兼容性 | 旧+新验收、迁移、回放 |
| L4 | 50万～100万+ LOC 大型仓库 | 商业认证 | 分阶段影子、全证据、SLA |

每个上层失败必须能下钻到下层 capability cell；否则测试只能告诉团队“失败了”，不能告诉团队“为什么失败”。

## 4. 多 Oracle 模型

一个 P0 case 至少需要四类证据，关键链路应覆盖八类：

1. **O0 静态结构 Oracle**：文件/模块、API、schema、路由、依赖、配置、权限模型。
2. **O1 构建与原测试 Oracle**：clean build、原测试、目标测试、重复构建。
3. **O2 行为 Oracle**：HTTP/RPC/UI/CLI/函数输出、错误类型和错误结构。
4. **O3 状态与副作用 Oracle**：数据库、序列、消息、缓存、文件、外部调用、审计日志。
5. **O4 Trace/并发 Oracle**：事务边界、锁、事件顺序、重试、幂等、取消、超时。
6. **O5 安全 Oracle**：认证、授权、CSRF/CORS、注入、秘密、租户隔离、供应链。
7. **O6 性能与资源 Oracle**：P50/P95/P99、吞吐、内存、启动、扫描字节、成本。
8. **O7 Disclosure Oracle**：不支持项、假设、人工修改、风险、降级必须完整披露。

Oracle 冲突时，按“业务契约/运行行为 > 状态副作用 > 原测试 > 静态结构 > 文本相似度”的证据优先级处理；原系统已知缺陷必须在 baseline contract 中显式标记，不应被无条件复制。

## 5. SOTA 测试技术组合

### 5.1 Example-based

固定输入、固定环境和明确期望，适合 P0 事故回归与业务验收。每个线上缺陷必须沉淀成最小回归 fixture 和真实仓库回放用例。

### 5.2 Property-based

围绕类型、Schema、API 和状态机生成大量输入，验证不变量：金额守恒、库存不为负、权限不扩张、序列单调、分页无重复、序列化 round-trip 等。失败样本必须 shrink 为最小反例。

### 5.3 Differential execution

在源与目标环境运行同一规范化 workload，比较：

- 返回值/响应；
- 异常与错误码；
- 数据库最终状态；
- 消息和外部副作用；
- 事务与事件 trace；
- 性能边界。

这是 Spring 现代化、跨语言和 SQL 转换的主 Oracle。

### 5.4 Metamorphic testing

当精确标准答案昂贵时，验证变形关系，例如：

- 重排无序输入不改变结果集合；
- 等价 SQL 重写应产生相同结果；
- 添加不相关模块不应改变既有 API；
- 翻译后再进行行为保持型重构，输出契约不变；
- 相同生成需求改写措辞，关键验收结果不变；
- 数据分片后合并结果等于整体执行。

### 5.5 Grammar/AST/State-machine fuzzing

对 Java/SQL/JSON/OpenAPI/配置/归档输入按语法生成；对 API、事务、Session、消息和项目演化按状态机生成。崩溃、挂起、未报告丢失、非确定性和跨租户污染都视为缺陷，并自动 reduction。

### 5.6 Mutation testing

主动注入能够模拟真实转换错误的 mutant：

- 删除 rollback；
- 交换 Filter/Interceptor 顺序；
- 把 Decimal 改为 float；
- 去掉权限判断；
- 把 `LEFT JOIN` 改为 `INNER JOIN`；
- 修改窗口 frame；
- 忽略 timezone；
- 删除缓存失效；
- 破坏生成项目的幂等键。

隐藏测试必须杀死高风险 mutant。若 mutant 存活，说明测试套件对该语义没有真实检测力。

### 5.7 Fault injection

在 inventory、plan、generate/transform、build、test、publish、计费、上传、回写数据库等每个 phase boundary，以及副作用发生前后注入失败，验证暂停、恢复、取消、幂等、fencing、回滚和审计完整性。

### 5.8 Temporal split 与 hidden tests

- 语料按 commit 时间切分，模型/Skill 不得访问评测之后的修复实现。
- hidden tests 放在独立评测服务，生成 Agent 不可读。
- 对公开 benchmark 增加私有变体、参数扰动、等价重写和新故障组合。
- 记录模型不可变版本、知识截止、Prompt/Skill digest，防止基准记忆被误报为泛化能力。

## 6. Spring 老项目现代化计划

### 6.1 Baseline capture

在任何修改前完成：

1. 构建依赖、模块、运行时、容器和外部系统清点；
2. 路由、请求绑定、Session/Cookie、Filter/Interceptor、视图、异常映射探测；
3. Bean graph、配置优先级、Profile 和生命周期记录；
4. 数据库 schema、SQL、事务传播/隔离、锁和触发器记录；
5. 安全规则、负向授权、CSRF/CORS、会话策略记录；
6. 关键业务 workload 录制与 DB/消息/文件快照；
7. 原测试的可靠性和覆盖盲区评估。

### 6.2 迁移路径

矩阵包含 Servlet/JSP/web.xml、Spring XML MVC、Struts 1、Struts 2、三者混合、Boot 1、Boot 2、Boot 3 到 Boot 4。每个路径覆盖 build、`javax→jakarta`、DI、Web、视图、数据事务、安全、集成、运维和测试迁移。

### 6.3 双运行验证

- 同一请求录制重放到源/目标；
- 动态值按规则归一化，不可粗暴忽略业务字段；
- 比较 HTTP、DOM、Session、DB、消息、外部调用与 trace；
- 事务关键场景运行强制故障，证明 rollback 和 isolation；
- 安全规则必须运行允许/拒绝矩阵，不能只验证正常登录。

### 6.4 Golden Route

P0 推荐顺序：

1. Spring Framework PetClinic：Plain Spring/JSP/XML → Boot 4；
2. Struts Examples：原子特性 fixture；
3. Broadleaf LegacyDemoSite：旧商业应用；
4. Apache Roller：WAR/JSP/Struts/Spring/Security/JPA 组合；
5. ≥3 个客户或内部 >500k LOC 仓库，其中 ≥1 个 >1M LOC。

## 7. 全库跨语言转换计划

### 7.1 不以文件翻译为单位

先构建 Repository Semantic Graph：模块、公共 API、类型、调用、数据、消息、配置、构建、部署、测试和外部依赖。目标仓库必须重新建立目标语言的惯用构建与依赖结构，同时保持业务契约。

### 7.2 语义不匹配处理

每个不一一对应语义必须产生明确 adaptation record：

- Java `synchronized`、Go channel、Rust ownership、C# LINQ、Python monkey patch、Node event loop 等；
- 选择目标原语、兼容层、架构改造或显式拒绝；
- 给出风险、证据、性能影响和人工审查点；
- 绝不以删除功能换取编译通过。

### 7.3 验证层

1. 目标 clean build；
2. 公共 API、Schema、协议和目录/模块契约；
3. 原测试移植与独立隐藏测试；
4. 源/目标 differential workload；
5. 属性、并发调度和资源释放；
6. round-trip probe 只作为诊断，不作为唯一正确性标准；
7. 多随机种子、多模型重复运行，报告均值、方差和最差分位。

矩阵声明 113 条语言/技术路径，覆盖后端 10 种语言的全部有向组合、Vue/React/Flutter 到四类小程序、Vue2→Vue3、React↔Flutter，以及 Objective-C/Swift/Android Kotlin 方向。

## 8. 多语言项目生成计划

### 8.1 Requirement Contract first

生成前必须把自然语言需求编译为：Actor、功能需求、质量属性、数据约束、错误语义、安全规则、验收测试、假设、冲突、非目标和演化序列。缺失条件必须提问或采用安全、可见、可修改的假设。

### 8.2 三类测试任务

- **Greenfield**：55 类项目模板 × 10 个技术栈 × 本地 Docker/Kubernetes 生产档。
- **Evolution**：字段/Schema、API 版本、认证、数据库、拆分服务、回滚等 20 类增量修改。
- **Adversarial requirements**：模糊、冲突、不可能约束、危险安全请求、秘密、许可证、Prompt Injection 等 15 类。

### 8.3 验证

- clean-room 构建、启动和部署；
- 黑盒验收测试由独立测试生成器/人工基准提供；
- 结构和架构规则只作为补充，不取代行为；
- 旧版本全部验收 + 新版本新增验收；
- Schema forward/backward、蓝绿/回滚、事件兼容；
- SAST、依赖、秘密、IaC 和运行时负向安全测试；
- 多 seed 生成，测量成功率、方差、修复回合、成本和 wall-clock。

## 9. SQL 方言与 Routine 转换计划

### 9.1 分层

1. Lexer/parser/AST；
2. 类型、表达式和查询；
3. DML/DDL；
4. Procedure/function/trigger/package；
5. 事务、并发和错误；
6. 分析平台对象、成本与权限。

### 9.2 双数据库 Oracle

同一规范化数据集分别装入 source/target，执行源 SQL/routine 和转换结果，比较：

- 有序或无序 result set；
- Decimal、timezone、collation 和 NULL；
- 所有表、序列、触发器副作用；
- OUT/INOUT 参数、错误码和异常 scope；
- commit/rollback/savepoint 与多会话 anomaly；
- 执行计划只是性能证据，不能替代结果正确性。

### 9.3 Routine 重点

P0 覆盖 cursor、dynamic SQL、异常、temp table、trigger、transaction/savepoint、package state、`%TYPE/%ROWTYPE`、bulk collect/forall、autonomous transaction adaptation、security definer/invoker 和 mutating-table 行为。

### 9.4 Fuzz 和 reduction

- 语法生成和数据库状态生成；
- 等价查询变形；
- 多 DBMS differential；
- 失败 query 自动 reduction；
- 每个修复进入固定 regression corpus。

## 10. 横切生产质量

### 10.1 Harness 与恢复

测试 pause/resume/cancel、断网、进程崩溃、宿主重启、数据库 failover、重复消息、部分上传、磁盘满、超时、限流和上下文截断。所有副作用需要 idempotency key、ownership、fencing 和可回放日志。

### 10.2 多租户与计费

- 账号并发上限和公平调度；
- workspace、缓存、artifact、secret、trace、账单隔离；
- token/credit 预扣、实时消耗、失败退款/结算；
- wall-clock ETA 与实际误差；
- 取消、重试、缓存命中不能重复计费。

### 10.3 安全与供应链

所有不可信仓库在无生产凭据的短生命周期沙箱中执行；默认断网、最小工具权限、只读基础镜像、资源限制、日志脱敏。公共仓库必须固定 commit、许可证批准、依赖锁定和恶意构建扫描。

## 11. 指标

### 11.1 核心指标

\[
SSER = \frac{\text{声称成功但隐藏 Oracle 发现语义错误的 case}}{\text{所有声称成功的 case}}
\]

\[
HIR = \frac{\text{需要人工修改或批准的 case}}{\text{所有 case}}
\]

\[
WeightedPass = \frac{\sum w_p \cdot passed}{\sum w_p}, \quad w_{P0}=5,w_{P1}=2,w_{P2}=1
\]

还要报告：build rate、execution pass、state equivalence、transaction equivalence、安全退化数、mutation kill rate、metamorphic pass、flake rate、恢复完整率、成本、wall-clock、修复回合和证据完整率。

### 11.2 统计要求

- 非确定性任务至少 3 个固定 seed；重要 release 候选建议 5～10 个 seed；
- 报告均值、标准差、P10/P50/P90 和最差值；
- 性能比较包含预热、稳态、置信区间和硬件/镜像 digest；
- 任何排除、超时、不可用环境都单列，不得从分母静默删除。

## 12. 发布门禁

详见 `RELEASE_GATES.md`。绝对硬门包括：

- P0 critical Oracle 100%；
- P0 SSER = 0；
- 数据损坏、安全退化、关键事务不一致 = 0；
- P0 flaky = 0；
- evidence completeness = 100%；
- 语料 commit 固定，许可证无阻断。

## 13. 执行计划

### P0：确定性商业 Golden Route

- 完成四个生产 harness adapter；
- 接入 P0 case、双运行、DB 状态、安全和证据包；
- Spring 与三条 SQL Golden Route 先达到 release gate；
- 机器 exhaustive wall-clock 目标：在 32～64 vCPU、并发 16～32 的测试集群上控制在 24～72 小时，实际值由 ETGB telemetry 校准。

### P1：仓库级规模与生成演化

- 公共真实仓库、RepoTransBench/TransRepo 等外部语料；
- 项目生成 10 栈、演化序列、多 seed；
- mutation、metamorphic、fault injection 全面启用；
- weekly 全量在独立 benchmark cluster 运行。

### P2：大型客户认证与形式化增强

- ≥3 个 >500k LOC，≥1 个 >1M LOC；
- 关键事务/权限/状态机接入 TLA+/Dafny/SMT 或模型检查 Oracle；
- 影子流量和分阶段生产回放；
- 建立公开可复验、私有 hidden 双排行榜。

## 14. 成功标准

Elmos 的竞争优势不应表述为“生成代码更多”，而应能量化证明：

1. 在真实仓库上保持行为与状态；
2. 遇到不可直接转换的语义时不撒谎；
3. 在故障、并发、安全和长期演化中仍可恢复、可审计；
4. 使用固定成本和机器 wall-clock 重复达到发布门禁。
