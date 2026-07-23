# ELMOS 业务线闭环矩阵

本矩阵用于区分两类状态：

- `REPOSITORY_CLOSED`：仓库内可以完成的实现、契约、测试、构建和保守门禁已经闭环。
- `EXTERNAL_GATE_REQUIRED`：必须依赖真实客户、生产等价环境、独立验证者或获授权的外部操作；在证据产生前保持 `NOT_RUN`，不得由本地测试替代。

## 业务线状态

| 业务线 | 用户入口与核心实现 | 仓库内闭环与验证 | 当前状态 | 尚需外部证据 |
| --- | --- | --- | --- | --- |
| 迁移与现代化 M1-M45 | Web Migration Studio、control-plane、语言与框架/数据/客户端/云迁移模块、各语言引擎 | 草稿创建/读取/删除形成浏览器内闭环；共享 Engine API、预算、选项和执行器枚举精确一致；Java、.NET、Python、TypeScript 和 Web 构建测试纳入 `make verify` | `REPOSITORY_CLOSED` | 代表性客户仓库、目标平台运行、独立验证与正式认证保持 `NOT_RUN` |
| 多语言项目生成 B46-B95 | `/generation`、`/api/capabilities/generation`、project-synthesis engine、Batch 66-95 Skills | 能力选择、参数编辑、草稿本地持久化/恢复/删除、精确 CLI 生成与复制闭环；损坏草稿失败关闭并限制为 50 条 | `REPOSITORY_CLOSED` | 非内置语言原生工具链、签名、设备/集群/云部署及生产交付保持 `NOT_RUN` |
| 工作区与 Private Runner | workspace-service、workspace manager、egress proxy、Compose 服务拓扑 | 工作区和秘密租约请求在提供者访问前完成身份、类型与 TTL 校验；策略/依赖故障返回稳定响应；默认拒绝出口 | `REPOSITORY_CLOSED` | 真实 rootless Runner 隔离、工作负载身份、远端证明、秘密租约与撤销演练保持 `NOT_RUN` |
| 验证、证据与认证 | java-engine-worker validation API、Batch 1-45 严格套件、补充套件、evidence contracts | 嵌套请求在执行前校验；同语义映射规范化后参与幂等指纹；终态不可改写；权威门禁按缺失证据失败关闭 | `REPOSITORY_CLOSED` | 逐用例执行者/独立验证者、原始证据、签名请求和信任库保持 `NOT_RUN` |
| Skills 与能力目录 | `.agents/skills`、`agent-skills/runtime`、`/skills` | UI 动态展示实际可调用 Skill 数量；新增业务线审计、生成旅程、跨服务运维闭环 Skills；各批次不可变清单与接口校验通过 | `REPOSITORY_CLOSED` | Skill 静态通过不等于客户、生产、行业或监管认证；相关证据保持 `NOT_RUN` |
| Web 产品体验 | `/`、`/migration`、`/generation`、`/commercialization`、`/skills` 及三组 API | 响应式页面、表单状态、空/错/成功反馈、浏览器本地草稿、能力 API、TypeScript 与 Next.js 生产构建闭环 | `REPOSITORY_CLOSED` | 真实浏览器/设备矩阵、无障碍人工审查、客户可用性验收保持 `NOT_RUN` |
| 运维、部署与可观测性 | 18 个运行时服务、24 个 Compose 服务、健康检查、runtime operability validator | Web 到 control-plane 路由闭环；名称/端口唯一；Java/.NET/TypeScript 公开错误边界扫描；13 个任务控制器强制 404/409；工作进程明确声明状态仅进程内保存 | `REPOSITORY_CLOSED` | 生产部署、持久任务恢复、SLO、告警值班、备份恢复、跨区 DR 和故障演练保持 `NOT_RUN` |
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
| 新 Skill 分发未进入总生产就绪门禁且 Makefile 绑定 Homebrew 路径 | 产品商业化、CI/开发者体验 | 使用可覆盖的 `UV ?= uv`；总门禁与 CI 纳入 Batch 97-104 及 Product Closure/Convergence | production-readiness 测试检查依赖集合与平台无关命令 |
| Vercel 从仓库根目录部署时未识别嵌套 Next.js 应用，生成空部署并返回边缘层 404 | Web 产品体验、运维部署 | Vercel 项目 Root Directory 精确设置为 `apps/web-console`，应用目录内声明 Next.js 框架并由锁定的 pnpm 版本安装/构建；不增加重写或额外公开入口 | production-readiness 配置测试、Web 生产构建、推送后的 Vercel 部署与根路由验证 |

## CI 业务线映射

CI 分别验证 Java reactor、.NET engine、Python engine、frontend-client engine、project-synthesis engine 和 Web console。Project Synthesis 作业额外验证 Batch 97-104 与 Product Closure/Convergence 分发。所有依赖安装均使用锁文件；任一验证失败都会阻止 CI 成功。

## 失败关闭规则

以下情况均不得解释为成功：`UNKNOWN`、`INCONCLUSIVE`、`NOT_RUN`、缺失或过期证据、执行者与验证者相同、未授权的外部操作、未绑定精确产物摘要、局部/稀疏工作区被当作完整工作区，以及只通过静态检查却声称真实运行、生产就绪或认证。

权威认证与产品闭环 gate 当前仍应返回 `BLOCKED`，直到对应外部证据真实产生并经过独立核验。这是预期的安全行为，不是待用假数据修复的测试失败。
