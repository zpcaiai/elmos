# Rootless Docker Workspace 主机

Workspace Service 只能连接到 `docker info --format '{{json .SecurityOptions}}'` 明确包含 `name=rootless` 的 daemon。客户 Workspace 永远不能获得 Docker socket；socket 只属于独立部署的 Workspace Service 安全域。

## 上线前 Gate

1. 安装并启动官方 rootless Docker，确认 cgroup v2、CPU、内存、PID 限制可用。
2. 分别构建 Java Transformer、Verifier、Runtime、通用 Workspace sandbox 和
   `apps/egress-proxy/Dockerfile`，记录不可变 `sha256:` digest。
3. 为每个镜像生成并归档 Smoke Test、SBOM、漏洞扫描、Provenance 和 Secret Scan；在 `sandbox_profiles` 中批准后才能被选择。
4. Java 21 sandbox digest 同时可作为 Snapshot materializer helper；它只连接 `network=none`，并把 Snapshot 解包到专用卷。
5. 创建内容寻址 Snapshot 根、命令 Artifact 根和 owner-only provider-secret 根。Provider 文件命名为 `<workspaceId>.<SECRET_TYPE>.secret`，权限 `0600`，撤销时会被消费和删除。
6. 建立状态为 `APPROVED` 且 `default_action=DENY` 的网络策略。无允许域名时客户容器没有网络；有允许域名时只能经 egress proxy 访问精确 DNS host 的 HTTPS 443。

必需环境变量：

```text
ELMOS_ROOTLESS_DOCKER_SOCKET=/run/user/<uid>/docker.sock
ELMOS_ROOTLESS_UID=<uid>
ELMOS_ROOTLESS_GID=<gid>
ELMOS_GITHUB_APP_ENABLED=true
ELMOS_GITHUB_APP_ID=<app id>
ELMOS_GITHUB_APP_PRIVATE_KEY_HOST_PATH=/run/elmos/github-app-private-key.pem
ELMOS_SNAPSHOT_ARTIFACT_HOST_PATH=/srv/elmos/artifacts
ELMOS_COMMAND_ARTIFACT_HOST_PATH=/srv/elmos/commands
ELMOS_PROVIDER_SECRET_HOST_PATH=/run/elmos/provider-secrets
ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH=/srv/elmos/java-upgrade-runs
ELMOS_VERIFIER_HMAC_SECRET_HOST_PATH=/run/elmos/java-verifier-hmac
ELMOS_TRANSFORMER_HMAC_SECRET_HOST_PATH=/run/elmos/java-transformer-hmac
ELMOS_VERIFIER_EVIDENCE_HOST_PATH=/srv/elmos/java-verifier-evidence
ELMOS_SPRING_RUNTIME_HMAC_SECRET_HOST_PATH=/run/elmos/java-runtime-hmac
ELMOS_SNAPSHOT_HELPER_IMAGE_DIGEST=sha256:<64 hex>
ELMOS_EGRESS_PROXY_IMAGE_DIGEST=sha256:<64 hex>
ELMOS_JAVA_RUNTIME_IMAGE_DIGEST=sha256:<64 hex>
ELMOS_SPRING_VERIFIER_IMAGE_DIGEST=sha256:<64 hex>
ELMOS_SPRING_TRANSFORMER_IMAGE_DIGEST=sha256:<64 hex>
ELMOS_NETWORK_POLICY_VERSION=<approved integer>
ELMOS_SPRING_UPGRADE_ROOTLESS_ATTESTED=true
ELMOS_SPRING_UPGRADE_NETWORK_POLICY_ATTESTED=true
ELMOS_SPRING_UPGRADE_VERIFIER_ID=<independently identified verifier>
ELMOS_ALLOWED_GIT_HOSTS=github.com
```

三个长期 HMAC 文件必须分别由部署系统生成至少 32 字节的随机值，放在 owner-only
`0700` 父目录中。由于 Rootless user namespace 内的 Worker UID 与 Workspace Service
UID 不同，共享的只读文件应为 `0444`，并由父目录阻止其他宿主用户遍历；部署 Gate
必须验证该父目录的 owner、ACL 和 mount target。不得提交到 Git 或写入环境变量。验证器只读
挂载候选 Artifact，验证 Evidence 使用独立持久卷，镜像中不包含 OpenRewrite
转换模块。Workspace Service 为每个验证请求创建短生命周期验证器容器，只挂载该
Run 的候选文件、Evidence 子目录和一次性 HMAC；长期 Worker-to-broker HMAC 不会
进入客户构建容器。OpenRewrite、源码编译和测试也不在长期 Worker 中运行：
Workspace Service 以 profile `spring-transformer-java17-java21-maven` 校验不可变
Transformer image digest，为每个 Run 创建专用 Rootless 容器和空白 tmpfs Maven
repository。镜像构建 Gate 会先用精确的 Java 17/21、Maven 3.9.11、OpenRewrite
6.44.0 和 rewrite-spring 6.35.0 完整执行一次参考转换，把所需依赖固化成只读种子；
子容器启动时把该种子复制到每个 Run 独立的 tmpfs，并强制 Maven `--offline`。
Transformer 与 Worker 使用相同的非 root UID `10001`。权威 Run 根下的
`evidence/run-state.json`、提升后的 FCM 和独立验证收据只由 Worker 持有；子容器唯一
可写 bind 是该 Run 的 `execution/` 子树，不能看到或修改权威 Evidence。Transformer
返回后，Worker 会重新约束输出真实路径、复算 ZIP 摘要、校验精确 FCM 元组，再把 FCM
提升到权威 Evidence，并记录内容摘要。子容器注入仅对该子容器有效的一次性 HMAC；
取消、完成或失败后强制删除容器。Worker、Transformer 和验证器
都只连接 `internal: true` 网络；公开 Git HTTPS 只可经过精确主机名 allowlist 的
`java-upgrade-egress-proxy`，Maven 在任务执行阶段没有网络访问。Proxy 审计日志应进入
不可变日志存储。

`apps/java-runtime-runner/Dockerfile` 必须单独构建、扫描、记录不可变 digest，并以
profile `spring-runtime-java21` 写入批准镜像注册表。一键启动不会在 Engine Worker
进程中执行客户 JAR；Workspace Service 会再次确认 daemon 的 `rootless` 安全选项，
按 Run 创建 `network=none`、只读根、全部能力移除、非 root、限 CPU/内存/PID 的
专属容器，在容器内部执行回环健康检查；停止会删除该容器。Worker 永远不挂载 Docker
socket。

两个 attestation 变量只能在部署 Gate 已确认当前 daemon 为
rootless、Java Engine Worker 运行在只读根文件系统、能力全部移除、迁移 Workspace
按 Run 隔离且 Maven cache 为每次任务的独立 tmpfs，而且客户代码默认无网络、Git
只能经过精确域名 allowlist 的可审计 egress proxy、Maven 强制离线后设置。默认 Compose
始终关闭真实转换；不能把
宿主机进程或普通 Docker Desktop 标记成隔离 Runner。

GitHub App private key文件也必须为 owner-only PKCS#8 PEM；控制平面只用它签发最长一小时、仓库绑定且最小权限的 installation token，不把 token 写入数据库、日志或 Snapshot。

使用默认 Compose 和 rootless override 启动：

```bash
docker compose -f deploy/compose/docker-compose.yml \
  -f deploy/rootless-docker/docker-compose.rootless.yml up --build
```

服务启动时会再次验证 rootless、批准镜像 digest、Snapshot/Artifact 根和网络策略；任一缺失都会 fail closed。终止验收应证明 Secret 已撤销、proxy 审计已落库、容器/卷/网络均已删除且重复清理安全。
