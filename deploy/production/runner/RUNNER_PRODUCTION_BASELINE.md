# ELMOS 托管执行面基线

生成日期：2026-07-28
状态：**架构决策待定 + 主机基线已给出**。本文不产生隔离证据；
`mature-product-packs/batch45/.../residual-risks.json` 的相关风险保持 `OPEN`。

---

## 1. 今天的执行面长什么样（事实）

生成、构建、启动探针这些动作最终都由 **rootless 容器**执行，而调用方是 **Web Console 的
BFF 进程**（`ELMOS_LOCAL_RUNNER_*` 全部在 `apps/web-console` 的服务端读取）。

配置形态：

```
ELMOS_LOCAL_RUNNER_ENABLED=true
ELMOS_LOCAL_RUNNER_EXECUTOR=ROOTLESS_CONTAINER   # 生产唯一允许值
ELMOS_LOCAL_RUNNER_ROOT=<专用绝对目录>
ELMOS_LOCAL_RUNNER_CONTAINER_ENGINE=<podman 绝对路径>
ELMOS_LOCAL_RUNNER_AUTH_TOKEN(_FILE)             # ≥24 字符，或 0600 文件
ELMOS_LOCAL_RUNNER_AUTH_TOKEN_EXPIRES_AT         # 带时区，≤24 小时
ELMOS_LOCAL_RUNNER_TENANT_ID / _ACTOR_ID         # 令牌唯一绑定的租户与 Actor
```

**这套设计有三个直接后果，必须先认清再动手：**

1. **单租户**。令牌绑定"一个租户 + 一个 Actor"。多客户共用一套部署时，
   要么所有客户共享同一个 Actor 身份（不可接受），要么每客户一套部署（成本不可接受）。
2. **同机执行**。BFF 直接调本机 podman，意味着客户代码派生的构建过程与产品进程在同一台机器上。
   仓库自身的约束是"客户代码不得在控制平面进程内执行"——同机不同进程勉强满足字面要求，
   但不满足商业化应有的隔离等级。
3. **令牌是长期环境变量**。有效期 ≤24 小时意味着**有人得每天去续**，否则执行面自己停摆。

---

## 2. 两条路，必须选一条

### 路线 A：Runner Agent（推荐）

新增一个独立的 Runner 服务，部署在与应用主机隔离的机器上：

```
web-console/control-plane  --(mTLS + 短期作业令牌)-->  runner-agent  --> rootless podman
```

- 作业令牌由服务端按**单次作业**签发，租户/Actor 从认证身份派生，不再是环境变量
- Runner 主机不装应用、不连业务数据库、只回传产物摘要
- 可水平扩容，可按套餐 `concurrentJobs`（1/3/5）做队列与配额

工作量估计：**6–9 人周**（agent 协议 + 令牌签发 + 队列配额 + 产物回传 + 隔离断言）。

### 路线 B：podman remote socket

保持 BFF 直接调用，但通过 SSH 指向远程 podman：

- 改动小（1–2 人周），能拿到机器隔离
- **但不解决单租户令牌问题**，也没有队列与配额
- 只适合"单客户专属部署"这种交付形态

工作量估计：**1–2 人周**，但只是权宜之计。

> 若 `DECISIONS.md` 的 D-03 选了"客户自部署 + 许可证"，路线 B 够用；
> 选"SaaS 多租户托管"则必须走路线 A。

---

## 3. 主机基线（两条路线都要做）

用 `scripts/operations/provision_runner_host.sh` 落地并校验：

```bash
# 只读检查，任何一项不满足以退出码 3 结束
ELMOS_RUNNER_USER=elmos-runner \
ELMOS_RUNNER_ROOT=/srv/elmos/runner \
  scripts/operations/provision_runner_host.sh --check

# 创建用户、subuid/subgid、0700 目录、开启 linger
sudo -E scripts/operations/provision_runner_host.sh --apply
```

脚本校验六项：容器引擎存在且 rootless、专用用户存在、`/etc/subuid` 与 `/etc/subgid`
已分配区间、Runner 根目录存在且权限为 700/750、user namespace 未被禁用、cgroup 可读。

**内置的危险路径守卫**（已实测，均以退出码 4 拒绝）：

| 输入 | 结果 |
|---|---|
| `ELMOS_RUNNER_ROOT=/` 或 `/usr`、`/etc`、`/var`、`/home`、`/srv` … | REFUSED |
| Runner 根是一个 Git 仓库根（存在 `.git`） | REFUSED |
| Runner 根是 `ELMOS_REPOSITORY_ROOT` 的祖先目录 | REFUSED |
| 相对路径 | REFUSED |
| `--apply` 非 root 执行 | REFUSED |

---

## 4. 作业容器硬化参数（每次作业都必须带全）

```
--rm
--network=none                     # 默认拒绝出网
--read-only                        # 只读根文件系统
--cap-drop=ALL
--security-opt=no-new-privileges
--user <非 root uid>:<gid>
--pids-limit=512
--memory=<上限>  --cpus=<上限>
--tmpfs /tmp:rw,noexec,nosuid,size=<上限>
--mount type=bind,src=<源码>,dst=/src,ro=true
镜像必须写成 name@sha256:<64 hex>
```

**任一参数缺失即视为隔离未成立。** 这不是"最佳实践清单"，是执行前置条件：
缺任何一项都不得执行客户派生的构建。

需要出网的作业（拉依赖）不能简单去掉 `--network=none`，正确做法是接
`egress-proxy` 走白名单，并把允许的域记录进作业证据。

---

## 5. 产物生命周期

定价目录已经声明了保留期：免费体验 7 天、月付 30 天、年付 90 天。
执行面必须自己实现清理，否则存储成本会无声增长，且过期产物变成数据留存风险。

需要的东西：产物落对象存储 → 按 `organizationId + jobId` 命名 → 打上套餐保留期标签 →
定时任务按标签删除 → 删除动作写审计。

---

## 6. 这份基线不能替代什么

- 它**不是**隔离证据。真实证据必须是"按第 4 节参数启动的作业容器 + 可复算的执行记录"。
- 它**不覆盖**多租户配额、队列公平性、抢占与超时治理——那些属于路线 A 的工作。
- 它**不构成**安全评审。RISK-SECURITY-001 仍需外部独立执行。
