# ELMOS 最小可运营生产拓扑

生成日期：2026-07-28
目的：把 `deploy/compose/docker-compose.yml` 的 24 个运行服务收敛为**第一版商业化实际需要部署的集合**。

本文是**部署规划**，不是部署证据。文中任何服务被列入"必需"都不代表它已在生产环境验证；
`mature-product-packs/batch45/.../residual-risks.json` 的 RISK-DEPLOY-001 仍为 `OPEN`。

---

## 1. 现状

`deploy/` 目录只有 8 个文件：

```
deploy/compose/docker-compose.yml              24 个服务 + 5 个卷
deploy/rootless-docker/docker-compose.rootless.yml
deploy/air-gap/runner-namespace.yaml
deploy/local-runner/runner.env.example
deploy/release-bundle/release-manifest.template.json
+ 3 个 README
```

**没有 Kubernetes/Helm、没有生产 IaC、没有 staging 环境定义、没有多环境配置分层。**

---

## 2. 首发范围假设

按 `COMMERCIALIZATION_GAP_ASSESSMENT.md` 第 2 节的证据分档，第一版只上：

- **A 档**：多语言项目生成 `/generation`（8 目标，自助订阅）
- **B 档（可选，按项目报价）**：Spring 升级 `/spring`（仅 Boot 2.7.18 / Java 17 / Maven）
- **B 档（支撑能力）**：Git 仓库接入 `/repositories`

**不上**：`/translation` 整库跨语言转换（C 档）、`/commercialization` 控制层页面、
以及所有 Batch 12–18 企业裁判层。

---

## 3. 最小必需服务集（Tier 1）

| 服务 | 作用 | 首发是否必需 | 依据 |
|---|---|---|---|
| `postgres` | 权威数据（含 V1–V50 计费/计量 Schema） | ✅ 必需 | 计费与任务状态的唯一权威 |
| `web-console` | 产品门面 + BFF（19,028 行） | ✅ 必需 | 所有用户入口 |
| `control-plane` | 任务/工作区控制面（3,464 行） | ✅ 必需 | `ELMOS_CONTROL_PLANE_BASE_URL` |
| `commercial-api` | 计费、订阅、试用、额度预留（1,983 行） | ✅ 必需 | `ELMOS_COMMERCIAL_API_URL` |
| `workspace-service` | 工作区与秘密租约（2,563 行） | ✅ 必需 | 仓库接入与生成前置 |
| `minio` / S3 | 产物存储 | ✅ 必需 | 归档下载、保留期策略 |
| **Runner 池**（compose 中不存在，需新建） | rootless 容器执行生成/构建/启动探针 | ✅ 必需 | 产品核心动作 |

Tier 1 = **6 个服务 + 1 个待建 Runner 池**。

---

## 4. 条件必需（Tier 2，随首发范围决定）

| 服务 | 触发条件 |
|---|---|
| `java-engine-worker`（6,875 行） | 上 Spring 升级业务线时必需 |
| `java-engine-verifier`（1,333 行） | 上 Spring 升级验证链路时必需 |
| `egress-proxy` | 需要受控出网时必需（默认拒绝网络策略的执行点） |
| `agent-gateway`（95 行） | 需要 Coding Agent 长尾修复时；注意模型目录当前全部 `NOT_CONFIGURED` |

---

## 5. 首发不部署（Tier 3）

以下 compose 服务在首发范围内**没有请求路径**，部署它们只会扩大攻击面与运维成本：

```
dotnet-engine-worker                 frontend-client-engine-worker
python-engine-worker*                database-data-engine-worker
infrastructure-engine-worker         security-compliance-engine-worker
test-quality-engine-worker           mainframe-engine-worker
enterprise-integration-engine-worker enterprise-suite-engine-worker
software-delivery-platform-engine-worker
ai-platform-engine-worker            edge-iot-industrial-engine-worker
operations-sre-itsm-engine-worker    enterprise-architecture-engine-worker
enterprise-control
```

`*` 若生成链路的 Python 目标由独立 worker 承担，则 `python-engine-worker` 升为 Tier 1；
部署前需按 `engines/project-synthesis-engine` 的实际调用路径确认。

**注意**：`ai-platform-engine`、`edge-iot-industrial-engine`、
`operations-sre-itsm-engine`、`software-delivery-platform-engine`、
`enterprise-architecture-engine` 的可执行代码均 ≤ 65 行，
`composite-engine` 与 `component-dialect-engine` 为 0 行。

---

## 6. 建议部署形态

### 6.1 第一版（成本优先，2–3 台机器）

```
┌─────────────────────────────────────────────┐
│ 托管 Web（Vercel）                            │
│   apps/web-console  (Root Directory 已配好)   │
└───────────────┬─────────────────────────────┘
                │ HTTPS（仅 BFF 出站）
┌───────────────▼─────────────────────────────┐
│ 应用主机 A（4C8G）                             │
│   control-plane / commercial-api             │
│   workspace-service / egress-proxy           │
│   （compose 或 systemd + podman）             │
└───────────────┬─────────────────────────────┘
                │ 内网
┌───────────────▼──────────┐  ┌───────────────┐
│ Runner 主机 B（8C16G）     │  │ 托管 PostgreSQL │
│   rootless podman 池      │  │  （Neon 等）     │
│   只读根 / 默认拒绝网络     │  └───────────────┘
│   CPU/内存/PID 限额        │
└──────────────────────────┘  ┌───────────────┐
                              │ 对象存储 S3/MinIO │
                              └───────────────┘
```

Runner 主机**必须与应用主机物理/网络隔离**：它执行的是客户代码派生的构建过程。
仓库既有约束已经写明"客户代码不得在控制平面进程内执行"。

### 6.2 扩展版（客户量上来后）

- Runner 池换成 K8s Job + 独立 node pool（taint/toleration 隔离）
- 应用层无状态化后横向扩容
- 加 staging 环境，与生产同拓扑不同规模

---

## 7. 环境分层

当前仓库只有"本地开发"与"CI"两层。商业化最少需要三层：

| 环境 | 用途 | 数据库 | Runner |
|---|---|---|---|
| `dev` | 本地开发 | 本地 PG 17 | `HOST_DEVELOPMENT` 允许 |
| `staging` | 上线前验证、升级/回滚演练 | 独立 PG 实例 | `ROOTLESS_CONTAINER` |
| `production` | 客户 | 托管 PG（含 PITR） | `ROOTLESS_CONTAINER` |

`staging` 是关闭 RISK-DEPLOY-001（升级/回滚/混版路径）的必要条件——
没有 staging 就没有演练场，风险无法闭合。

---

## 8. 部署前必须闭合的检查（摘要）

完整清单见 `GO_LIVE_RUNBOOK.md`。最低限度：

1. 所有 Tier 1 服务的 liveness / readiness 探针在目标环境返回 UP
2. `commercial-api` 的 `BillingDatabaseHealthIndicator` 目录版本 == 应用编译版本
3. Runner 以非 root、只读根、删除全部 capability、`no-new-privileges`、
   默认拒绝网络、CPU/内存/PID 限额启动，并有真实断言证据
4. Actuator metrics 只在内网可达
5. 数据库运行角色确认为 `NOSUPERUSER NOBYPASSRLS`，且与迁移 owner 不同
6. 备份可用性经过一次真实恢复演练（不是备份成功，是**恢复成功**）
