# 55-Skill Catalog

| ID | 阶段 | 优先级 | 能力 | 主要输出 |
|---|---|---:|---|---|
| `00-modernization-orchestrator` | `control-plane` | P0 | 仓库级现代化总编排器：把输入仓库、目标基线、策略、权限、证据、转换、验证、修复和认证组织成可恢复、可审计的长任务状态机。 | `modernization-run-manifest`, `phase-dag`, `final-certification-bundle` |
| `01-job-contract-and-policy-resolver` | `control-plane` | P0 | 任务契约与策略解析：把用户目标解析为不可变任务契约，明确行为等价、允许的现代化范围、安全硬化模式、目标 JDK、视图策略和生产门禁。 | `job-contract`, `policy-snapshot` |
| `02-reproducible-repository-snapshot` | `control-plane` | P0 | 可复现仓库快照：固定 Git、子模块、LFS、构建依赖、制品仓库、JDK、容器镜像、环境配置和数据库基线，形成可重放输入。 | `repository-snapshot`, `reproduction-lock` |
| `03-checkpoint-resume-cancel` | `control-plane` | P0 | 检查点、恢复与取消：为每个扫描、IR、改写、构建、测试和修复步骤提供幂等检查点、租约、fencing、恢复、暂停和取消语义。 | `execution-checkpoints`, `resume-token`, `cancellation-ledger` |
| `04-wall-clock-eta-and-cost-model` | `control-plane` | P0 | 机器运行时 ETA 与成本模型：按仓库规模、语言/框架密度、构建耗时、测试矩阵和历史吞吐估计 Elmos 自身 wall-clock ETA、token、计算和存储成本。 | `eta-estimate`, `cost-estimate`, `estimate-confidence` |
| `05-tool-authority-and-sandbox` | `control-plane` | P0 | 工具权限与执行沙箱：把每个 Environment/Attachment 的仓库、网络、数据库、密钥和执行权限绑定到具体任务阶段，默认拒绝越权副作用。 | `authority-plan`, `sandbox-profile`, `audit-policy` |
| `10-build-and-module-topology` | `repository-forensics` | P0 | 构建与模块拓扑恢复：识别 Maven/Gradle/Ant/Ivy、自定义脚本、EAR/WAR/JAR、父子 POM、生成源码、profile、插件和模块依赖顺序。 | `build-topology`, `module-dag`, `generated-source-map` |
| `11-framework-and-version-fingerprinting` | `repository-forensics` | P0 | 框架与版本指纹：从依赖、类继承、XML、注解、JSP 标签和运行轨迹识别 Struts1、Struts2、Servlet、旧 Spring 及混合框架版本。 | `framework-inventory`, `version-confidence` |
| `12-runtime-deployment-topology` | `repository-forensics` | P0 | 运行时与部署拓扑恢复：恢复 Tomcat/WebLogic/WebSphere/JBoss/Jetty、外置容器、JNDI、共享类库、context path、classloader 和节点拓扑。 | `runtime-topology`, `container-contract` |
| `13-route-ownership-and-conflict-analysis` | `repository-forensics` | P0 | 路由所有权与冲突分析：合并 web.xml、web-fragment、注解、Struts 配置和程序化注册，计算每条 URL/HTTP 方法最终由谁处理及冲突优先级。 | `effective-route-table`, `route-conflicts` |
| `14-environment-config-overlay-analysis` | `repository-forensics` | P0 | 环境配置叠加分析：解析 profile、系统属性、JNDI、外部配置、容器 descriptor、资源过滤和秘密注入的覆盖顺序，生成环境矩阵。 | `effective-config-matrix`, `secret-reference-map` |
| `15-dependency-compatibility-and-jakarta-readiness` | `repository-forensics` | P0 | 依赖兼容性与 Jakarta 就绪度：分析 javax→jakarta、Servlet 6.1、Spring Framework 7、Boot 4 模块化、第三方库、容器和字节码基线兼容性。 | `dependency-compatibility-graph`, `jakarta-readiness-report` |
| `20-struts1-lifecycle-recovery` | `semantic-recovery` | P0 | Struts 1 请求生命周期恢复：恢复 RequestProcessor、ActionServlet、ActionMapping、ActionForm、验证、角色、forward/include、异常和模块配置的真实执行序。 | `struts1-pipeline-ir` |
| `21-struts2-interceptor-pipeline-recovery` | `semantic-recovery` | P0 | Struts 2 拦截器流水线恢复：展开 package 继承、interceptor stack、条件/短路、参数覆盖、ValueStack/OGNL、PreResultListener、Result 与 action chain。 | `struts2-invocation-ir` |
| `22-servlet-container-semantics-recovery` | `semantic-recovery` | P0 | Servlet 容器语义恢复：恢复 servlet/filter/listener 生命周期、mapping precedence、dispatcher types、async、error dispatch、multipart、session 和安全约束。 | `servlet-container-ir` |
| `23-jsp-taglib-and-view-semantics` | `semantic-recovery` | P0 | JSP、Taglib 与视图语义恢复：解析 JSP/JSTL/TLD/custom tag/Tiles/FreeMarker 等视图依赖、scope、表达式、动态 include、标签副作用和输出编码。 | `view-semantics-ir`, `view-dependency-graph` |
| `24-request-binding-and-type-conversion` | `semantic-recovery` | P0 | 请求绑定与类型转换恢复：恢复参数来源、别名、集合/嵌套属性、缺省值、checkbox reset、conversion error、locale/date/number 和绑定白名单。 | `binding-conversion-ir` |
| `25-navigation-dispatch-and-error-semantics` | `semantic-recovery` | P0 | 导航、分派与错误语义恢复：统一建模 forward、include、redirect、chain、error dispatch、welcome file、result code、状态码、请求属性和 URL 编码。 | `navigation-dispatch-ir` |
| `26-session-state-and-scope-semantics` | `semantic-recovery` | P0 | Session、状态与作用域语义恢复：识别 page/request/action/session/application/thread/static/cache/DB 状态，恢复创建、读取、覆盖、失效、序列化和跨请求序列。 | `state-scope-ir`, `request-sequence-state-machine` |
| `27-security-authn-authz-csrf-semantics` | `semantic-recovery` | P0 | 认证、授权与 CSRF 语义恢复：恢复 container security-constraint、角色检查、登录会话、拦截器、token/double-submit、CSRF、Cookie 和拒绝路径。 | `security-semantics-ir` |
| `28-transaction-and-side-effect-topology` | `semantic-recovery` | P0 | 事务与副作用拓扑恢复：恢复 JDBC/JPA/iBATIS/Hibernate、JMS、文件、邮件、远程 HTTP、缓存、审计日志等副作用的事务边界、顺序与幂等性。 | `transaction-ir`, `side-effect-graph` |
| `29-concurrency-lifecycle-and-threadlocal` | `semantic-recovery` | P0 | 并发、实例生命周期与 ThreadLocal 恢复：识别 Action/Servlet/Filter/Listener/Bean 的实例策略、共享字段、同步、ThreadLocal、异步 dispatch 和资源释放风险。 | `concurrency-lifecycle-ir` |
| `30-repository-evidence-graph` | `semantic-model` | P0 | Repository Evidence Graph：把代码、配置、构建、trace、测试、数据库和人工决策转换为带 provenance、置信度、冲突和有效期的证据图。 | `repository-evidence-graph` |
| `31-legacy-web-semantic-ir` | `semantic-model` | P0 | Legacy Web Semantic IR：将异构框架事实规范化为 endpoint、pipeline、binding、state、view、security、transaction、side-effect 和 deployment IR。 | `legacy-web-semantic-ir` |
| `32-behavioral-contract-and-sequence-mining` | `semantic-model` | P0 | 行为契约与请求序列挖掘：从代码、现有测试、日志/trace 和流量生成单请求契约与跨请求状态机，包括 wizard、登录、重复提交和异常恢复。 | `behavior-contracts`, `sequence-scenarios` |
| `33-unknown-semantics-ledger` | `semantic-model` | P0 | 未知语义债务账本：把无法可靠解释、证据冲突、动态反射/脚本和环境缺失显式登记，禁止以猜测冒充已迁移事实。 | `unknown-semantics-ledger` |
| `34-semantic-risk-scoring` | `semantic-model` | P0 | 语义风险评分：按业务关键度、证据覆盖、状态性、并发性、安全性、副作用和回滚难度为模块/端点计算风险与验证预算。 | `semantic-risk-register`, `verification-budget` |
| `40-preserve-first-migration-strategy` | `planning` | P0 | Preserve-first 迁移策略：默认把框架替换与 UI/领域重构分离，先保持行为，再在独立变更波次中现代化，避免差异归因失真。 | `migration-strategy` |
| `41-springboot4-target-architecture` | `planning` | P0 | Spring Boot 4 目标架构合成：根据 IR 选择 Spring MVC、Security、Validation、Transaction、Session、容器、JSP/WAR 或无 JSP/JAR 的目标结构。 | `target-architecture` |
| `42-multi-module-conversion-wave-planner` | `planning` | P0 | 多模块转换波次规划：按模块 DAG、路由簇、数据库边界、共享库和风险切分可独立构建、验证、回滚的 transformation units。 | `conversion-wave-plan` |
| `43-compatibility-shim-synthesis` | `planning` | P0 | 兼容层合成规划：当 Spring 无直接等价物时生成最小、可测试、可移除的 compatibility shim，而非改变业务行为或留下隐式 TODO。 | `compatibility-shim-plan` |
| `44-packaging-view-and-container-decision` | `planning` | P0 | 打包、视图与容器决策：根据 JSP、外置容器、共享类库、JNDI、classloader 和部署约束选择 executable WAR/JAR、容器与视图迁移策略。 | `packaging-decision` |
| `45-cutover-strangler-and-dual-run-plan` | `planning` | P0 | 切流、Strangler 与双运行规划：设计路由级/模块级双运行、影子流量、canary、session 兼容、数据库写入策略、回滚和流量提升门槛。 | `cutover-plan`, `rollback-plan` |
| `50-deterministic-ast-and-config-rewrite` | `transformation` | P0 | 确定性 AST 与配置改写：以类型解析、XML/descriptor 模型和 OpenRewrite 风格 recipe 实施可重复改写；LLM 仅处理有证据约束的语义缺口。 | `deterministic-change-set` |
| `51-struts1-to-springmvc-generator` | `transformation` | P0 | Struts 1→Spring MVC 生成器：从 Struts1 pipeline IR 生成 Controller、DTO/ModelAttribute、Validator、Interceptor/Filter、ExceptionHandler 和导航桥。 | `struts1-target-changes` |
| `52-struts2-to-springmvc-generator` | `transformation` | P0 | Struts 2→Spring MVC 生成器：将 interceptor stack 的前置/后置/短路语义、OGNL/ValueStack、Result、异常和 action chain 映射到 Spring 扩展点。 | `struts2-target-changes` |
| `53-servlet-to-springmvc-generator` | `transformation` | P0 | Servlet→Spring MVC 生成器：转换 HttpServlet、Filter、Listener、程序化注册、异步/流式响应和 descriptor，同时保留 dispatch 与生命周期语义。 | `servlet-target-changes` |
| `54-jakarta-and-dependency-migration` | `transformation` | P0 | Jakarta 与依赖迁移：以符号解析和兼容图迁移 javax→jakarta、Boot 4 starter/module、插件、测试依赖和容器，不做全局字符串替换。 | `dependency-target-changes` |
| `55-spring-security-validation-transaction-generator` | `transformation` | P0 | Security、Validation 与 Transaction 生成器：根据恢复语义生成 Spring Security、Jakarta Validation/自定义 Validator 和事务边界，支持 preserve 与 harden 双模式。 | `cross-cutting-target-changes` |
| `56-jsp-preserve-or-modernize` | `transformation` | P0 | JSP 保留或现代化：默认保留 JSP/Tiles/taglib 并提供 WAR 路径；可在独立波次迁移至 Thymeleaf/React/Vue，保持 view model 契约。 | `view-target-changes` |
| `57-source-map-change-provenance` | `transformation` | P0 | 语义 Source Map 与变更溯源：为每个目标类、配置和测试记录来自哪些 legacy 证据、IR 节点、recipe、模型决策和验证结果。 | `semantic-source-map`, `change-provenance` |
| `58-idempotent-change-set-commit` | `transformation` | P0 | 幂等 Change Set 提交：将改写按 transformation unit 分组，确保重复执行不漂移、冲突可回滚、提交原子化且生成机器可读 manifest。 | `committed-change-sets` |
| `60-static-semantic-coverage` | `verification` | P0 | 静态语义覆盖验证：对照源/目标 IR 检查端点、pipeline、状态、异常、安全、事务和副作用覆盖，检测遗漏与多余行为。 | `static-coverage-report` |
| `61-test-and-scenario-generation` | `verification` | P0 | 测试与场景生成：从契约、状态机和风险预算生成单元、集成、MockMvc、容器、浏览器、故障与跨请求序列测试。 | `generated-test-suite` |
| `62-differential-http-and-view-oracle` | `verification` | P0 | HTTP 与视图差分 Oracle：同一输入重放 legacy/target，比较 status、headers、cookie、body、redirect/forward、JSP/HTML/JSON/XML，应用显式归一化。 | `http-view-equivalence-report` |
| `63-session-db-and-side-effect-diff` | `verification` | P0 | Session、数据库与副作用差分：比较跨请求 session、DB 行/事务、消息、文件、缓存、邮件和审计副作用，识别顺序、次数和回滚差异。 | `state-side-effect-equivalence-report` |
| `64-security-equivalence-and-hardening` | `verification` | P0 | 安全等价与可选硬化验证：验证认证、角色、拒绝路径、CSRF/token、Cookie 和绑定面；将行为保持与显式安全硬化差异分开报告。 | `security-equivalence-report`, `hardening-delta-report` |
| `65-concurrency-performance-and-fault-verification` | `verification` | P0 | 并发、性能与故障验证：验证 singleton/thread safety、ThreadLocal 泄漏、异步、流式响应、连接池、P95/P99、压力和依赖故障下的等价性。 | `nonfunctional-equivalence-report` |
| `66-observability-and-trace-correlation` | `verification` | P0 | 可观测性与 Trace 关联：用统一 request/sequence/side-effect correlation id 对齐 legacy 与 target trace，输出可定位到 IR/源文件的差异证据。 | `trace-correlation-index` |
| `70-mismatch-classification` | `repair-certification` | P0 | 差异分类与根因定位：把差异归类为 route、binding、lifecycle、state、view、security、transaction、dependency、environment 或 oracle 噪声。 | `mismatch-ledger` |
| `71-bounded-semantic-auto-repair` | `repair-certification` | P0 | 有界语义自动修复：基于最小影响范围、证据约束和风险上限生成修复；每次只改一个根因，限制循环次数并禁止无证据大范围重写。 | `repair-change-sets`, `repair-evidence` |
| `72-impact-based-regression-selection` | `repair-certification` | P1 | 影响面回归选择：利用 module/route/state/side-effect/source-map 图选择最小但完备的回归集，并周期性执行全量测试防止局部盲区。 | `regression-selection-plan` |
| `73-production-cutover-rollback` | `repair-certification` | P1 | 生产切流与回滚执行：执行影子、canary、流量提升、数据库保护、session 策略、健康门和自动回滚，所有副作用步骤必须幂等。 | `cutover-execution-report` |
| `74-evidence-bundle-and-e0-e5-certification` | `repair-certification` | P0 | 证据包与 E0–E5 生产认证：聚合快照、IR、source map、构建、测试、差分、风险、SBOM、性能、安全、切流和未知语义，签发分级认证。 | `e0-e5-certification`, `evidence-bundle` |
| `75-golden-route-benchmark-and-learning-cache` | `repair-certification` | P1 | Golden Route 基准与学习缓存：在 ≥3 个 500k+ LOC、至少 1 个 1M+ LOC 的真实/授权仓库上复测，缓存已确认映射、oracle 与修复模式并依赖感知失效。 | `golden-route-scorecard`, `validated-pattern-cache` |
