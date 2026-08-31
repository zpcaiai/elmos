import type { GenerationStage, GenerationTarget, MigrationCapability, ProductStage } from "./contracts";

export const generationTargets: GenerationTarget[] = [
  { id: "java", language: "Java", runtime: "21", framework: "Spring Boot 3.5.3", port: 8081, sourceSkill: "PG077–PG088", verificationCommand: "mvn -B package", verificationStatus: "NOT_RUN", maturity: "limited", productionProfiles: ["postgresql+jwt", "postgresql+oidc"], productionEntityScope: "multi-entity", accent: "amber", icon: "code" },
  { id: "python", language: "Python", runtime: "3.12", framework: "FastAPI 0.116.1", port: 8082, sourceSkill: "PG089–PG100", verificationCommand: "uv run pytest && uv run mypy src", verificationStatus: "NOT_RUN", maturity: "limited", productionProfiles: ["postgresql+jwt", "postgresql+oidc"], productionEntityScope: "multi-entity", accent: "blue", icon: "spark" },
  { id: "csharp", language: "C#", runtime: ".NET 10.0.301", framework: "ASP.NET Core 10", port: 8083, sourceSkill: "PG101–PG112", verificationCommand: "dotnet test -c Release", verificationStatus: "NOT_RUN", maturity: "limited", productionProfiles: ["postgresql+jwt", "postgresql+oidc"], productionEntityScope: "single-entity", accent: "violet", icon: "layers" },
  { id: "typescript", language: "TypeScript", runtime: "Node 26.0.0", framework: "NestJS 11.1.6 / Fastify 5.6.1", port: 8084, sourceSkill: "PG226", verificationCommand: "pnpm check && pnpm test && pnpm build", verificationStatus: "NOT_RUN", maturity: "limited", productionProfiles: ["postgresql+jwt", "postgresql+oidc"], productionEntityScope: "single-entity", accent: "cyan", icon: "code" },
  { id: "go", language: "Go", runtime: "1.25.0", framework: "net/http", port: 8085, sourceSkill: "PG237", verificationCommand: "go vet ./... && go test -race ./...", verificationStatus: "NOT_RUN", maturity: "limited", productionProfiles: ["postgresql+jwt", "postgresql+oidc"], productionEntityScope: "single-entity", accent: "green", icon: "code" },
  { id: "kotlin", language: "Kotlin", runtime: "2.2.20 / JVM 21", framework: "Ktor 3.2.3", port: 8086, sourceSkill: "PG250", verificationCommand: "gradle --no-daemon test build", verificationStatus: "NOT_RUN", maturity: "limited", productionProfiles: ["postgresql+jwt", "postgresql+oidc"], productionEntityScope: "single-entity", accent: "violet", icon: "layers" },
  { id: "php", language: "PHP", runtime: "8.4.12", framework: "Native HTTP modular service", port: 8087, sourceSkill: "PG263", verificationCommand: "php -l public/index.php && php tests/run.php", verificationStatus: "NOT_RUN", maturity: "limited", productionProfiles: ["postgresql+jwt", "postgresql+oidc"], productionEntityScope: "single-entity", accent: "blue", icon: "spark" },
  { id: "rust", language: "Rust", runtime: "1.89.0", framework: "Axum 0.8.4", port: 8088, sourceSkill: "PG287", verificationCommand: "cargo clippy && cargo test --locked", verificationStatus: "NOT_RUN", maturity: "limited", productionProfiles: ["postgresql+jwt", "postgresql+oidc"], productionEntityScope: "single-entity", accent: "amber", icon: "code" },
];

export const generationStages: GenerationStage[] = [
  { batch: "B46–B48", title: "需求发现", detail: "澄清实体、需求与验收条件" },
  { batch: "B49–B50", title: "架构约束", detail: "冻结运行时与框架版本" },
  { batch: "B51–B52", title: "工程蓝图", detail: "规划 API、测试和配置" },
  { batch: "B53–B57", title: "核心目标发射", detail: "Java、Python 与 C# 独立工程" },
  { batch: "B66–B71", title: "Polyglot 发射", detail: "TypeScript、Go、Kotlin、PHP 与 Rust" },
  { batch: "B80", title: "构建与交付", detail: "逐目标构建、探针、资产图与证据归档" },
];

export const installedSkillInventory = {
  codexSkillCount: 4319,
  runtimeSkillCount: 6442,
  countingRule: "directories-with-SKILL.md",
} as const;

export const migrationCapabilities: MigrationCapability[] = [
  { id: "M29", batch: 29, title: "跨语言路由", domain: "Directed language routes", description: "12 个方向的 typed-pure-function-v1 已通过精确本地工具链、独立 holdout 与代表性语料，提升为受限支持；任意整库语义和外部认证仍为 NOT_RUN。", skillCount: 20, schemaCount: 3, gateCommand: "scripts/batch29/run_route_gate.py", status: "LIMITED", icon: "code", accent: "cyan" },
  { id: "M30", batch: 30, title: "框架现代化", domain: "Framework modernization", description: "Spring Boot 2.7.18→3.5.3 的 Web、配置和生命周期子集已通过真实公共仓库、源/目标构建与启动验证；客户私库、Rootless 和外部独立认证仍为 NOT_RUN。", skillCount: 20, schemaCount: 4, gateCommand: "scripts/batch30/run_framework_gate.py", status: "LIMITED", icon: "workflow", accent: "blue" },
  { id: "M31", batch: 31, title: "数据库与数据平台", domain: "Database & data", description: "类型、约束、SQL、ETL 与逐项对账的精确迁移；ChinaDB 扩展已登记 13 个国产目标与 78 条规划路线，精确适配器和实库证据缺失时一律阻断。", skillCount: 69, schemaCount: 9, gateCommand: "scripts/batch31/run_database_gate.py", status: "READY", icon: "database", accent: "violet" },
  { id: "M32", batch: 32, title: "前端与客户端", domain: "Frontend & client", description: "路由、状态、权限、可访问性与真实浏览器旅程。", skillCount: 20, schemaCount: 7, gateCommand: "scripts/batch32/run_client_gate.py", status: "READY", icon: "layers", accent: "amber" },
  { id: "M33", batch: 33, title: "Cloud / IaC / DevOps", domain: "Cloud & infrastructure", description: "架构契约、IaC IR、计划、回滚与安全边界。", skillCount: 20, schemaCount: 8, gateCommand: "scripts/batch33/run_cloud_gate.py", status: "READY", icon: "cloud", accent: "blue" },
  { id: "M34", batch: 34, title: "超大组合调度", domain: "Portfolio scale", description: "组合图、分片、检查点、公平调度与 DR 回放。", skillCount: 22, schemaCount: 10, gateCommand: "scripts/batch34/run_portfolio_gate.py", status: "READY", icon: "box", accent: "green" },
  { id: "M35", batch: 35, title: "高级正确性验证", domain: "Advanced verification", description: "属性、模糊、模型、符号、并发与反例回放。", skillCount: 22, schemaCount: 13, gateCommand: "scripts/batch35/run_verification_gate.py", status: "EXPERIMENTAL", icon: "shield", accent: "violet" },
  { id: "M36", batch: 36, title: "开发者工作流", domain: "Developer experience", description: "IDE、CLI、预览、受保护区域、PR Bot 与离线边界。", skillCount: 18, schemaCount: 12, gateCommand: "scripts/batch36/run_developer_experience_gate.py", status: "EXPERIMENTAL", icon: "spark", accent: "cyan" },
  { id: "M37", batch: 37, title: "扩展 SDK 与 Marketplace", domain: "Extensions & marketplace", description: "ABI、沙箱、签名、发布者、安装、撤销与商业结算。", skillCount: 36, schemaCount: 25, gateCommand: "scripts/batch37/run_marketplace_gate.py", status: "EXPERIMENTAL", icon: "box", accent: "amber" },
];

export const productStages: ProductStage[] = [
  {
    batch: "B34", shortTitle: "租户身份", title: "可信租户与身份上下文", subtitle: "Tenant / Workload identity / JIT",
    status: "ENFORCED", icon: "shield",
    checks: [
      { label: "认证身份绑定", status: "ENFORCED", detail: "租户只从认证身份与可信资源绑定推导" },
      { label: "PostgreSQL RLS", status: "ENFORCED", detail: "缺失或模糊的租户上下文默认拒绝" },
      { label: "外部 IdP 实证", status: "NOT_RUN", detail: "真实企业 IdP 与工作负载身份尚未执行" },
    ],
    restrictions: ["不能从客户端参数信任 tenant_id", "JIT 与 break-glass 必须短期、可撤销、可审计"],
  },
  {
    batch: "B35", shortTitle: "代码源", title: "SCM 与高级工作空间", subtitle: "SCM / Commit / LFS / Workspace",
    status: "NOT_RUN", icon: "repository",
    checks: [
      { label: "精确提交解析", status: "READY", detail: "仓库身份由 Provider 实例与原生 ID 组成" },
      { label: "短期凭证租约", status: "READY", detail: "Provider Token 不进入持久化层" },
      { label: "真实 Provider 连接", status: "NOT_RUN", detail: "GitHub / GitLab 等尚未进行外部调用" },
    ],
    restrictions: ["Submodule 必须单独授权", "Sparse checkout 不是安全边界", "LFS 对象必须重新验证"],
  },
  {
    batch: "B36", shortTitle: "执行面", title: "Runner、Sandbox 与运营", subtitle: "Scheduler / Runner / Offline",
    status: "NOT_CONFIGURED", icon: "server",
    checks: [
      { label: "默认拒绝网络", status: "READY", detail: "仓库内容不能弱化 Sandbox 策略" },
      { label: "Epoch 与回执", status: "READY", detail: "通过幂等、回执与对账替代 exactly-once 宣称" },
      { label: "真实 Runner Attestation", status: "NOT_RUN", detail: "外部 Runner 与独立能力验证尚未绑定" },
    ],
    restrictions: ["源码只读挂载", "Rootless 运行", "Offline Permit 不能创造新权限"],
  },
  {
    batch: "B37", shortTitle: "证据", title: "证据与 Assurance Fabric", subtitle: "Artifact / Attestation / Judge",
    status: "REVIEW", icon: "file",
    checks: [
      { label: "生产者与验证者分离", status: "READY", detail: "执行者不能给自己的证据签发通过" },
      { label: "原生与归一化证据", status: "READY", detail: "两份证据独立保存并保留来源" },
      { label: "独立 Assurance 结论", status: "NOT_RUN", detail: "仍需真实外部证据和人工决定" },
    ],
    restrictions: ["UNKNOWN / INCONCLUSIVE / NOT_RUN 永不通过", "关键失败不能被聚合指标隐藏"],
  },
  {
    batch: "B38", shortTitle: "持续授权", title: "Policy 与持续授权", subtitle: "PAP / PIP / PDP / PEP",
    status: "BLOCKED", icon: "lock",
    checks: [
      { label: "签名 Policy Bundle", status: "READY", detail: "版本不可变、可撤销、可重放" },
      { label: "强制义务支持", status: "BLOCKED", detail: "任何未支持的 mandatory obligation 默认拒绝" },
      { label: "外部 PEP 回执", status: "NOT_RUN", detail: "控制面决策不是执行或批准回执" },
    ],
    restrictions: ["PAP / PIP / PDP / PEP 严格分离", "异常必须精确、到期并具备补偿控制"],
  },
];
