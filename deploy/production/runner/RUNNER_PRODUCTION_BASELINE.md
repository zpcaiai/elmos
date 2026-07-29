# ELMOS 多租户托管执行面基线

更新日期：2026-07-29
实现状态：**本地工程闭环完成；staging/生产执行证据 `NOT_RUN`**

## 已实现架构

```text
Web Console
  -> OIDC Bearer + 数据库组织成员关系复核
Control Plane
  -> PostgreSQL 持久队列 / 公平调度 / 配额 / 租约 / 取消 / 超时回收
Runner Agent
  -> rootless 容器 / 只读源码 / 默认拒绝网络 / 摘要固定镜像
Object Storage
  -> 预签名上传 / 服务端回读复算 SHA-256 / 保留期物理删除
```

生产 Web 必须设置：

```text
ELMOS_HOSTED_EXECUTION_ENABLED=true
ELMOS_LOCAL_RUNNER_ENABLED=false
```

`apps/web-console` 只提交、读取和取消作业，不再直接启动客户进程。控制面不把
租户会话或供应商凭据转交给 Runner；Runner 只得到一个有界作业租约。

## Runner 身份生命周期

1. 组织管理员用 `admin:operate` 权限为一个确切 Runner Pool 申请一次性
   enrollment token。
2. 每个 Runner 节点必须获得**自己的一枚** token；禁止多个副本共享。
3. Agent 在本地生成 node token，只把 SHA-256 发给控制面。
4. enrollment token 被该节点声明后不可用于其他节点。
5. node token 有效期 24 小时，Agent 在到期前用客户端生成的新 token 和
   `rotationRequestId` 做幂等轮换；旧 token 只保留 5 分钟重试窗口。
6. Operator/独立验证器确认隔离声明前，节点保持 `REGISTERED`，不能领作业。
7. 吊销、Drain、心跳丢失和租约过期均失败关闭。

仓库中的 Kubernetes 文件是**每节点模板**，不是可直接复用同一 Secret 的伸缩
清单。扩容控制器必须先为每个待建节点调用 enrollment API，再创建独立 Secret；
这个外部控制器和真实集群执行当前均为 `NOT_RUN`。

## 作业隔离的不变条件

Agent 启动作业时强制：

```text
--rm
--network=none
--read-only
--cap-drop=ALL
--security-opt=no-new-privileges
--userns=keep-id
--user <非 root uid>:<gid>
--pids-limit=<有界值>
--memory=<作业预算>
--cpus=<作业预算>
--tmpfs /tmp:rw,noexec,nosuid,size=<有界值>
--mount type=bind,src=<workspace>,dst=/workspace,rw
镜像必须是 name@sha256:<64 hex>
```

源码在工作区中只读落地，任何未经声明的网络、Secret、宿主路径、特权、可变镜像
或 host execution 都会在生产配置校验或 attestation 中被拒绝。仓库内容不能修改
这些策略。

## 队列与故障语义

- 队列状态、派发状态和租约状态分别持久化。
- 领取使用 PostgreSQL `FOR UPDATE SKIP LOCKED`，组织计数器和套餐并发上限在
  同一事务内校验。
- 公平调度按组织轮转；一个租户不能占满所有 Runner。
- 心跳续租；用户取消通过下一次心跳传给 Agent，先终止再强制杀死。
- 控制面 advisory lock 保证多副本 lease reaper 不重复回收。
- 租约丢失、节点凭据不匹配、过期和未知供应商结果均不是成功。
- 完成回报幂等；可重试失败按有界退避重新排队，达到上限后终止。

## 产物

- Runner 只用短期预签名 URL 上传。
- 对象键以组织 ID 为前缀，内容对象在数据库中也是租户作用域，不做跨租户去重。
- 上传后控制面从对象存储重新读取全部字节，复算大小和 SHA-256；客户端声明不算
  验证证据。
- 下载 URL 最长 15 分钟，并记录组织、Actor、产物和有效期。
- 到期元数据先变为不可下载的 `PURGE_PENDING`，对象存储确认 `DELETE` 2xx/404
  后才进入 `PURGED`；超时和未知结果保留待重试。
- Legal Hold 覆盖普通保留策略。

## 操作步骤

1. 对 PostgreSQL 执行至 V61。
2. 用 `scripts/operations/configure_control_plane_runtime_role.sh` 给
   `LOGIN NOSUPERUSER NOBYPASSRLS` 运行角色授予精确权限。
3. 用 `deploy/production/postgres/configure_hosted_runtime.sql` 写入经人工验证的
   endpoint、bucket、SSE/CMK 和 Secret Reference；脚本不接收存储凭据值。
4. 通过管理 API 为每个节点分别签发一次性 enrollment token。
5. 将 token 放入 owner-only/投射 Secret，渲染
   `apps/runner-agent/deploy/runner-agent.yaml` 中的确切镜像摘要、节点 ID、Pool 和
   网络策略。
6. 独立验证隔离声明后再把节点转为 `READY`。
7. 执行真实作业、取消、节点丢失、对象删除和恢复演练，保存原始证据。

## 当前证据边界

本地已有 Java 自测、真实 PostgreSQL Testcontainers 迁移/行为测试、前端类型检查
和 HTTP 假对象存储测试。它们不能证明：

- Kubernetes/Podman 在目标内核上的真实隔离；
- 真实 OIDC、GitHub App、S3/OSS/MinIO、DNS、证书和网络策略；
- 多节点压力、公平性、故障恢复、成本和 SLO；
- 客户仓库兼容性、独立安全评审或生产认证。

以上在实际授权执行前一律保持 `NOT_RUN`。
