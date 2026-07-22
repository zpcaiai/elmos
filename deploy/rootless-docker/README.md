# Rootless Docker Workspace 主机

Workspace Service 只能连接到 `docker info --format '{{json .SecurityOptions}}'` 明确包含 `name=rootless` 的 daemon。客户 Workspace 永远不能获得 Docker socket；socket 只属于独立部署的 Workspace Service 安全域。

## 上线前 Gate

1. 安装并启动官方 rootless Docker，确认 cgroup v2、CPU、内存、PID 限制可用。
2. 构建四个 Java sandbox image 和 `apps/egress-proxy/Dockerfile`，记录不可变 `sha256:` digest。
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
ELMOS_SNAPSHOT_HELPER_IMAGE_DIGEST=sha256:<64 hex>
ELMOS_EGRESS_PROXY_IMAGE_DIGEST=sha256:<64 hex>
```

GitHub App private key文件也必须为 owner-only PKCS#8 PEM；控制平面只用它签发最长一小时、仓库绑定且最小权限的 installation token，不把 token 写入数据库、日志或 Snapshot。

使用默认 Compose 和 rootless override 启动：

```bash
docker compose -f deploy/compose/docker-compose.yml \
  -f deploy/rootless-docker/docker-compose.rootless.yml up --build
```

服务启动时会再次验证 rootless、批准镜像 digest、Snapshot/Artifact 根和网络策略；任一缺失都会 fail closed。终止验收应证明 Secret 已撤销、proxy 审计已落库、容器/卷/网络均已删除且重复清理安全。
