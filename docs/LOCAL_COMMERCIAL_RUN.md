# 本地商业管理核心一键运行

这条入口用于在一台开发机上真实启动 ELMOS 的最小商业管理闭环：PostgreSQL、
Control Plane、Commercial API、Workspace Service 与 Web Console。它会生成 8 小时有效、
绑定 `local-commercial` 租户和 `local-commercial-admin` 操作者的服务与会话短期凭据，等待依赖就绪，
然后实际请求各服务 readiness，并验证共享 Bearer 值无法访问管理 API。

前置条件：本机 Docker 必须使用 Unix socket 的本地 context，并安装 Java 21、Maven 3.9
与摘要校验通过的 pnpm 10.12.4。
脚本会在宿主机一次性构建三个 Java 可执行 JAR，再用固定 digest 的 JRE 生成最小非 root
运行镜像；正式生产 Dockerfile 与生产 Compose 不受这一开发机加速路径影响。远程 TCP/SSH
Docker context 会 fail closed，避免“本地”启动或数据重置误作用到远端主机。
容器启动后、冒烟前，脚本会幂等初始化固定的 `local-commercial` 本地租户根记录，
因此新卷与保留卷都适用。该部署 bootstrap 不创建账户、成员身份、会话、令牌或额外权限；
运营端点仍须通过原有短租约凭据和租户绑定授权。若保留卷中同 ID 记录与固定本地契约冲突，
启动会 fail closed，不会覆盖原数据。

```bash
make local-commercial-up
```

命令成功后会打印：

- 管理员专用入口 `http://127.0.0.1:3000/admin/login`（本地栈未配置 OIDC，失败关闭）；
- 服务短期凭据到期时间；
- 冒烟证据路径 `.elmos/local-commercial/smoke-result.json`。

日常操作：

```bash
make local-commercial-status
make local-commercial-smoke
make local-commercial-down
```

需要独立复验租户初始化时，下列命令会对当前本地卷重复执行两次幂等 bootstrap，
再在 PostgreSQL 事务内制造一次契约冲突；冲突必须失败且自动回滚，不保留 fixture：

```bash
python3 scripts/operations/local_commercial.py bootstrap-self-test
```

`down` 只停止并移除本项目容器，默认保留数据库卷。所有宿主机端口只绑定
`127.0.0.1`。Workspace 容器执行、Secret 注入、自动修复、付费扣款、邮件通知、托管 Runner
和真实仓库均默认关闭。所有管理读取与写入都要求已验证的指定管理员 OIDC 会话；
本地生成的负向 Bearer fixture 只用于证明旧共享令牌路径返回 401，不能读取运营总览、
作业、Runner Fleet、财务或用户数据。

数据库密码不属于 8 小时短租约；它会随保留的数据卷稳定存在。密码与数据卷是一对不可分割的
本地恢复材料。不要只删除
`.elmos/local-commercial/runtime.env` 后继续复用旧卷；脚本会对此 fail closed。若密码文件无法从备份恢复，
且确认本地数据可以永久删除，使用下面的显式重置命令，再重新执行 `make local-commercial-up`：

```bash
python3 scripts/operations/local_commercial.py reset-data --confirm-local-data-loss
```

每次 `up` 或 `smoke` 都会先把旧证据失效为 `RUNNING`；失败会记录 `LOCAL_FAIL`，因此
`status` 不会把历史 `LOCAL_PASS` 当成本次结果。可处理的 Ctrl-C 中断和未分类 Python
异常也会 fail closed 为 `LOCAL_FAIL`；进程被 `SIGKILL`、主机断电或文件系统无法写入时，
仍可能留下 `RUNNING`，该状态永远不得视为通过。

## 证据边界

本入口的 `LOCAL_PASS` 只证明当前提交在当前 Docker 环境中能够构建、启动、响应核心健康检查，
并证明共享管理 Bearer fixture 被管理 API 拒绝。冒烟仅将检查名、HTTP 状态、
耗时和已验证的契约断言写入 `smoke-result.json`；不持久化响应体、令牌、Secret、
作业内容或修复预览，上游错误体也不会回显。以下门禁不会被本地冒烟提升：

- 真实企业 OIDC 与选中租户 delegation；
- 支付商户、经营主体、税务和对账；
- 真实 Private Runner 隔离、attestation 与多节点故障；
- 生产 TLS、备份恢复、告警投递、容量压测与客户验收。

这些状态在生成的证据中保持 `NOT_RUN`，不能据此宣称生产认证或已经开售。
