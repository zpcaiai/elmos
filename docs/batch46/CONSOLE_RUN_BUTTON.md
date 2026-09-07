# Batch 46 — Console 一键运行按钮

生成或转换完成后，接收方在 ELMOS Web Console 上点一个按钮就能把产物跑起来，
免费额度 10 分钟，到期自动回收。按钮不实现任何策略，它只是启动冒烟包自带的
运行器并如实显示它写下的证据 —— 这样 Console 与 CLI 不可能各说各话。

## 组成

| 位置 | 作用 |
| --- | --- |
| `app/lib/smokeContracts.ts` | 前后端共用的会话、能力、证据类型 |
| `app/lib/server/smokeLeaseRunner.ts` | 会话生命周期：能力探测、启动、轮询、续期、停止、证据 |
| `app/api/smoke/*` | REST 入口，沿用 `withBusinessAudit` 与 `BLOCKED/reason` 约定 |
| `app/components/SmokeRunButton.tsx` | 可复用按钮面板：倒计时、断言、续期、回收报告、证据 |
| `app/smoke/page.tsx` | 独立页面，手工指定 projectRef 载入冒烟包 |
| `app/translation/TranslationStudio.tsx` | 转换任务产物就绪后内联渲染同一个按钮 |

## 环境变量

| 变量 | 必需 | 说明 |
| --- | --- | --- |
| `ELMOS_SMOKE_PROJECTS_ROOT` | 本机执行必需 | 生成项目的根目录；`projectRef` 相对它解析并做路径封闭校验 |
| `ELMOS_RUNTIME_STATE_DIR` | 本机执行必需 | 会话记录 `smoke-sessions/<id>.json` 的存放位置 |
| `ELMOS_LOCAL_RUNNER_ENABLED` | 本机执行必需 | 与既有本机 Runner 共用开关 |
| `ELMOS_SMOKE_PYTHON` | 可选 | 默认 `python3` |
| `ELMOS_SMOKE_HOSTED_ENDPOINT` | 沙箱执行必需 | 托管 Runner 端点，必须是 https 或回环地址 |
| `ELMOS_SMOKE_HOSTED_TOKEN` | 沙箱执行必需 | 托管 Runner 凭据 |
| `ELMOS_SMOKE_MAX_ACTIVE_SESSIONS` | 可选 | 每租户并发上限，默认 3 |
| `ELMOS_SMOKE_SKIP_INSTALL` | 可选 | 置 `true` 时按钮启动的运行跳过依赖安装；仅用于工具链已预置的 CI 或沙箱镜像，其他环境安装步骤本身就是「从干净检出能起来」的一部分 |

未配置的执行位置会以 `NOT_CONFIGURED` / `BLOCKED` 加理由返回，界面照实显示，
**不会**退化成一个看起来能点、点了报错的按钮。

## 执行位置选择

能力接口按可用性择优：优先 `HOSTED_RUNNER`（接收方本机不需要任何工具链），
其次 `LOCAL_WORKSTATION`（更接近他们真正的运行方式）。两条路径共用同一套租约、
断言与证据模型；差别只在谁来跑。

## 托管 Runner 需要实现的接口

`ELMOS_SMOKE_HOSTED_ENDPOINT` 指向的服务需提供：

```
POST /smoke-runs                      → { runId }
GET  /smoke-runs/{runId}              → { state, url, remainingSeconds, ttlSeconds,
                                          billableSeconds, expiresAtEpoch, checks[],
                                          notes[], lease, gateStatus, gateFailures[],
                                          gateLimitations[], evidenceAvailable }
POST /smoke-runs/{runId}/extend       → { seconds, reason, actor }
POST /smoke-runs/{runId}/stop         → { reason }
GET  /smoke-runs/{runId}/evidence     → { result, gate, lease, logs[] }
```

字段语义与 `smoke/runtime/status.json`、`result.json`、`lease-result.json` 一一对应。
托管实现必须执行同一份冒烟包与同一条 10 分钟额度规则；它不能自行放宽额度，
也不能把 `NOT_RUN` 报成通过。

## 界面行为

- **倒计时**：本地每秒渲染，截止时间始终以服务端 `expiresAtEpoch` 为准，轮询会重新对时。
- **到期禁用**：额度耗尽后按钮变为「重新运行（新的免费额度）」，开一条全新租约，
  而不是把旧租约续下去。
- **显式续期**：面板内提供续期，但强制填写理由（≥4 字符）与操作人；超出免费额度的
  秒数以 `billableSeconds` 显示并计入 Batch 44 的计量边界。续期走审计，
  即使运行本身没离开本机。
- **回收报告**：到期后展示停了几个进程、是否有进程未在宽限期内响应 SIGTERM、
  容器与卷的处理结果、删除了多少临时数据、有无残留。
- **证据保留**：服务被回收，`result.json`、门禁结论及带原始字节数的有界日志尾部仍可
  在界面上查看；Console 不把任意长度日志装入 API 响应。

## 并发与证据隔离

- 会话创建先拿租户锁，再拿由真实项目路径摘要得到的项目锁；同一个项目不能被两个
  本机会话同时启动，跨租户竞争同样失败关闭。
- 运行租约写入 `console_session_id`。续期和停止前必须同时匹配租户、会话记录、真实
  项目路径和当前租约；旧会话句柄不能操作同项目的新租约。
- 同项目重跑前，上一会话必须已经生成 `result.json`、`lease-result.json` 和
  `gate-result.json`。随后这些 JSON 与有界日志会复制到
  `smoke-sessions/evidence/<sessionId>/`，每个文件绑定真实字节数和 SHA-256；最后才清空
  项目的当前运行目录。最终化尚未完成、快照被篡改或存在不归 Console 管理的 CLI
  运行产物时，重跑都会被阻断。

## 与 CLI 的关系

按钮启动的就是 `smoke/tools/run_smoke.py`，续期与停止调用的就是
`smoke/tools/smoke_lease.py`。运行器进程是 detach 的：Console 重启不影响它，
租约看门狗仍在自己的进程里管着回收。看门狗每轮会重读 `lease.json`，因此在
界面上批准的续期会被正在运行的实例真正采纳，而不是只记录不生效。

## 转换完成页的接入约定

`TranslationStudio` 在 `job.artifactReady` 后以 `projectRef={job.id}` 渲染按钮，
即约定转换产物落在 `${ELMOS_SMOKE_PROJECTS_ROOT}/<jobId>` 且已挂好冒烟包。
若产物不在那里，`/api/smoke/pack` 返回 `SMOKE_PACK_NOT_FOUND`，面板照实提示，
不会假装可以运行。其他业务线接入只需一行：

```tsx
{artifactReady && <SmokeRunButton projectRef={generatedProjectRef} />}
```

## e2e

`apps/web-console/e2e/smoke-run-button.spec.ts` 覆盖两层：

- **真实会话旅程**（chromium 串行执行一次）：真的 scaffold `e2e/fixtures/smoke-projects/demo-service`，
  真的通过按钮的 API 起服务、跑断言、显式续期、停止回收，并断言门禁给出 `limited`
  与保留下来的证据；随后重跑同一项目，验证旧证据摘要不变且旧会话不能停止新租约。
  fixture 只用 Python 标准库，配合 `ELMOS_SMOKE_SKIP_INSTALL=true` 所以不依赖网络。
- **界面桩测试**（沿用仓库既有 `page.route` 约定）：倒计时与服务地址、NOT_RUN 照实显示、
  续期未填理由时无法提交、到期后按钮变「重新运行」并展示回收报告与门禁结论、
  没有可用执行位置时按钮禁用并说明原因。

```bash
pnpm --dir apps/web-console exec playwright test e2e/smoke-run-button.spec.ts --project=chromium
```

`playwright.config.ts` 会在 runner root 下创建 `smoke-projects/` 与 `smoke-runtime-state/`
并注入对应环境变量；spec 通过 `ELMOS_E2E_SMOKE_PROJECTS_ROOT` 找到它们。
若机器上没有 python3，真实旅程会 skip 而不是假通过。
