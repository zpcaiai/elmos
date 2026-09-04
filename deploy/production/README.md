# deploy/production

更新日期：2026-09-04
本目录是**第一版商业化部署的制品**。它们尚未在任何环境执行过——
RISK-DEPLOY-001 与 RISK-SRE-001 保持 `OPEN`，直到在 staging 真实起停并留下证据。

```
deploy/production/
├── README.md                              本文件
├── SPRING_LAUNCH_EVIDENCE.md              Spring 签名外部证据接入与重放流程
├── elmos-commercial.env.example           全部生产环境变量模板
├── compose/
│   ├── docker-compose.production.yml      应用安全域 Tier 1 编排（YAML 已校验，未执行）
│   ├── docker-compose.spring-application.yml Spring 应用域显式激活 overlay（未执行）
│   └── docker-compose.spring-runner.yml   独立 Rootless Spring Runner（未执行）
├── postgres/
│   └── configure_hosted_runtime.sql       对象存储后端显式激活
├── runner/
│   ├── RUNNER_PRODUCTION_BASELINE.md      已实现托管执行面与证据边界
│   ├── nginx.spring-runner.conf           三条精确 HMAC API 的 HTTPS ingress
│   ├── spring-runner.env.example           Runner-only 严格 allowlist 数据模板
│   └── validate_spring_runner_topology.py 静态/主机/运行中只读 preflight
├── observability/
│   └── prometheus-rules.yml               12 条告警（promtool 3.5.0 校验通过）
└── backup/
    └── RESTORE_DRILL.md                   恢复演练手册（关闭 RISK-DATA-001 的唯一途径）
```

配套脚本：

- `scripts/operations/provision_runner_host.sh` —— Runner 主机预置与失败关闭校验
- `scripts/operations/configure_control_plane_runtime_role.sh` —— 控制面最小权限运行角色
- `scripts/commercial/validate_pricing_catalog_publication.py` —— 定价目录发布门禁
- `scripts/batch30/validate_spring_launch_readiness.py` —— Spring 精确首发路线、生产环境与外部证据门禁
- `scripts/batch30/spring_launch_evidence.py` —— 内容寻址证据与 Ed25519 收据验证器（不生成通过声明）

---

## 各制品的验证状态（不要越级引用）

| 制品 | 已验证 | 未验证 |
|---|---|---|
| `docker-compose.production.yml` + `docker-compose.spring-application.yml` | 非 Spring 基线不挂载 engine HMAC；显式 overlay 才向 BFF/Worker 精确挂载同一文件并启用多租户认证；Spring 静态首发合同已校验 | **从未 `up` 过**；`read_only`/`user` 标记 VERIFY-REQUIRED 的项依赖镜像实际写入路径，Spring 外部证据仍 `NOT_RUN` |
| `docker-compose.spring-runner.yml` | 独立安全域、三服务、Rootless socket 单一持有者、内部 edge/broker 网络、proxy-only 执行出网、精确 HTTPS 路由与 owner-only Secret 契约可由静态 validator 重放 | **从未 `up` 过**；真实 Rootless daemon 的 internal bridge + published-port 可达性、私有数据库 endpoint、TLS、网络策略、镜像和跨主机共享存储均 `NOT_RUN` |
| `prometheus-rules.yml` | `promtool check rules` → SUCCESS: 12 rules found | 未对接指标源；无一条告警被真实触发/恢复；阈值未用基线校准 |
| `provision_runner_host.sh` | `bash -n` 通过；`--check` 与 4 类危险路径守卫已实测（退出码 3/4 符合预期） | `--apply` 从未在真实主机执行 |
| `validate_pricing_catalog_publication.py` | 6 个用例实测通过（含伪造 PUBLISHED 被阻断、免费套餐被改成收费被拒） | 未接入 CI |
| `RESTORE_DRILL.md` | —— | **演练本身未执行**；这是关闭 RISK-DATA-001 的前提 |
| `RUNNER_PRODUCTION_BASELINE.md` | 持久队列、Runner Agent、租约/轮换、隔离和对象存储实现已通过本地测试 | **未部署到真实 Runner 集群**；真实 Podman、网络策略、多节点故障与独立隔离验证均 `NOT_RUN` |

---

## 起步顺序

```bash
# 1. 环境变量
cp deploy/production/elmos-commercial.env.example /srv/elmos/elmos.env
chmod 0600 /srv/elmos/elmos.env
# 逐项填写；未填项对应能力会失败关闭，这是预期行为

# 管理员登录邮件 Secret：Web 容器以 UID 10001 运行，文件必须 owner-only 且可读。
sudo install -d -o 10001 -g 10001 -m 0700 /srv/elmos/secrets
sudo install -o 10001 -g 10001 -m 0600 /dev/null /srv/elmos/secrets/resend-api-key
# 通过 Secret Manager 或无回显的受控流程写入 Resend API Key；不要写入 shell 历史。
# 网络策略仅为 Web Console 放行 api.resend.com:443；禁止重定向与其他邮件端点。

# 非 Spring 基线不需要也不会挂载 engine HMAC。仅在启用 Spring 前，由 Secret
# Manager 在应用主机创建 launch env 指定的 owner-only engine HMAC 文件；不要用
# /dev/null、目录自动创建、环境变量 Secret 或 group/other 读权限代替。

# 2. PostgreSQL 迁移完成后配置 NOBYPASSRLS 运行角色与对象后端
scripts/operations/configure_control_plane_runtime_role.sh
psql "${ELMOS_DATABASE_URL#jdbc:}" \
  -f deploy/production/postgres/configure_hosted_runtime.sql \
  -v backend_kind=S3 ...                         # 其余精确参数见脚本头

# 3. 通用 Runner 主机（独立机器）
ELMOS_RUNNER_USER=elmos-runner ELMOS_RUNNER_ROOT=/srv/elmos/runner \
  scripts/operations/provision_runner_host.sh --check
sudo -E scripts/operations/provision_runner_host.sh --apply

# 4. 每个 Runner 节点分别签发一次性 enrollment，再渲染 Agent 清单
# 同一个 enrollment Secret 绝不能跨副本复用。

# 5. Spring Runner 静态合同（不需要 Docker，也不会写外部证据）
uv run --quiet --with pyyaml \
  python deploy/production/runner/validate_spring_runner_topology.py

# 6. 在 Spring 专用 Linux 主机、以 rootless daemon owner 身份预置控制网络。
# 该 internal 网络还必须接入唯一批准的私有 PostgreSQL proxy/endpoint；后者的
# 外联由宿主防火墙单独 allowlist，并保留外部证明。
docker network create --internal \
  --label io.elmos.network.default-deny=true \
  --label io.elmos.network.purpose=spring-runner-control \
  elmos-spring-runner-control

# 7. 将 deploy/production/runner/spring-runner.env.example 复制到下面的仓库外路径，
# 填写精确值并设置父目录 0700、文件 0400/0600。把 runner env 当作数据解析，
# 然后做不变更主机的 preflight。禁止 source/eval；
# parser 使用 Runner 专属 allowlist，拒绝未知项、重复项、插值和命令语法，并要求
# 仓库外绝对路径、非 symlink、owner-only 文件及 0700 父目录。
# 该文件只供 preflight 与 `docker compose --env-file` 做变量替换；三个 Runner
# service 均禁止 service-level `env_file`，因此 TLS/Socket/宿主路径等不会整包注入容器。
# --check-host 验证 rootless SecurityOptions、internal 控制网络、digest 格式、
# socket、目录、Secret owner/mode/inode 和 TLS/config；它不会制造 attestation。
uv run --quiet --with pyyaml \
  python deploy/production/runner/validate_spring_runner_topology.py \
  --environment-file /srv/elmos/spring-runner/runner.env --check-host

# 8. 在该独立主机启动 Runner；绝不能与应用 compose 叠加。
docker compose --env-file /srv/elmos/spring-runner/runner.env \
  -f deploy/production/compose/docker-compose.spring-runner.yml up -d
uv run --quiet --with pyyaml \
  python deploy/production/runner/validate_spring_runner_topology.py \
  --environment-file /srv/elmos/spring-runner/runner.env --check-running

# spring-runner-edge 与 spring-runner-broker 都是 internal bridge。Rootless 端口
# 转发必须仍能把批准的宿主私网地址映射到 ingress:8443；从应用主机执行 TLS 握手和
# 经 HMAC 的 canary 请求并归档收据。若所选引擎不能同时满足 internal + published
# port，保持上线 BLOCKED，不得把 edge 改成可任意出网的普通 bridge。

# 9. 应用主机（先在 staging）。把 spring-launch.env.example 复制到仓库外，
# 由同一受控配置源生成 Compose 与门禁使用的 Spring 值；chmod 0600，禁止 source/eval。
python3 scripts/batch30/validate_spring_launch_readiness.py
python3 scripts/batch30/validate_spring_launch_readiness.py \
  --environment-file /controlled/spring.env \
  --compose-environment-file /srv/elmos/elmos.env
docker compose --env-file /srv/elmos/elmos.env \
  -f deploy/production/compose/docker-compose.production.yml up -d
docker compose --env-file /srv/elmos/elmos.env \
  --env-file /controlled/spring.env \
  -f deploy/production/compose/docker-compose.production.yml \
  -f deploy/production/compose/docker-compose.spring-application.yml \
  --profile spring up -d                           # 只在售卖 Spring 升级时

# 10. 正式放量必须再提供签名外部证据、独立信任库和证据字节根；
# 模板中的 NOT_RUN、URL/摘要自报、单方签名或仓库内收据都不能通过。
# APPROVED_SPRING_TRUST_STORE_DIGEST 必须来自独立审批/配置系统，禁止在同一
# 命令里从待验证 trust store 临时计算后自我固定。
make spring-launch-gate \
  SPRING_ENV_FILE=/controlled/spring.env \
  ELMOS_ENV_FILE=/srv/elmos/elmos.env \
  SPRING_EXTERNAL_EVIDENCE=/controlled/evidence/spring-launch-receipt.json \
  SPRING_TRUST_STORE=/controlled/trust/spring-trust-store.json \
  SPRING_TRUST_STORE_DIGEST="$APPROVED_SPRING_TRUST_STORE_DIGEST" \
  SPRING_EVIDENCE_ROOT=/controlled/evidence \
  SPRING_ENVIRONMENT_ID=spring-staging-cn-1 \
  SPRING_DEPLOYMENT_ID="$SPRING_DEPLOYMENT_ID" \
  SPRING_PROVIDER=private-linux \
  SPRING_REGION=cn-north-1 \
  SPRING_ENVIRONMENT_CLASS=STAGING

# 11. 告警
promtool check rules deploy/production/observability/prometheus-rules.yml

# 12. 恢复演练（上线前必做一次）
# 按 deploy/production/backup/RESTORE_DRILL.md 执行，产出 drills/drill-<时间戳>.md

# 13. 定价目录门禁（CI 常驻 + 开售前）
python3 scripts/commercial/validate_pricing_catalog_publication.py
python3 scripts/commercial/validate_pricing_catalog_publication.py --check-publishable
```

`SPRING_ENV_FILE` 的 19 个 Spring 值必须与实际 `ELMOS_ENV_FILE` 完全一致；后者
还必须把 `ELMOS_ENV_FILE` 自身设置为同一绝对路径。门禁以无 shell、无插值的数据
解析器稳定读取两者，并把实际 Compose env 文件的字节摘要纳入
`SPRING_CONFIGURATION_DIGEST`。两份文件与调用进程均不得设置
`SPRING_APPLICATION_JSON`、`JAVA_TOOL_OPTIONS`、`_JAVA_OPTIONS`、
`JDK_JAVA_OPTIONS`、servlet/context path 或 Spring config/profile 覆盖；不要
`source`/`eval` 任一文件。生产 overlay 同时在 Worker 容器边界清空 JVM/JSON/path
覆盖且不向 Worker 注入宽泛应用 env_file。

外部 staging 收据还必须引用并摘要绑定该部署的原始容器 inspect 产物，证明镜像
`ENV`、Compose 合并和运行时层之后的 Worker effective environment 仍与签名配置
一致；只提供两份宿主 env 文件摘要不能通过正式证据门禁。

无外部收据的 Spring preflight 成功输出明确包含：

```text
SPRING_LAUNCH_GATE=READY_FOR_EXTERNAL_GATE
EXTERNAL_EVIDENCE_INTAKE=NOT_RUN
CERTIFICATION=NOT_CERTIFIED
```

签名收据完整通过时也只会输出
`SPRING_LAUNCH_GATE=EXTERNAL_GATE_VERIFIED_NOT_CERTIFIED`、
`EXTERNAL_EVIDENCE_INTAKE=VALIDATED_NOT_CERTIFIED` 和
`CERTIFICATION=NOT_CERTIFIED`。它证明收据通过仓库的真实性/绑定校验，不替代
Batch 30 保守认证门禁，也不授权部署或开售。

## Spring 两个安全域与 Secret 所有权

应用主机运行 Web BFF 和 Java Engine Worker，二者都使用容器 UID/GID
`10001:10001`。该主机上的 Secret 父目录为 `0700`、owner `10001:10001`，四个
文件为 `0400`（受控轮换期间可为 `0600`）：

- `engine.hmac`：仅 BFF 与 Worker，绝不进入 Runner；
- `verifier.hmac`、`transformer.hmac`、`runtime.hmac`：Worker 侧的三个调用密钥。

独立 Runner 主机只接收后三个逻辑密钥的**独立文件副本**。broker Secret 父目录
由 rootless daemon 的宿主 UID/GID 持有且为 `0700`；文件由容器 UID/GID 10001
对应的 mapped host UID/GID 持有且为 `0400`。Compose 中 broker 仍以 10001 运行，
supplementary group 0 只用于 rootless Docker socket。不得用 `0444`、group/other
读权限、硬链接或同一 inode 解决跨 user namespace 可读性。三个逻辑密钥和
`engine.hmac` 四者的值不得复用；对应 Worker/broker 副本必须由 Secret Manager
协调轮换并在撤销后删除旧 inode。

应用 Worker 与 Runner broker 必须把同一个租户/Run 内容寻址 POSIX 文件系统挂到
`ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH`。该路径相同只是校验条件，不足以证明是同一
存储；staging 必须用跨主机写入/摘要/读取和并发租户隔离测试形成外部收据。

第 13 步当前返回：

```
DECISION=PUBLICATION_BLOCKED   （--check-publishable，退出码 3）
  - sellerLegalEntityStatus='NOT_CONFIGURED'
  - taxStatus='NOT_CONFIGURED'
  - paymentStatus='NOT_CONFIGURED'
  - costValidationStatus='NOT_RUN'
  - taxPresentation='UNSPECIFIED'
```

**这是正确结果**，不是需要修的测试失败。它会一直阻断到经营主体、税务、
支付商户和单位经济性四件事真的做完为止。

---

## 建议接入 CI

在既有 `.github/workflows/ci.yml` 增加一个轻量作业，防止定价目录被误改：

```yaml
  pricing-catalog-gate:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5
      - run: python3 scripts/commercial/validate_pricing_catalog_publication.py
```

注意用 `verify` 模式（不加 `--check-publishable`）：它只在目录**声称 PUBLISHED 却没有
闭合前置条件**时失败，不会因为目录还是 DRAFT 就让 CI 变红。
`--check-publishable` 属于开售前的人工门禁，不适合放进日常 CI。
