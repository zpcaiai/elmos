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
| Spring 老项目翻新 M30 | `/spring`、Spring 指纹探测器、受控代理、Java Worker、`spring-boot-2-7-18-to-3-5-3` Pack | 区分经典 Spring 与 Boot，识别 XML/注解、Jakarta 和 MVC/WebFlux 阻断；真实任务、取消/重试、日志、独立摘要验证、产物与运行态形成闭环；下载响应绑定长度、ETag 与 SHA-256，浏览器复算字节摘要后才交付；代理默认关闭并绑定可信单租户 | `REPOSITORY_CLOSED` | 客户源仓真实基线、目标启动/数据/安全等价、独立 holdout 与外部认证保持 `NOT_RUN` |
| 全库跨语言转换 M29 | `/translation`、12 个方向 Route Pack、polyglot-route engine、精确工具链清单 | 四种语言形成 12 条方向独立路线；`typed-pure-function-v1` 已完成开发、holdout、代表性编译与行为回放；整库执行确定性只读扫描、稳定读取、内容摘要和逐源文件工作单元拆分，UI 只接受与仓库/路线完全匹配的清单；不把工作单元发现扩张为整库成功 | `REPOSITORY_CLOSED` | 对象图、异常、异步、I/O、框架、数据库、并发、真实客户整库逐单元执行与独立验证保持 `NOT_RUN` |
| 多语言项目生成 B46-B95 | `/generation`、生成 API、本地 Runner、project-synthesis engine、Batch 66-95 Skills | 8 个精确目标；草稿、结构化分析、开放问题、一次性审阅摘要、显式批准、生成/验证、文件摘要复算、归档下载、启动健康探针与停止形成闭环；刷新后可用完整 UUID、租户、Actor 和重新输入的短期令牌恢复原子持久化任务；生成 CI Action 与基础镜像均固定到不可变摘要；Python 的 PostgreSQL 17.5 + JWT/OIDC 精确配置已完成真实本地迁移、启动、鉴权、RLS 租户隔离和集成测试；缺失工具链逐目标保持 `NOT_RUN` | `REPOSITORY_CLOSED` | 其他语言的生产持久化/身份配置、外部托管 PostgreSQL 与真实 IdP、完整传递依赖 SBOM/签名、设备/集群/云部署、独立验证及生产交付保持 `NOT_RUN` |
| 工作区与 Private Runner | workspace-service、workspace manager、egress proxy、Compose 服务拓扑 | 工作区和秘密租约请求在提供者访问前完成身份、类型与 TTL 校验；策略/依赖故障返回稳定响应；默认拒绝出口 | `REPOSITORY_CLOSED` | 真实 rootless Runner 隔离、工作负载身份、远端证明、秘密租约与撤销演练保持 `NOT_RUN` |
| 验证、证据与认证 | java-engine-worker validation API、Batch 1-45 严格套件、补充套件、evidence contracts | 嵌套请求在执行前校验；同语义映射规范化后参与幂等指纹；终态不可改写；权威门禁按缺失证据失败关闭 | `REPOSITORY_CLOSED` | 逐用例执行者/独立验证者、原始证据、签名请求和信任库保持 `NOT_RUN` |
| Skills 与能力目录 | `.agents/skills`、`agent-skills/runtime`、`/skills` | UI 展示实际可调用 Skill 数量，并由生产就绪门禁逐目录核对，库存漂移会失败关闭；新增业务线审计、生成旅程、跨服务运维闭环 Skills；各批次不可变清单与接口校验通过 | `REPOSITORY_CLOSED` | Skill 静态通过不等于客户、生产、行业或监管认证；相关证据保持 `NOT_RUN` |
| Web 产品体验 | `/`、`/spring`、`/translation`、`/generation`、`/migration`、`/commercialization`、`/skills` 及能力/任务 API | 响应式页面、表单状态、空/错/成功反馈、浏览器草稿、保守状态、TypeScript 与 Next.js 生产构建闭环；Chromium、Firefox、WebKit 及 Chromium/WebKit 移动视口执行自动可访问性、键盘、失败关闭与无横向溢出检查；有副作用的真实生成/运行旅程只在隔离 Chromium 项目执行一次 | `REPOSITORY_CLOSED` | Firefox/WebKit 的有副作用 Runner 旅程、辅助技术人工审查与客户可用性验收保持 `NOT_RUN` |
| 运维、部署与可观测性 | 18 个运行时服务、24 个 Compose 服务、Web/Runner 健康检查、runtime operability validator | Web 到 control-plane 路由闭环；名称/端口唯一；Java/.NET/TypeScript 公开错误边界扫描；13 个任务控制器强制 404/409；项目生成任务使用租户目录原子持久化、重启失败关闭、0600 Secret 文件、维护期拒绝写入、内容寻址备份/逐文件校验/静默恢复；非 root 只读 Web 容器声明健康探针 | `REPOSITORY_CLOSED` | 真实生产部署、外部 Secret Provider、SLO/告警值班、离机保留、生产 RPO/RTO、跨区 DR 和故障演练保持 `NOT_RUN` |
| 产品商业化 B34-B56A 与 Convergence | commercialization UI/API、Product Skills、closure/convergence control plane | 产品闭环/收敛 Skills 的来源、摘要、接口和反伪造校验通过；CI 与 `production-readiness-check` 都覆盖 Batch 97-104 和 closure/convergence；缺失外证时 gate 返回 `BLOCKED` | `REPOSITORY_CLOSED` | 至少两个独立设计伙伴、独立审查、客户验收、单位经济性、GA/生产批准保持 `NOT_RUN` |

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
| 下载按钮信任服务端元数据，浏览器未复算 Spring ZIP | Spring 老项目翻新、Web 产品体验 | Worker 下载响应加入长度、ETag 和 SHA-256，Next.js 代理透传，浏览器复算长度与摘要，不一致拒绝交付 | Java reactor 测试、Spring Playwright 下载旅程 |
| 生成项目的 CI 使用可变 Action 标签 | 多语言项目生成、供应链 | 8 个目标模板的所有 GitHub Action 固定为 40 位上游提交摘要并保留版本注释 | Project Synthesis 测试拒绝任意可变或格式错误的 `uses:` 引用 |
| 生成项目的基础镜像使用可变标签，Python/PostgreSQL 文案与运行配置漂移 | 多语言项目生成、供应链、Web 产品体验 | 8 个目标的所有非 `scratch` 基础镜像固定到官方多架构清单 SHA-256；Python 统一为 3.12.12，PostgreSQL 统一为 17.5；UI、README、CI、rootless Runner 与本地运行器共用精确契约 | Project Synthesis 测试拒绝任意可变/格式错误镜像；全仓契约测试拒绝版本漂移；JWT 与 OIDC 均通过真实本地 PostgreSQL 17.5 验收 |
| 新 Skill 分发未进入总生产就绪门禁且 Makefile 绑定 Homebrew 路径 | 产品商业化、CI/开发者体验 | 使用可覆盖的 `UV ?= uv`；总门禁与 CI 纳入 Batch 97-104 及 Product Closure/Convergence | production-readiness 测试检查依赖集合与平台无关命令 |
| Vercel 从仓库根目录部署时未识别嵌套 Next.js 应用，生成空部署并返回边缘层 404 | Web 产品体验、运维部署 | Vercel 项目 Root Directory 精确设置为 `apps/web-console`，应用目录内声明 Next.js 框架并由锁定的 pnpm 版本安装/构建；不增加重写或额外公开入口 | production-readiness 配置测试、Web 生产构建、推送后的 Vercel 部署与根路由验证 |

## 三条核心业务线的本地执行边界

Spring 代理和项目生成 Runner 都默认关闭。启用项目生成 Runner 时，以下变量必须全部显式配置；Web UI 不会显示或持久化令牌：

- `ELMOS_LOCAL_RUNNER_ENABLED=true`
- `ELMOS_LOCAL_RUNNER_ROOT`：专用绝对目录，不能是文件系统根、仓库根或仓库祖先目录
- `ELMOS_REPOSITORY_ROOT`：本仓库绝对路径
- `ELMOS_UV_PATH`：精确 `uv` 可执行文件绝对路径
- `ELMOS_LOCAL_RUNNER_AUTH_TOKEN`：至少 24 字符的短期令牌；或使用 owner-only（0600）、非符号链接的绝对路径 `ELMOS_LOCAL_RUNNER_AUTH_TOKEN_FILE`，两者必须且只能配置一个
- `ELMOS_LOCAL_RUNNER_AUTH_TOKEN_EXPIRES_AT`：带时区、未来且不超过 24 小时的租约截止时间
- `ELMOS_LOCAL_RUNNER_TENANT_ID` 与 `ELMOS_LOCAL_RUNNER_ACTOR_ID`：该令牌唯一绑定的租户和 Actor
- `ELMOS_LOCAL_RUNNER_EXECUTOR=ROOTLESS_CONTAINER`：生产模式唯一允许的执行器；必须配置绝对 rootless Podman/Docker 路径。`HOST_DEVELOPMENT` 仅用于显式本地开发并在 `NODE_ENV=production` 下拒绝。

令牌正确但租户或 Actor 请求头不匹配时返回 403。需求分析结果只在 30 分钟内有效，且摘要、Actor、租户和规范化 Intent 必须完全匹配；每份审阅摘要只能被一个任务消费。归档下载前和运行启动前都会重新计算摘要，工作区或归档发生漂移即失败关闭。

Web liveness 与 readiness 分别由 `/api/health?probe=liveness` 和
`/api/health?probe=readiness` 提供。备份前必须先由
`scripts/operations/generation_runner_backup.py quiesce` 阻断新写入并排空活动任务；
恢复会逐文件复算摘要且保持 `RESTORED_REQUIRES_RESUME`，直至同一授权 Actor
显式恢复。该本地演练不替代生产离机备份、RPO/RTO 或跨区 DR 证据。

## CI 业务线映射

CI 分别验证 Java reactor、.NET engine、Python engine、frontend-client engine、project-synthesis engine 和 Web console。Project Synthesis 作业额外验证 Batch 97-104 与 Product Closure/Convergence 分发。所有依赖安装均使用锁文件；任一验证失败都会阻止 CI 成功。

## 失败关闭规则

以下情况均不得解释为成功：`UNKNOWN`、`INCONCLUSIVE`、`NOT_RUN`、缺失或过期证据、执行者与验证者相同、未授权的外部操作、未绑定精确产物摘要、局部/稀疏工作区被当作完整工作区，以及只通过静态检查却声称真实运行、生产就绪或认证。

权威认证与产品闭环 gate 当前仍应返回 `BLOCKED`，直到对应外部证据真实产生并经过独立核验。这是预期的安全行为，不是待用假数据修复的测试失败。
