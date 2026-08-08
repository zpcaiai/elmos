# ELMOS 业务线闭环矩阵

本矩阵用于区分两类状态：

- `REPOSITORY_CLOSED`：仓库内可以完成的实现、契约、测试、构建和保守门禁已经闭环。
- `EXTERNAL_GATE_REQUIRED`：必须依赖真实客户、生产等价环境、独立验证者或获授权的外部操作；在证据产生前保持 `NOT_RUN`，不得由本地测试替代。

当前总状态：**精确支持矩阵内的本地演示、工程验证和 POC 已达到
`REPOSITORY_CLOSED`；任意企业项目的完整迁移、任意环境的一键生产运行、
GA、生产就绪和外部认证仍为 `EXTERNAL_GATE_REQUIRED`。** 后一类状态只有在
真实目标环境、客户数据与独立验证证据产生后才能提升，本地生成物和测试不能
替代这些外部门禁。

## 业务线状态

| 业务线 | 用户入口与核心实现 | 仓库内闭环与验证 | 当前状态 | 尚需外部证据 |
| --- | --- | --- | --- | --- |
| Spring 老项目翻新 M30 | `/spring`、Spring 指纹探测器、受控代理、Java Worker、`spring-boot-2-7-18-to-3-5-3` Pack | 区分经典 Spring 与 Boot，识别 XML/注解、Jakarta 和 MVC/WebFlux 阻断；浏览器代理操作绑定最长 24 小时短期令牌、唯一租户与 Actor；真实任务、Run UUID 身份恢复、取消/重试、日志、独立摘要验证、产物与运行态形成闭环；下载响应绑定长度、ETag 与 SHA-256，浏览器复算字节摘要后才交付；Gradle 2.x 区间精确声明为 `[2.0.0,3.0.0)`，已接入 Gradle 8.14.3 隔离构建/测试/启动与 OpenRewrite Gradle 插件入口，精确 tuple 证据保持 `NOT_RUN` | `REPOSITORY_CLOSED` | 客户源仓真实基线、目标启动/数据/安全等价、Gradle 真实 tuple、独立 holdout 与外部认证保持 `NOT_RUN` |
| 全库跨语言转换 M29 | `/translation`、30 个方向 Route Pack、polyglot-route engine、持久受控 Runner | 六种语言（Java、Python、C#、Go、Rust、TypeScript）两两成对形成 30 条方向独立路线，全部 `status=limited` / `local_execution_status=PASSED_LOCAL`；`typed-pure-function-v1` 已完成开发、holdout、代表性编译与行为回放；`repository-pipeline` 合并确定性只读清单、编译器发现、逐单元行为回放、绑定快照/源码/语料摘要且验证目标字节的断点检查点、命名空间隔离装配、真实整库构建与内容寻址 ZIP；UI 以租户/Actor/短期令牌启动、恢复、取消任务并在下载时复算 SHA-256；缺少行为用例、漂移、跳过或失败只能得到 `PARTIAL`/阻断，不会扩张为整库成功 | `REPOSITORY_CLOSED` | 对象图、异常、异步、I/O、框架、数据库、并发、真实客户整库逐单元执行、独立验证与外部认证保持 `NOT_RUN` |
| 多语言项目生成 B46-B95 | `/generation`、生成 API、本地 Runner、project-synthesis engine、Batch 66-95 Skills | 8 个精确目标；草稿、结构化分析、开放问题、一次性审阅摘要、显式批准、生成/验证、文件摘要复算、归档下载、启动健康探针与停止形成闭环；刷新后可用完整 UUID、租户、Actor 和重新输入的短期令牌恢复原子持久化任务；生成 CI Action 与基础镜像均固定到不可变摘要；全部八种语言已完成真实生成、精确工具链构建、测试、启动探针和清理；`run_production_matrix.py` 对 8 × JWT/OIDC 共 16 个 PostgreSQL 17.5 Profile 执行迁移、鉴权负向路径、CRUD 与 RLS 跨租户隔离；Java/Python 多实体和其余六目标单实体的生产边界成为前后端共同契约，需求分析后立即阻断不兼容批准 | `REPOSITORY_CLOSED` | 外部托管 PostgreSQL、真实 IdP、完整传递依赖 SBOM/签名、真实 rootless 生产 Runner、设备/集群/云部署、恢复/DR、独立用户验收、外部验证及生产交付保持 `NOT_RUN` |
| Git 仓库接入与修改 | `/repositories`、Web BFF、repository-workspace control-plane API、JGit 工作区 | GitHub、Gitee 与通用 HTTPS Git 统一接入；远端引用先解析为 advertised 精确提交，浅拉取后再次比对提交；源码、测试、说明、配置、本地和云部署文件分类、读取、新建、修改与删除闭环；租户/Actor、短期用户门禁、内部密钥、owner-only 私库凭据引用、显式路径批准、旧 SHA-256 并发保护、CODEOWNERS 审批、密钥/二进制/符号链接保护及操作日志闭环；子模块/LFS 未独立授权时保持只读 | `REPOSITORY_CLOSED` | 私有 GitHub/Gitee/自建实例实仓 E2E、子模块逐仓授权、LFS 对象完整水合、远端分支保护/PR/推送和部署均保持 `NOT_RUN`，必须另行授权 |
| 工作区与 Private Runner | workspace-service、workspace manager、egress proxy、Compose 服务拓扑 | 工作区和秘密租约请求在提供者访问前完成身份、类型与 TTL 校验；策略/依赖故障返回稳定响应；默认拒绝出口 | `REPOSITORY_CLOSED` | 真实 rootless Runner 隔离、工作负载身份、远端证明、秘密租约与撤销演练保持 `NOT_RUN` |
| 验证、证据与认证 | java-engine-worker validation API、Batch 1-45 严格套件、补充套件、evidence contracts | 嵌套请求在执行前校验；同语义映射规范化后参与幂等指纹；终态不可改写；权威门禁按缺失证据失败关闭 | `REPOSITORY_CLOSED` | 逐用例执行者/独立验证者、原始证据、签名请求和信任库保持 `NOT_RUN` |
| Skills 与能力目录 | `.agents/skills`、`agent-skills/runtime`、`/skills` | UI 展示实际可调用 Skill 数量，并由生产就绪门禁逐目录核对，库存漂移会失败关闭；新增业务线审计、生成旅程、跨服务运维闭环 Skills；各批次不可变清单与接口校验通过 | `REPOSITORY_CLOSED` | Skill 静态通过不等于客户、生产、行业或监管认证；相关证据保持 `NOT_RUN` |
| Web 产品体验 | `/`、`/spring`、`/translation`、`/generation`、`/repositories`、`/migration`、`/commercialization`、`/skills`、`/admin` 及能力/任务 API | 响应式页面、表单状态、空/错/成功反馈、浏览器草稿、保守状态、TypeScript 与 Next.js 生产构建闭环；Chromium、Firefox、WebKit 及 Chromium/WebKit 移动视口执行自动可访问性、键盘、失败关闭与无横向溢出检查；有副作用的真实生成/运行旅程只在隔离 Chromium 项目执行一次 | `REPOSITORY_CLOSED` | Firefox/WebKit 的有副作用 Runner 旅程、辅助技术人工审查与客户可用性验收保持 `NOT_RUN` |
| 用户操作日志与生产运营管理端 | 根布局采集器、Web BFF 审计 proxy、control-plane 全 API 拦截器、V50/V51 双存储、企业 OIDC、`/admin` | 浏览器隐私性能遥测与不可删除服务端审计分离；BFF 每个业务 API 在执行前写审计，control-plane 每个 API 写执行前/完成结果和耗时；企业会话权限映射真实租户/Actor；18 条业务线 SLO、告警、事件、负责人、通知 outbox、性能/Bug 诊断提案、乐观并发、审批、摘要绑定 SCM 计划、30 天保留证据与自动任务闭环；输入、Token、查询、请求体、错误原文和源码均不采集 | `REPOSITORY_CLOSED` | 真实 IdP/凭证轮换执行、外部告警接收、真实 SCM 补丁/测试/PR/部署、生产量级容量成本、隐私评审和值班/故障演练保持 `NOT_RUN` |
| 运维、部署与可观测性 | 18 个运行时服务、24 个 Compose 服务、Web/Runner 健康检查、runtime operability validator | Web 到 control-plane 路由闭环；名称/端口唯一；Java/.NET/TypeScript 公开错误边界扫描；13 个任务控制器强制 404/409；项目生成任务使用租户目录原子持久化、重启失败关闭、0600 Secret 文件、维护期拒绝写入、内容寻址备份/逐文件校验/静默恢复；非 root 只读 Web 容器声明健康探针 | `REPOSITORY_CLOSED` | 真实生产部署、外部 Secret Provider、SLO/告警值班、离机保留、生产 RPO/RTO、跨区 DR 和故障演练保持 `NOT_RUN` |
| 产品商业化 B34-B56A 与 Convergence | commercialization UI/API、Product Skills、closure/convergence control plane | 产品闭环/收敛 Skills 的来源、摘要、接口和反伪造校验通过；CI 与 `production-readiness-check` 都覆盖 Batch 97-104 和 closure/convergence；缺失外证时 gate 返回 `BLOCKED` | `REPOSITORY_CLOSED` | 至少两个独立设计伙伴、独立审查、客户验收、单位经济性、GA/生产批准保持 `NOT_RUN` |
| SQL 方言转写 `certified-ddl-v1` + `certified-alter-v1` | `engines/sql-dialect-engine` CLI、`make sql-dialect` | PostgreSQL/MySQL/Oracle/SQL Server 四方言 12 条方向；单条 `CREATE TABLE`/`CREATE INDEX` 的类型、约束与引用动作白名单内真转写；解析用真实 `sqlglot`，发射为逐厂商手写（`sqlglot` 自带跨方言生成器对 AUTO_INCREMENT/IDENTITY 的缺陷已复现并规避）；发射结果由目标方言严格模式**真重解析**校验；给定 DSN 时对 Postgres/MySQL 在事务回滚/临时库内**真执行** DDL；白名单外一律 `DialectError` → `BLOCKED`，携带机器可读 reason code；提供**转换前覆盖率预检**（`scan`：用 sqlglot 真解析器切分语句而非按分号切；blocker 同时报「出现次数」与「不同原因数」，因为实测中单个复制粘贴惯用法可占某 blocker 342 次里的 340 次，只按次数排名会误导路线图；对本仓库 64 个真实迁移文件实测 **174/1015 = 17.1%**（两个 profile 合计；8.0% → 10.3% → 17.1%，每一步都由 blocker 表读数驱动），首测 8.0% 时发现并修复了「内联 `REFERENCES` 被拒但等价的表级 `FOREIGN KEY` 被接受」的真实缺陷）；新增 **`certified-alter-v1`**（按实测选定范围：635 个真实 ALTER 动作里 603 个 ADD COLUMN，故覆盖 ADD/DROP/RENAME COLUMN 与 ADD/DROP CONSTRAINT；**拒绝** `ALTER COLUMN TYPE`/`SET NOT NULL`/`SET DEFAULT`，因为 MySQL 与 SQL Server 都要求重述列的完整类型而单条 ALTER 并不携带，凭空补类型正是本 profile 要防的静默损坏；**两条方言规则语法校验腿抓不到**——sqlglot 会接受 Oracle 的 `ADD COLUMN` 和 T-SQL 的 `RENAME COLUMN` 而真实数据库拒绝，故写入发射器并由断言锁定）；修复**引用动作的逐方言可达性**（Oracle 无 `ON UPDATE` 子句、`ON DELETE` 仅支持 CASCADE/SET NULL 且以省略表达 NO ACTION，Oracle 与 SQL Server 均无 RESTRICT；不可达一律 `BLOCKED` 而非静默降级——降级会改变约束的检查时机。该缺陷此前被引擎自己的 12 方向往返测试掩盖：夹具用 `ON UPDATE RESTRICT` 却报 PASSED，因为 sqlglot 对所有方言都接受它）；115 条真实测试、`ruff`/`mypy` 干净 | `REPOSITORY_CLOSED`（仅限 `certified-ddl-v1` 子集） | Oracle/SQL Server 无免费 root-less 本地实例，执行级验证恒为 `EXECUTION_NOT_AVAILABLE`；子集外任意 SQL（实测被阻塞的 910 条里 470 条根本不是 `CREATE TABLE`/`CREATE INDEX`——228 个 trigger、128 条 `ALTER TABLE`、18 个 schema、17 个 function，**缺口是结构性的而非增量的**，只有另做 `ALTER TABLE` profile 才能覆盖）、真实客户 schema 迁移、独立验证与外部认证保持 `NOT_RUN` |
| 大前端组件转写 `certified-component-v1` | `engines/component-dialect-engine` CLI、仓库级流水线、`make component-dialect` | 10 个框架（React/TypeScript/Vue 3/Vue 2/Angular/Svelte/React Native/微信小程序/ArkUI/Flutter）、6 个可作源、**54 条方向对全部真转写**；解析全部走各自官方真编译器，发射为逐框架手写；每次发射由目标框架**真编译器**回验；React/TypeScript/Vue 3/Vue 2/Svelte 五端**真 SSR 渲染并比对规范化 DOM**（54 对中 20 对拿到行为等价证据）；Vue 3/Svelte/Angular 往返 canonical IR **精确相等**（含列表渲染）；支持**组件组合**（子组件引用：Angular 按 selector 且必须进 standalone `imports`、微信必须进 `usingComponents`、Vue 2 必须进 `components`——三者写错都是「编译通过但渲染空白」）、**单文件多组件**（逐组件隔离失败，一个组件越界不牵连同文件其它组件）、**语义容器标签**与**同文件具名 props 类型**；提供**转换前覆盖率预检**（`scan`：纯解析、不写盘、不选目标端，输出「N 个组件 / M 个在子集内 / 阻塞原因排名」的 JSON+Markdown 双格式报告，并在报告正文声明该数字是上界；对本仓库自带的 `apps/web-console` 真实代码实测为 **8/33（24.2%）**，另有 50 个返回非 JSX 的辅助函数被正确判定为「非组件」并排除出分母；首次实测为 0/28，正是该读数驱动了后续四轮子集扩容）；提供**人工接管工作流**（`handoff`：指派、标记手工移植、`handoff.json` 随工程入库；重跑**绝不覆盖**手写代码，源文件变更后以 `SOURCE_CHANGED_SINCE_PORT` 判定手工移植已过期并把 `deliveryStatus` 压回 `INCOMPLETE`；人工产物不记任何引擎证据，故 `status` 仍为 `PARTIAL`）；仓库级流水线产出**真能 `vite build` 的工程** + 逐文件 `coverage-report.json`，子集外产出大声抛错的占位桩且整体记 `PARTIAL`；263 条真实测试、`tsc` 干净 | `REPOSITORY_CLOSED`（仅限 `certified-component-v1` 子集） | ArkUI（ArkTS `struct` 无独立解析器）与 Flutter（需 Dart SDK）**只能作目标端**；Angular/React Native/微信小程序/ArkUI/Flutter 缺可得运行时，执行级验证恒为 `EXECUTION_NOT_AVAILABLE`；子集外构造（对象 props、其余 hooks、slots、路由、样式体系、异步数据）；Vue 2/微信小程序的运行期 props 只记 `Array` 而无元素类型，故**只能作列表目标端、不能作列表源端**（`CERTIFIED_COMPONENT_UNRECOVERABLE_LIST_ELEMENT`）、真实客户整库迁移、独立验证与外部认证保持 `NOT_RUN` |

## 第二轮横向缺陷与解决方案

| 横向问题 | 影响业务线 | 已实施解决方案 | 防回归证据 |
| --- | --- | --- | --- |
| OpenAPI 只列出部分执行器，Java 静默丢弃 `options` | 所有语言/框架/数据/云迁移 | OpenAPI 与 Java 135 个 `ExecutorType` 做精确集合相等校验；Java `JobRequest` 保留只读、规范化的 `options` | `EngineApiContractTest` 比较完整枚举、反序列化 options、拒绝非法嵌套预算 |
| 相同嵌套 JSON 因键顺序不同产生幂等冲突 | Java、.NET、Python、前端引擎 | Java 与 .NET 对嵌套映射递归排序；Python/前端继续使用确定性 JSON 规范化 | Java/.NET 新增重排输入回归用例；更改预算仍必须冲突 |
| 已失败/成功任务可被取消为 `CANCELLED`，幂等缓存与查询状态分裂 | 13 个 Java 控制器和四种语言工作进程 | 终态统一不可变；未知/跨租户任务为 404，终态冲突为 409；错误码不再依赖英文文案匹配 | 共享状态机和每类专用引擎负向测试；operability validator 强制控制器处理器存在 |
| 工作进程内存任务表被误解为持久任务系统 | 全部执行引擎、运维 | capability 明示 `EPHEMERAL_PROCESS_LOCAL`、`ELMOS_CONTROL_PLANE` 和不支持工作进程重启恢复 | Java/.NET/Python/TypeScript capability 测试；OpenAPI 明示持久状态责任 |
| 前端与 .NET 将解析器、路径或异常消息直接返回 | 客户端迁移、.NET 迁移、运维安全 | 所有公开响应使用稳定错误码和固定安全文案；底层异常仅能进入受控诊断证据 | TypeScript HTTP/引擎负向测试、.NET 路径泄漏测试、跨语言静态泄漏扫描 |
| 项目生成计划刷新即丢失 | 多语言项目生成、Web 产品体验 | 本地创建、读取、恢复、删除闭环；恢复后重新锁定命令；损坏或超限数据被过滤 | Next.js 类型检查/生产构建和 production-readiness 源码契约测试 |
| 任务已由服务端持久化，但浏览器刷新后无法继续观察 | 多语言项目生成、运维 | 增加按完整 UUID 恢复入口；恢复请求重新绑定租户、Actor 与页面内存中的短期令牌，令牌不持久化 | Chromium 恢复旅程断言身份请求头和终态任务回显 |
| 整库转换 UI 仅保存仓库引用，未形成可执行拆分输入 | 全库跨语言转换 | 增加不跟随符号链接的稳定只读扫描、内容摘要、资源上限和逐源文件工作单元；UI 严格校验路线、仓库与摘要契约 | polyglot engine 单元/负向测试、跨浏览器清单导入与保存旅程 |
| 整库转换仍需人工串联命令，无法从 UI 恢复执行 | 全库跨语言转换、运维 | 增加可恢复 `repository-pipeline`、租户隔离原子任务、只读源码/语料根、取消、内容寻址归档和浏览器 SHA-256 复算；生产只允许不可变工具链镜像 Rootless 执行 | polyglot pipeline 单元/恢复测试、Chromium 真实整库任务与下载旅程 |
| 整库转换断点只按工作单元 ID 复用，源码或行为语料漂移后可能误用旧通过结果 | 全库跨语言转换、证据完整性 | 检查点绑定仓库快照、方向、Profile、源码 SHA-256、函数、发现判定与行为语料 SHA-256；恢复前复算目标字节，任一漂移即重跑；失败前先移除旧报告与 ZIP，避免陈旧交付物被误取 | 源码漂移、语料漂移、目标字节完整性与确定性恢复单元测试 |
| Spring 浏览器代理只依赖固定组织头，缺少最终用户身份绑定 | Spring 老项目翻新、安全 | 运行读取、变更、私有仓库目录和 GitHub App 操作均要求短期 Bearer、租户和 Actor 精确绑定；Run UUID 恢复不再只凭浏览器会话 | TypeScript 构建、Spring Playwright 显式身份恢复旅程 |
| 生成目标的多实体生产边界到生成中途才暴露 | 多语言项目生成、Web 产品体验 | 将 Java/Python 多实体与其余六目标单实体边界加入前后端能力契约；结构化需求分析后立即阻断不兼容批准，服务端在消费一次性审阅摘要前再次校验 | Chromium UI 边界测试与 API 409 负向测试 |
| 下载按钮信任服务端元数据，浏览器未复算 Spring ZIP | Spring 老项目翻新、Web 产品体验 | Worker 下载响应加入长度、ETag 和 SHA-256，Next.js 代理透传，浏览器复算长度与摘要，不一致拒绝交付 | Java reactor 测试、Spring Playwright 下载旅程 |
| 生成项目的 CI 使用可变 Action 标签 | 多语言项目生成、供应链 | 8 个目标模板的所有 GitHub Action 固定为 40 位上游提交摘要并保留版本注释 | Project Synthesis 测试拒绝任意可变或格式错误的 `uses:` 引用 |
| 生成项目的基础镜像使用可变标签，Python/PostgreSQL 文案与运行配置漂移 | 多语言项目生成、供应链、Web 产品体验 | 8 个目标的所有非 `scratch` 基础镜像固定到官方多架构清单 SHA-256；Python 统一为 3.12.12，PostgreSQL 统一为 17.5；UI、README、CI、rootless Runner 与本地运行器共用精确契约 | Project Synthesis 测试拒绝任意可变/格式错误镜像；全仓契约测试拒绝版本漂移；JWT 与 OIDC 均通过真实本地 PostgreSQL 17.5 验收 |
| C# 启动 Profile 覆盖测试分配端口，Kotlin 构建继承用户级 Gradle 镜像配置 | 多语言项目生成、可复现工具链 | .NET 启动显式禁用 launch profile；Kotlin 使用 owner-only、非符号链接的隔离 Gradle User Home，并只接受无凭据、无路径的显式 HTTP(S) 代理配置，阻断用户级 `init.d` 和隐式镜像改写 | C# 动态端口启动/健康探针通过；Kotlin 冷/热缓存规划负向测试与真实构建通过；8 语言 Starter 和 16 项 PostgreSQL JWT/OIDC 生产矩阵全部通过 |
| 新 Skill 分发未进入总生产就绪门禁且 Makefile 绑定 Homebrew 路径 | 产品商业化、CI/开发者体验 | 使用可覆盖的 `UV ?= uv`；总门禁与 CI 纳入 Batch 97-104 及 Product Closure/Convergence | production-readiness 测试检查依赖集合与平台无关命令 |
| Vercel 从仓库根目录部署时未识别嵌套 Next.js 应用，生成空部署并返回边缘层 404 | Web 产品体验、运维部署 | Vercel 项目 Root Directory 精确设置为 `apps/web-console`，应用目录内声明 Next.js 框架并由锁定的 pnpm 版本安装/构建；不增加重写或额外公开入口 | production-readiness 配置测试、Web 生产构建、推送后的 Vercel 部署与根路由验证 |
| 仓库来源局限于 GitHub 快照且只能读取，Gitee/自建 Git、说明/配置/部署文件和安全修改没有统一闭环 | 三条业务线输入、工作区、安全、Web 产品体验 | 新增 provider-neutral 精确提交工作区；支持 GitHub/Gitee/通用 HTTPS Git；统一文件分类、UTF-8 读取、新建/修改/删除、哈希并发保护、CODEOWNERS 审批、私库临时凭据、租户/Actor 与追加式操作日志；远端推送/PR/部署保持独立门禁 | JGit 本地真实仓库测试、控制器/凭据负向测试、Next.js 生产构建与 Chromium UI 旅程 |
| 15 个样本的 nearest-rank p95 实际取最大值，单次主机调度停顿导致 SQL 路线性能假失败 | 数据库迁移、CI 稳定性 | 保持 75ms 阈值不变，将预热提高到 5 次、观测提高到 40 次，使 p95 使用第三高样本；仍完整保留每次原始计时并在任一真实持续退化时失败关闭 | SQLite 3.53.3→DuckDB 1.5.4 真实引擎等价、事务/锁与性能证据测试 |

## 三条核心业务线的本地执行边界

Spring 代理、整库转换 Runner 和项目生成 Runner 都默认关闭。启用项目生成 Runner 或整库转换 Runner 时，以下共享变量必须全部显式配置；Web UI 不会显示或持久化令牌：

- `ELMOS_LOCAL_RUNNER_ENABLED=true`
- `ELMOS_LOCAL_RUNNER_ROOT`：专用绝对目录，不能是文件系统根、仓库根或仓库祖先目录
- `ELMOS_REPOSITORY_ROOT`：本仓库绝对路径
- `ELMOS_UV_PATH`：精确 `uv` 可执行文件绝对路径
- `ELMOS_LOCAL_RUNNER_AUTH_TOKEN`：至少 24 字符的短期令牌；或使用 owner-only（0600）、非符号链接的绝对路径 `ELMOS_LOCAL_RUNNER_AUTH_TOKEN_FILE`，两者必须且只能配置一个
- `ELMOS_LOCAL_RUNNER_AUTH_TOKEN_EXPIRES_AT`：带时区、未来且不超过 24 小时的租约截止时间
- `ELMOS_LOCAL_RUNNER_TENANT_ID` 与 `ELMOS_LOCAL_RUNNER_ACTOR_ID`：该令牌唯一绑定的租户和 Actor
- `ELMOS_LOCAL_RUNNER_EXECUTOR=ROOTLESS_CONTAINER`：生产模式唯一允许的执行器；必须配置绝对 rootless Podman/Docker 路径。`HOST_DEVELOPMENT` 仅用于显式本地开发并在 `NODE_ENV=production` 下拒绝。

整库转换额外要求 `ELMOS_TRANSLATION_SOURCE_ROOT` 与
`ELMOS_TRANSLATION_CASES_ROOT` 两个管理员材料化的绝对只读目录。生产
Rootless 执行还要求 `ELMOS_TRANSLATION_RUNNER_IMAGE` 为
`name@sha256:<64 hex>` 不可变镜像；容器以只读根文件系统、只读源码/语料挂载、
默认拒绝网络、删除全部 capability、`no-new-privileges` 及 CPU/内存/PID 限额运行。

Spring 代理额外要求：

- `ELMOS_SPRING_PROXY_ENABLED=true`、`JAVA_ENGINE_BASE_URL` 与 `ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID`
- `ELMOS_SPRING_PROXY_AUTH_TOKEN`，或 owner-only 的绝对路径 `ELMOS_SPRING_PROXY_AUTH_TOKEN_FILE`，两者必须且只能配置一个
- `ELMOS_SPRING_PROXY_AUTH_TOKEN_EXPIRES_AT`：带时区、未来且不超过 24 小时
- `ELMOS_SPRING_PROXY_ACTOR_ID`：令牌唯一绑定的 Actor

令牌正确但租户或 Actor 请求头不匹配时返回 403。需求分析结果只在 30 分钟内有效，且摘要、Actor、租户和规范化 Intent 必须完全匹配；每份审阅摘要只能被一个任务消费。归档下载前和运行启动前都会重新计算摘要，工作区或归档发生漂移即失败关闭。

Web liveness 与 readiness 分别由 `/api/health?probe=liveness` 和
`/api/health?probe=readiness` 提供。备份前必须先由
`scripts/operations/generation_runner_backup.py quiesce` 阻断新写入并排空活动任务；
恢复会逐文件复算摘要且保持 `RESTORED_REQUIRES_RESUME`，直至同一授权 Actor
显式恢复。该本地演练不替代生产离机备份、RPO/RTO 或跨区 DR 证据。

## CI 业务线映射

CI 分别验证 Java reactor、商业计费 PostgreSQL 17/Flyway/RLS、.NET engine、Python engine、
frontend-client engine、30 条有向语言路线、project-synthesis engine、八语言精确工具链及
16 个 PostgreSQL JWT/OIDC 生产 Profile，并在 Chromium 桌面/移动视口运行关键 Web
旅程。Project Synthesis 作业额外验证 Batch 97-104 与 Product Closure/Convergence
分发。所有依赖安装均使用锁文件或不可变 Action 摘要；任一验证失败都会阻止 CI 成功。

## 备注：`modules/lowering` 链与本矩阵的关系

`modules/intake` → `modules/semantic` → `modules/uir` → `modules/skeleton` →
`modules/lowering` → `modules/dependency-migration` → `modules/framework-migration`
（另见 `docs/adr/ADR-0023-faithful-first-core-language-lowering.md`）
是一条独立、真实、有测试覆盖，但**已明确被产品执行路径取代，且未被 `apps/` 下任何控制器、CLI 或 Worker 调用**的历史参考架构。
本条此前只列出前五个模块；实测 `dependency-migration` 与 `framework-migration`
同样零 `apps/` 引用，且只被该链自身和 `modules/architecture-tests` 依赖，属于同一个死簇，共 7 个模块。
这 7 个模块目前仍在每次 `make backend` 中编译并执行测试。**不能直接从 `<modules>` 删除**：
`ArchitectureRulesTest` 对 `io.elmos.intake..` 至 `io.elmos.frameworkmigration..`
施加 ArchUnit 边界规则，模块消失后这些规则会对空类集静默通过。
退役必须在同一次变更里同时下线对应规则，并由真实 `make backend` 验证；
在此之前 `make backend-fast` 仅供本地迭代跳过该簇，`make verify` 与 CI 仍构建全部模块。
"全库跨语言转换 M29" 一行描述的能力完全建立在 `engines/polyglot-route-engine` 之上，与该链无关。
这不是本矩阵的遗漏——该链本就不在任何已发布业务线的请求路径上，也不得作为产品回退。
五个模块各自的 `README.md` 和 ADR-0023 的闭环决定（2026-07-28）记录了这一事实；
重新启用必须先通过新 ADR 消除双重权威，并重新取得 Batch 29 证据。

## 失败关闭规则

以下情况均不得解释为成功：`UNKNOWN`、`INCONCLUSIVE`、`NOT_RUN`、缺失或过期证据、执行者与验证者相同、未授权的外部操作、未绑定精确产物摘要、局部/稀疏工作区被当作完整工作区，以及只通过静态检查却声称真实运行、生产就绪或认证。

权威认证与产品闭环 gate 当前仍应返回 `BLOCKED`，直到对应外部证据真实产生并经过独立核验。这是预期的安全行为，不是待用假数据修复的测试失败。
