# deploy/production

更新日期：2026-09-05
本目录是**第一版商业化部署的制品**。它们尚未在任何环境执行过——
RISK-DEPLOY-001 与 RISK-SRE-001 保持 `OPEN`，直到在 staging 真实起停并留下证据。

```
deploy/production/
├── README.md                              本文件
├── SPRING_LAUNCH_EVIDENCE.md              Spring 签名外部证据接入与重放流程
├── .env.example                           无凭据 Compose 插值清单模板（永不注入容器）
├── env/                                   按服务拆分的最小运行环境模板
├── elmos-commercial.env.example           旧版全量变量清单（仅迁移参考，禁止运行时使用）
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
| `docker-compose.production.yml` + `docker-compose.spring-application.yml` | Compose 清单不再注入任何容器；Web、Control Plane、Commercial API、Workspace Service、MinIO 使用互不共享的最小 env file；Spring Worker 保持 `env_file: []`；显式 overlay 才向 BFF/Worker 精确挂载同一 engine HMAC | **从未 `up` 过**；`read_only`/`user` 标记 VERIFY-REQUIRED 的项依赖镜像实际写入路径，Spring 外部证据仍 `NOT_RUN` |
| `docker-compose.spring-runner.yml` | 独立安全域、三服务、Rootless socket 单一持有者、内部 edge/broker 网络、proxy-only 执行出网、精确 HTTPS 路由与 owner-only Secret 契约可由静态 validator 重放 | **从未 `up` 过**；真实 Rootless daemon 的 internal bridge + published-port 可达性、私有数据库 endpoint、TLS、网络策略、镜像和跨主机共享存储均 `NOT_RUN` |
| `prometheus-rules.yml` | `promtool check rules` → SUCCESS: 12 rules found | 未对接指标源；无一条告警被真实触发/恢复；阈值未用基线校准 |
| `provision_runner_host.sh` | `bash -n` 通过；`--check` 与 4 类危险路径守卫已实测（退出码 3/4 符合预期） | `--apply` 从未在真实主机执行 |
| `validate_pricing_catalog_publication.py` | 6 个用例实测通过（含伪造 PUBLISHED 被阻断、免费套餐被改成收费被拒） | 未接入 CI |
| `RESTORE_DRILL.md` | —— | **演练本身未执行**；这是关闭 RISK-DATA-001 的前提 |
| `RUNNER_PRODUCTION_BASELINE.md` | 持久队列、Runner Agent、租约/轮换、隔离和对象存储实现已通过本地测试 | **未部署到真实 Runner 集群**；真实 Podman、网络策略、多节点故障与独立隔离验证均 `NOT_RUN` |

---

## 起步顺序

```bash
# 1. 创建唯一的应用部署/门禁身份。该账号、容器和宿主 bind source 使用同一
# 精确 UID/GID 10001；不要以另一个 deploy user 创建配置后再放宽权限。
sudo groupadd --system --gid 10001 elmos-spring-app
sudo useradd --system --uid 10001 --gid 10001 --home-dir /nonexistent \
  --shell /usr/sbin/nologin elmos-spring-app
test "$(id -u elmos-spring-app)" = 10001
test "$(id -g elmos-spring-app)" = 10001
sudo install -d -o 10001 -g 10001 -m 0700 \
  /srv/elmos/config /controlled/spring /controlled/evidence \
  /controlled/drafts /controlled/trust

# Compose 插值清单只包含自身路径、七个服务 env 路径和 Secret 根路径，禁止凭据。
# 七份 service env 互不共享；逐项通过 Secret Manager/受控无回显流程填写。
sudo install -o 10001 -g 10001 -m 0600 \
  deploy/production/.env.example /srv/elmos/config/compose.env
sudo install -o 10001 -g 10001 -m 0600 \
  deploy/production/env/web-console.env.example /srv/elmos/config/web-console.env
sudo install -o 10001 -g 10001 -m 0600 \
  deploy/production/env/control-plane.env.example /srv/elmos/config/control-plane.env
sudo install -o 10001 -g 10001 -m 0600 \
  deploy/production/env/commercial-api.env.example /srv/elmos/config/commercial-api.env
sudo install -o 10001 -g 10001 -m 0600 \
  deploy/production/env/workspace-service.env.example /srv/elmos/config/workspace-service.env
sudo install -o 10001 -g 10001 -m 0600 \
  deploy/production/env/database-data-engine.env.example /srv/elmos/config/database-data-engine.env
sudo install -o 10001 -g 10001 -m 0600 \
  deploy/production/env/egress-proxy.env.example /srv/elmos/config/egress-proxy.env
sudo install -o 10001 -g 10001 -m 0600 \
  deploy/production/env/minio.env.example /srv/elmos/config/minio.env
sudo install -o 10001 -g 10001 -m 0600 \
  deploy/production/spring-launch.env.example /controlled/spring/spring.env
# `elmos-commercial.env.example` 是字段迁移清单，不得复制成 Compose/service env_file。

# 管理员登录邮件 Secret：Web 容器以 UID 10001 运行，文件必须 owner-only 且可读。
sudo install -d -o 10001 -g 10001 -m 0700 \
  /srv/elmos/secrets /srv/elmos/secrets/web \
  /srv/elmos/secrets/control-plane /srv/elmos/secrets/commercial-api
sudo install -o 10001 -g 10001 -m 0600 /dev/null \
  /srv/elmos/secrets/web/resend-api-key
# 通过 Secret Manager 或无回显的受控流程写入 Resend API Key；不要写入 shell 历史。
# 网络策略仅为 Web Console 放行 api.resend.com:443；禁止重定向与其他邮件端点。
# Control Plane 的对象存储/GitHub/identity 文件只写入
# `/srv/elmos/secrets/control-plane`；Commercial API 的支付宝文件只写入
# `/srv/elmos/secrets/commercial-api`。Compose 只把各自子目录挂给对应服务，任何
# 服务都不得挂载 `/srv/elmos/secrets` 根目录或其他服务子目录。

# 非 Spring 基线不需要也不会挂载 engine HMAC。启用 Spring 前先准备应用主机边界：
# 所有中间祖先必须由 root 或 UID 10001 持有，且不得是无 sticky bit 的 group/other
# writable 目录。workspace 必须先挂载真实的跨主机外部存储；mkdir 本地目录不能
# 冒充“共享存储已验证”的外部证据。
sudo install -d -o 10001 -g 10001 -m 0700 \
  /srv/elmos/spring-secrets/application \
  /srv/elmos/spring-replay/application/engine
# 外部共享存储挂载成功后，才校验/设置其既有 mount point：
sudo chown 10001:10001 /srv/elmos/spring-shared/runs
sudo chmod 0700 /srv/elmos/spring-shared/runs

# 由 Secret Manager 或等价无回显受控流程原子写入以下四个不同文件；不得生成、打印
# 或复制 Secret 到 shell/history。每个文件必须是 32..4096 bytes、UID:GID
# 10001:10001、0400（轮换窗口可 0600）、单 hard link；四份 effective bytes 必须互异。
# /srv/elmos/spring-secrets/application/{engine,verifier,transformer,runtime}.hmac
# 写入完成后只校验 metadata/长度，绝不输出内容。

# 受控发布流水线还必须把精确 revision 安装到：
#   /opt/elmos-spring-gate/<40-hex-revision>/
# 该目录、Git object database、/usr/bin/python3、系统 PyYAML/jsonschema/OpenSSL 3
# 及其完整祖先链都必须 root-owned 且不可由 UID 10001 或 Runner daemon owner 写入。
# 应用 gate 与 root observer 都只从这个 detached、只读、精确 revision 镜像执行。

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
/usr/bin/docker network create --internal \
  --label io.elmos.network.default-deny=true \
  --label io.elmos.network.purpose=spring-runner-control \
  elmos-spring-runner-control

# 7. 将 deploy/production/runner/spring-runner.env.example 复制到下面的仓库外路径，
# 填写精确值并设置父目录 0700、文件 0400/0600。把 runner env 当作数据解析，
# 然后由受控 root 只读 observer 做不变更主机的 preflight。禁止 source/eval；
# parser 使用 Runner 专属 allowlist，拒绝未知项、重复项、插值和命令语法，并要求
# 仓库外绝对路径、非 symlink、owner-only 文件及 0700 父目录。
# 该文件只供 preflight 与 `docker compose --env-file` 做变量替换；三个 Runner
# service 均禁止 service-level `env_file`，因此 TLS/Socket/宿主路径等不会整包注入容器。
# --check-host 验证 rootless SecurityOptions、internal 控制网络、digest 格式、
# socket、目录、Secret owner/mode/inode/value separation 和 TLS/config。root 权限
# 仅用于读取 mapped-UID/0400 Secret 及 /proc/<container-pid>/root；Docker daemon
# 仍必须是 rootless。独立参数不得从 runner.env 自行推导。observer 只能从
# root-owned immutable revision mirror 执行，且 bundle digest 必须先由 CI 计算并
# 经独立审批渠道固定；digest 同时覆盖 Runner observer、application launch gate、
# Makefile、Schema、Compose、env 合同及其读取的 Java/TypeScript 静态输入。该检查不制造 attestation。
RUNNER_UID="$(/usr/bin/id -u elmos-spring-runner)"
RUNNER_GID="$(/usr/bin/id -g elmos-spring-runner)"
REVISION="$DEPLOYED_GIT_REVISION"
/usr/bin/python3 -I /opt/elmos-spring-gate/$REVISION/deploy/production/runner/validate_spring_runner_topology.py \
  --show-observer-bundle-digest
# 将上一行 sha256 结果送独立审批系统；生产检查只接受审批系统回传值。
OBSERVER_BUNDLE_DIGEST="$APPROVED_SPRING_OBSERVER_BUNDLE_DIGEST"
sudo /usr/bin/env -i HOME=/root LANG=C LC_ALL=C PATH=/usr/bin:/bin \
  /usr/bin/python3 -I /opt/elmos-spring-gate/$REVISION/deploy/production/runner/validate_spring_runner_topology.py \
  --environment-file /srv/elmos/spring-runner/runner.env \
  --rootless-owner-uid "$RUNNER_UID" --rootless-owner-gid "$RUNNER_GID" \
  --observer-revision "$REVISION" \
  --observer-bundle-digest "$OBSERVER_BUNDLE_DIGEST" --check-host

# 8. 在该独立主机启动 Runner；绝不能与应用 compose 叠加。
sudo -u elmos-spring-runner /usr/bin/docker compose \
  --env-file /srv/elmos/spring-runner/runner.env \
  -f /opt/elmos-spring-gate/$REVISION/deploy/production/compose/docker-compose.spring-runner.yml up -d
sudo /usr/bin/env -i HOME=/root LANG=C LC_ALL=C PATH=/usr/bin:/bin \
  /usr/bin/python3 -I /opt/elmos-spring-gate/$REVISION/deploy/production/runner/validate_spring_runner_topology.py \
  --environment-file /srv/elmos/spring-runner/runner.env \
  --rootless-owner-uid "$RUNNER_UID" --rootless-owner-gid "$RUNNER_GID" \
  --observer-revision "$REVISION" \
  --observer-bundle-digest "$OBSERVER_BUNDLE_DIGEST" --check-running

# spring-runner-edge 与 spring-runner-broker 都是 internal bridge。Rootless 端口
# 转发必须仍能把批准的宿主私网地址映射到 ingress:8443；从应用主机执行 TLS 握手和
# 经 HMAC 的 canary 请求并归档收据。若所选引擎不能同时满足 internal + published
# port，保持上线 BLOCKED，不得把 edge 改成可任意出网的普通 bridge。

# 9. 应用主机（先在 staging）。compose.env 仅做变量插值，永不注入服务；
# web-console.env 和六个后端 env 各自只进入对应服务。Spring 值只放在
# /controlled/spring/spring.env。全部文件归 UID/GID 10001，父目录 0700，文件
# 0400/0600；门禁和 Compose 都以 elmos-spring-app 身份执行，不放宽权限。
GATE_ROOT="/opt/elmos-spring-gate/$DEPLOYED_GIT_REVISION"
sudo -u elmos-spring-app /usr/bin/env -i HOME=/nonexistent LANG=C LC_ALL=C PATH=/usr/bin:/bin \
  /usr/bin/python3 -I "$GATE_ROOT/scripts/batch30/validate_spring_launch_readiness.py"
sudo -u elmos-spring-app /usr/bin/env -i HOME=/nonexistent LANG=C LC_ALL=C PATH=/usr/bin:/bin \
  /usr/bin/python3 -I "$GATE_ROOT/scripts/batch30/validate_spring_launch_readiness.py" \
  --environment-file /controlled/spring/spring.env \
  --compose-environment-file /srv/elmos/config/compose.env \
  --web-environment-file /srv/elmos/config/web-console.env
sudo -u elmos-spring-app /usr/bin/docker compose \
  --env-file /srv/elmos/config/compose.env \
  -f "$GATE_ROOT/deploy/production/compose/docker-compose.production.yml" up -d
sudo -u elmos-spring-app /usr/bin/docker compose \
  --env-file /srv/elmos/config/compose.env \
  --env-file /controlled/spring/spring.env \
  -f "$GATE_ROOT/deploy/production/compose/docker-compose.production.yml" \
  -f "$GATE_ROOT/deploy/production/compose/docker-compose.spring-application.yml" \
  --profile spring up -d                           # 只在售卖 Spring 升级时

# web-console 的 raw inspect 含 env_file 明文，禁止落盘；collector 在 Linux Docker
# 宿主内存中同时校验 web/worker，并通过 /proc/<pid>/root 比较每个 bind 的源/目标
# inode；collector 必须由具备受控只读 /proc 权限的 host observer 执行。仅输出
# 脱敏、content-addressed attestation，不携带 raw web inspect 摘要
# （避免弱密钥离线猜测 oracle），不签名、不生成外部通过状态。生产入口是 bundle
# 内的固定 launcher；它不接受 Make flag/第二个 -f，并只会 exec root-owned
# /usr/bin/make -f Makefile.batch30 的两个 allowlisted target。
sudo -u elmos-spring-app /usr/bin/env -i \
  HOME=/nonexistent LANG=C LC_ALL=C PATH=/usr/bin:/bin \
  SPRING_EXPECTED_REVISION="$DEPLOYED_GIT_REVISION" \
  SPRING_OBSERVER_BUNDLE_DIGEST="$APPROVED_SPRING_OBSERVER_BUNDLE_DIGEST" \
  SPRING_WEB_CONTAINER=elmos-staging-web-console-1 \
  SPRING_WEB_IMAGE_DIGEST="$PINNED_WEB_IMAGE_ID" \
  SPRING_WORKER_CONTAINER=elmos-staging-java-engine-worker-1 \
  SPRING_WORKER_IMAGE_DIGEST="$PINNED_WORKER_IMAGE_ID" \
  SPRING_WEB_COLLECTOR_ID=staging-runtime-collector \
  SPRING_WEB_RUNTIME_ATTESTATION_OUTPUT=/controlled/evidence/web-console.runtime-attestation.json \
  /usr/bin/python3 -I "$GATE_ROOT/scripts/batch30/run_spring_production_gate.py" \
  spring-web-runtime-attestation

# 10. 正式放量必须再提供签名外部证据、独立信任库和证据字节根；
# 模板中的 NOT_RUN、URL/摘要自报、单方签名或仓库内收据都不能通过。
# APPROVED_SPRING_TRUST_STORE_DIGEST 必须来自独立审批/配置系统，禁止在同一
# 命令里从待验证 trust store 临时计算后自我固定。受控交接副本必须归 UID 10001，
# 但审批 digest 与私钥仍来自独立系统。生产门禁固定使用 /usr/bin/python3 -I
# 执行 bundle 内 launcher，不解析 PATH 中的 uv，也不接受任意 Make 参数；make、
# Python、系统依赖及其祖先必须 root-owned 且 UID 10001 不可写。
sudo -u elmos-spring-app /usr/bin/env -i \
  HOME=/nonexistent LANG=C LC_ALL=C PATH=/usr/bin:/bin \
  SPRING_ENV_FILE=/controlled/spring/spring.env \
  ELMOS_ENV_FILE=/srv/elmos/config/compose.env \
  ELMOS_WEB_ENV_FILE=/srv/elmos/config/web-console.env \
  SPRING_EXTERNAL_EVIDENCE=/controlled/evidence/spring-launch-receipt.json \
  SPRING_TRUST_STORE=/controlled/trust/spring-trust-store.json \
  SPRING_TRUST_STORE_DIGEST="$APPROVED_SPRING_TRUST_STORE_DIGEST" \
  SPRING_EVIDENCE_ROOT=/controlled/evidence \
  SPRING_EXPECTED_REVISION="$DEPLOYED_GIT_REVISION" \
  SPRING_OBSERVER_BUNDLE_DIGEST="$APPROVED_SPRING_OBSERVER_BUNDLE_DIGEST" \
  SPRING_ENVIRONMENT_ID=spring-staging-cn-1 \
  SPRING_DEPLOYMENT_ID="$SPRING_DEPLOYMENT_ID" \
  SPRING_PROVIDER=private-linux \
  SPRING_REGION=cn-north-1 \
  SPRING_ENVIRONMENT_CLASS=STAGING \
  SPRING_WORKER_APPLICATION_ARTIFACT_DIGEST="$SPRING_WORKER_APPLICATION_ARTIFACT_DIGEST" \
  /usr/bin/python3 -I "$GATE_ROOT/scripts/batch30/run_spring_production_gate.py" \
  spring-launch-gate

# 11. 告警
promtool check rules deploy/production/observability/prometheus-rules.yml

# 12. 恢复演练（上线前必做一次）
# 按 deploy/production/backup/RESTORE_DRILL.md 执行，产出 drills/drill-<时间戳>.md

# 13. 定价目录门禁（CI 常驻 + 开售前）
python3 scripts/commercial/validate_pricing_catalog_publication.py
python3 scripts/commercial/validate_pricing_catalog_publication.py --check-publishable
```

`SPRING_ENV_FILE` 是精确 20-key Spring-only gate 与 application overlay 插值输入；
`ELMOS_ENV_FILE` 是无凭据 Compose 清单，只允许自身绝对路径、七个 service env
绝对路径和 `ELMOS_SECRET_ROOT`。它从不成为 service `env_file`。Web/BFF 的实际
运行环境由 `ELMOS_WEB_ENV_FILE` 单独提供；数据库、支付与后端 OIDC 凭据留在各自
后端文件，门禁会拒绝出现在 Web 文件或 Compose 清单。门禁以无 shell、无插值的
数据解析器稳定读取三者。Web env 的 portable commitment 仅绑定
exact key、presence/empty 以及严格 allowlist 的非秘密值，绝不把 DB/OIDC/session/
provider/API secret value 或原始文件摘要写入 stdout/收据形成离线猜测 oracle。
三份门禁输入与调用进程均不得设置
`SPRING_APPLICATION_JSON`、`JAVA_TOOL_OPTIONS`、`_JAVA_OPTIONS`、
`JDK_JAVA_OPTIONS`、servlet/context path 或 Spring config/profile 覆盖；不要
`source`/`eval` 任一文件。生产 overlay 同时在 Worker 容器边界清空 JVM/JSON/path
覆盖且不向 Worker 注入宽泛应用 env_file。

application-host mount commitment 对 secret file 绑定 path digest、dev/inode/type/
size/mode/UID/GID/nlink/ctime；对会正常增长的 workspace/replay directory 绑定稳定
dev/inode/type/mode/UID/GID，并对完整父目录链绑定 dev/inode/type/mode/UID/GID；secret
的立即父目录必须为 10001:10001/0700，所有祖先必须由 root/10001 持有且不得是不带
sticky bit 的 group/other writable 目录。workspace 与各 replay 目录的 dev/inode
必须两两不同，且任何一个都不得等于任一 Secret 父目录；不同路径名或 bind-mount
别名不能绕过此检查。签名 `deployment_id` 充当可写目录生命周期 epoch。collector
在所有 canary 操作后最后执行，过程中任一容器 restart 或同路径 source replacement
都会 fail closed；正常目录子项写入不会仅因 ctime/size 变化使 72 小时收据失效。

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

应用主机的唯一部署/门禁账号 `elmos-spring-app`、Web BFF 和 Java Engine Worker
都使用 UID/GID `10001:10001`。Compose 清单、七个 service env、Spring env、受控
证据/信任库交接副本和 Secret 都只允许该账号读取；父目录为 `0700`，文件为
`0400/0600`。因此门禁无需 root，也不需要 group/other 权限。门禁代码和解释器来自
root-owned immutable revision mirror，账号 10001 不得修改它们。该主机上的 Secret
父目录为 `0700`、owner `10001:10001`，四个
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

Runner host/running validator 由受控 root observer 读取这些 mapped-UID/`0400`
文件并比较三者的 canonical byte digest（摘要不出站），同时只读访问容器 `/proc`
mount namespace。该 observer 不是 Docker daemon；daemon 必须继续以独立非 root
身份运行并通过 `name=rootless` 检查。以 daemon owner 直接执行会因正确的文件和
ptrace 权限而失败，因此不得通过放宽 Secret mode 或容器 UID 绕过。

威胁模型边界：rootless Docker daemon 及其 owner 是本地拓扑观测的 Runner TCB，
不是独立验证者。root observer 会绑定 socket/daemon identity 并拒绝普通替换、漂移
和跨检查变化，但无法从同一个 Docker API 自证 daemon owner 没有失陷或进行
`A -> B -> A` 响应欺骗。若 owner/daemon 有失陷嫌疑，或缺少其权限域之外的签名
runtime attestation，本地检查结果必须作废并保持上线 `BLOCKED`；不得用它满足独立
外部证据或认证门禁。

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
