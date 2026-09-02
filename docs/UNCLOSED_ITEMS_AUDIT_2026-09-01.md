# ELMOS 未闭环项审计 — 2026-09-01

按仓库自己的口径，逐 pack 清点「未完成 / 未测试通过 / 未认证通过」，并区分哪些是代码缺口、
哪些是设计使然的外部门禁。

## 执行边界

本次**没有执行任何 `make` 目标、batch 门禁脚本或 e2e 测试**——本地 Linux 工作区在整个会话
期间卡死。下面每一条状态都来自仓库里已经存在的、由工具确定性生成的结果文件
（`gate-result.json`、`gap-inventory.json`、`batch38-45-strict-gate-output.json`、
`BUSINESS_LINE_CLOSURE_MATRIX.md` 等）。

2026-09-01 续跑会话同样没有拿到 shell（本地 Linux 工作区仍然起不来，macOS 终端只能授到
「可见+点击」权限，不允许代打字），因此新增内容仍限于读取、比对与改文件；所有需要执行的
步骤固化在 `.ai-tmp/resume-audit-2026-09-01.sh` 里等人跑。

这是一次**读取式检测**，不是执行式复验：它能告诉你上一次门禁跑出了什么，不能保证当前
工作树重跑还是同一个结果。第 5 节正是一个反例。唯一现场计算的是第 5 节的 SHA-256 比对。

**更新（2026-09-01 23:47 UTC+8）**：`.ai-tmp/resume-audit-2026-09-01.sh` 的步骤 1、2 已由人
在本机执行（HEAD `765c97fc8`，`main`；日志 `.ai-tmp/logs/audit-resume-20260901-234740/`），
结果与本报告预测一致，已回写进 §5、§6、§9 与 §10 附记。步骤 3（全量基线）尚未执行。

## 1. 结论

仓库内能自证的部分基本闭环；对外能声称的认证一个都没有——而这在绝大多数情况下是设计使然。

ELMOS 的门禁是 fail-closed 的：`UNKNOWN` / `INCONCLUSIVE` / `NOT_RUN` 一律不算通过，
执行者不能给自己签字，本地跑绿的 `make verify` 按定义不构成独立验证证据。所以「全平台
`NOT_CERTIFIED`」的读数本身是正确行为，不是等着被假数据填平的失败。

| 读数 | 值 |
|---|---|
| 处于 `CERTIFIED` 的 pack | **0** |
| `certification_status: NOT_CERTIFIED` 记录 | 98 |
| `independent_verifier: NOT_RUN` | 124 |
| `decision: BLOCKED` | 11 |
| 从未执行的严格测试用例 | **2,648** |
| B38–45 认证阻塞项 / 待办项 | 224 / 183 |
| 结构门禁真判 failed 的 pack | 1 → **0**（v1 于 23:49 重跑清零，见 §5 附记） |

真正值得排期的只有三类：可立刻动手的（§5、§6）、要有人授权才能跑的（§3）、
机器永远做不了的（§7）。

## 2. 未认证通过 · Batch 38–45 成熟产品认证

8 个 pack 的 `gate-result.json` 无一 eligible。Batch 45 是综合认证，依赖前 7 个批次先过，
所以它连门禁都没被调用。

| 批次 | Pack | 门禁 | 在范围 Skills | 阻塞 | 待办 | 首要缺口 |
|---|---|---|---|---|---|---|
| 38 部署矩阵 | `deployment-matrix` | BLOCKED | 22 | 27 | 23 | 9 项指标未测量、8 项零容忍未评估、evidence-manifest 未产出 |
| 39 全球 SRE | `sre-operations` | BLOCKED | 22 | 27 | 23 | SLO / 恢复 / 事件演练通过率均未测量 |
| 40 供应链合规 | `supply-chain` | BLOCKED | 24 | 25 | 27 | **11 条凭据扫描发现待分诊**；两条 claim 非 PASS |
| 41 知识飞轮 | `knowledge-flywheel` | BLOCKED | 20 | 27 | 21 | 来源覆盖 / 隐私隔离 / 预测校准未测量 |
| 42 Agent 工厂 | `agent-factory` | BLOCKED | 22 | 28 | 23 | Agent 评测与 kill-switch 通过率未测量 |
| 43 版本生命周期 | `product-lifecycle` | BLOCKED | 20 | 23 | 21 | 全仓唯一有真实证据的 claim 在此 |
| 44 FinOps | `finops` | BLOCKED | 20 | 27 | 21 | 计量对账、预算护栏、毛利证据覆盖均未测量 |
| 45 综合认证 | `production-readiness` | **NOT_RUN** | 22 | 40 | 24 | 门禁未被调用：无 trust store、无签名请求、无现场证据 |

按类别：能力覆盖 172、指标未测 75、零容忍未评估 67、证据未产出 37、摘要仍是全零占位 16、
语料为空 16、无问责审批 8、认证状态非 CERTIFIED 8、跨批聚合 7、claim 范围 1。

**已有真实证据的只有两处**：Batch 43 的 `b43-schema-surface-compatibility`
（606 个 Schema 受检、527 个逐字段比对、0 破坏性变更）；Batch 40 的依赖清单
（493 个组件，`sbomCoverage = 0.9199`）与凭据扫描（7,800 个文件）。后者因 11 条发现未分诊
而诚实记为 `INCONCLUSIVE`，没有伪装成 PASS。

## 3. 未认证通过 · verification-packs 与其余 pack 根

结构门禁大多是绿的，但 `certification_decision` 无一例外是 `NOT_CERTIFIED`，
`pack_status` 停在 `experimental` / `limited`，最高本地判定 `READY_FOR_EXTERNAL_GATE`。

| Pack | 结构门禁 | pack_status | 判定 | 备注 |
|---|---|---|---|---|
| `frontend-72-route-formal-equivalence-v1` | failed → **passed**（23:49 重跑） | experimental | BLOCKED | stale 判定确认过期，结构清零；仅剩「v1 修复还是退役给 v2」的决策，见 §5 附记 |
| `build-cache-tenant-isolation-v1.2` | eligible=false | — | NOT_CERTIFIED | 8 项全 `NOT_RUN`：本地测试、负例语料、holdout、变异、P0 独立评审 |
| `frontend-72-route-formal-equivalence-v2` | passed | experimental | NOT_CERTIFIED | v1 继任者；`PROVED_UNDER_ASSUMPTIONS`，有界证明与模型形式化就绪 |
| `elmos-project-generation-source-ingestion` | passed | limited | NOT_CERTIFIED | holdout「本地跑过但无独立验证」；DNS rebinding 演练 `NOT_RUN` |
| `proof-driven-harness-v3-local` | passed | limited | NOT_CERTIFIED | 20+ 项指标未达阈值 |
| `formal-assurance-kernel-local` | passed | experimental | NOT_CERTIFIED | fuzz / 变异 / 元形态 / 模型迁移覆盖全部未达标 |
| `elmos-three-line-workflow-protocol` | passed | experimental | NOT_CERTIFIED | 负例语料清单缺失；fuzz 种子语料引用不是 pack 内安全路径 |
| `precision-migration-b01-44-runtime` | passed | experimental | NOT_CERTIFIED | 3 种必需验证技术在注册表里是「未知类型」——契约缺口 |
| 另 4 个 verification-pack | passed | experimental | NOT_CERTIFIED | 7plus1 契约、本地高级验证、多模态接入授权、polyglot 30 路线 |
| `frt-g01-g30-platform` | passed | experimental | READY_FOR_EXTERNAL_GATE | 472 Skills / 30 条有向路线；**9 项外部检查全部 `NOT_RUN`** |
| cloud / portfolio / dev-experience / marketplace | passed | experimental | NOT_CERTIFIED | 缺口全是外部执行：gcloud、真实 SCM、签名密钥、计费对账 |

## 4. 未测试通过

### A. 从未执行的严格测试用例（2,648 条）

不是「跑了没过」，是「一次都没跑过」。门禁按 `not-run` 判 `BLOCKED`，退出码 2 —— 预期行为。

| 套件 | 用例 | 结果 |
|---|---|---|
| `batch38-45-strict` | 400 | not-run 400/400；P0 218 · P1 91 · P2 91，通过率全 `0.0`；316 条 blocker；外部绑定 0 |
| `batch1-37-strict` | 408 | not-run；需逐用例验证者身份 + 套件外信任锚 + 可验签名 |
| `batch1-65-slightly-strict` | 750 | not-run；最高权威 `READY_FOR_EXTERNAL_GATE` |
| `batch66-80-slightly-strict` | 450 | not-run；需原生 / 供应商 / 生产环境 |
| `batch81-95-language-packs` | 640 | not-run；180 个直接源绑定、47,700 条用例-目标链接 |

### B. web-console e2e：干净代码上必失败的 5 个 spec

上一次会话已通过 `git stash` 复现验证：与任何新改动无关。

| Spec | 原因 | 归属 |
|---|---|---|
| `frt-external-quality:43` | 审批后的视觉基线根 `visual-baselines/approved/` 不存在（已确认该目录只有 `policy.json` 与 README） | 该 spec 属 `test:frt-external-quality`，不该进默认跑 |
| `generation-runner:253` | `.venv/bin/ruff` 报 `Exec format error` | 缓存 venv 里是错架构二进制 · 环境问题 |
| `project-evidence-charts:217` | 选择器 `exact` 匹配不上无障碍名 | **已定位·夹具过期**（§4-C 第 1 条，已修） |
| `project-evidence-charts:252` | `/translation` 根本不渲染覆盖图表 | **已定位·真缺口**（§4-C 第 2 条，未修） |
| `translation-evidence-adversarial:597 / :1076` | V3 support-matrix 夹具的 `reason` 文案落后于 canonical contract | **已定位·夹具过期**（§4-C 第 3 条，已修） |
| `vercel-deployment-smoke:36` | 打已部署 URL；对 localhost 健康端点返回 `UP`，不在允许列表 | 需 `playwright.vercel.config.ts` · 配置问题 |

`multimodal-intake.spec.ts` 的随机超时已于 2026-09-01 定位并修复（隐藏 file input 与按钮
共用 `disabled={busy || !recoveryStoreReady}` 门控，spec 加 `gotoIntake(page)` 等待），
不再是未决项。

### C. 三条「疑似」已逐条定位（2026-09-01）

**1. `project-evidence-charts:217` — 选择器写死了 `exact`，永远匹配不上。已修。**

`CoverageMeter` 的无障碍名是 `aria-label={`${label}，${valueText}`}`
（`app/components/ProjectEvidenceCharts.tsx:104`），而 NxN 面板传进去的 label 是
`` `${label}有向目标对` ``（同文件 `EquivalenceMatrix`，:367）。所以那个 progressbar 的实际
无障碍名是「直接行为等价有向目标对，0 / 2；未运行 2」，spec 里的
`{ name: "直接行为等价", exact: true }` 不可能命中任何元素。

同一条 case 的其余断言与实现是**对得上的**：`aria-valuemax` 期望 2，
而 `expectedEligible = 语言数 ×(语言数-1) = 2×1 = 2`；矩阵 region 名
「直接行为等价矩阵，可横向滚动」和单元格 `aria-label`「Java 到 Python，直接行为等价未运行，…」
都存在。所以这是选择器过期，不是产品缺陷。**已把选择器改成按前缀匹配
「直接行为等价有向目标对」。** 全仓只有这一个 spec 用 `role=progressbar` 选元素，改动无外溢。

**2. `project-evidence-charts:252` — `/translation` 根本不渲染覆盖图表。这是真缺口，未修。**

`TranslationEvidenceCharts`（`ProjectEvidenceCharts.tsx:524`）里确实有
`<h3>转换语义与行为覆盖</h3>`，而且**无条件渲染**——但**没有任何页面引用这个导出**。
`/translation` 渲染的是 `TranslationStudio`，该文件里 `semanticCoverage`、`behaviorCoverage`
一次都没出现；抽查的 11 个工作区组件（generation / translation / migration / frontend /
spring / playground / proof-loop / capabilities / 首页等）中，只有
`ProjectGenerationStudio.tsx:15` 引用了同文件的 `ProjectEvidenceCharts`。

也就是说：**接口返回了逐主题语义覆盖和逐工作单元行为覆盖，控制台把它们整个丢掉了**，
组件写好了却从未挂上去。这不是选择器问题，改 spec 不能解决——需要决定把它挂到
`TranslationStudio` 的哪个位置（任务恢复后的结果区最自然），属于产品决策，未擅自改。

**3. `translation-evidence-adversarial` — V3 support-matrix 夹具文案落后于契约。已修。**

契约端 `V3_RESEARCH_SUPPORT_CAPABILITIES`（`app/lib/server/translationRoutes.ts:125`）
把 11 条能力的 `reason` **逐字符钉死**，校验时 `capability.reason !== expected[3]` 即报
`TRANSLATION_ROUTE_V3_SUPPORT_CONTRACT_INVALID`（同文件 :1159）。而 e2e 夹具
`v3ResearchSupportMatrix` 写的还是早期占位文案（`"Initial scaffold; evidence required"`、
`"Not yet implemented"`…），11 条无一对得上。

失败必然从 `java-to-kotlin` 开始：`activePairs` 按 `activeLanguageIds` 顺序展开，
kotlin 是第 11 个语言，因此 `java-to-kotlin` 是第一条 research 路线；而
`assertExactV3ResearchSupportMatrix` 在 `assertExactV3ResearchCertification` **之前**执行
（:1402-1404）。报错文案正是「路线 java-to-kotlin 的 V3 capability 不是未执行的 canonical
research 声明」——与 §4-B 里记的现象逐字吻合。夹具的 certification / evidence 两份文档
经比对与 canonical 完全一致，**只有 support-matrix 落后**。
**已把夹具的 11 条 `reason` 同步为契约端的 canonical 文案。**

## 5. 已验证：一条门禁失败其实已经过期

`frontend-72-route-formal-equivalence-v1` 是全仓唯一结构门禁真判 `failed` 的 pack，
4 条失败全是「实现/回放捕获相对活仓库已过期」。

`scripts/batch32/validate_frontend_formal_route_campaign.py:1925` 的判据是：
比较 **campaign JSON 里登记的 artifact 摘要**与**活仓库文件的实际字节**，不匹配即报 stale。
三方（登记摘要 / pack 内捕获副本 / 活仓库文件）SHA-256 实测：

```
scripts/batch32/run_client_gate.py                          三方一致  9481bc56…   45,509 B
tooling/generate_frontend_formal_verification_pack.py       三方一致  191229bc…  378,230 B
tooling/run_frontend_formal_toolchains.py                   三方一致  1b64206e…  475,185 B
scripts/batch32/validate_frontend_formal_route_campaign.py  三方一致  dba418dd…  109,274 B
```

4/4 逐字节相同，字节数也相同——**触发失败的条件现在为假**。时间戳解释了原因：
`gate-result.json` 与被刷新的 `manifest.json` 都落在 2026-09-01 18:03:44 同一秒，
门禁结果是在同一次生成流程里、捕获刷新之前写下的。

**2026-09-01 二次独立复核**：换一个会话重做了这项比对，并且把范围从 4 条扩到
**登记表里全部 19 条仓库捕获**（implementation 清单 16 条 + replay 清单 3 条），
按 `validate_frontend_formal_route_campaign.py` 的原判据逐条比 `sha256` 与 `bytes`：

```
OK    : 19        STALE : 0        MISSING : 0
```

也就是说触发 stale 的条件对整张登记表都为假，不只是被点名的那 4 条。门禁的 `failures`
数组里也只有这 4 条，没有别的结构问题被这批失败掩盖——重跑后结构层预期干净清零。

**行动**：重跑该 pack 的 `run_verification_gate.py`（`make batch35-gate PACK=...`），
预期 4 条结构失败清零。注意只清结构层，`certification_readiness` 仍会因外部原因保持
`BLOCKED`。同时决定：v1 修复，还是正式退役让位给已通过的 v2。

**附记（2026-09-01 23:49 已执行）**：`make batch35-gate PACK=verification-packs/frontend-72-route-formal-equivalence-v1`
已在本机重跑，`GATE PASS`：结构失败 4 → **0**，`structural_gate_status: passed`。
`certification_decision` 仍为 `NOT_CERTIFIED`、`certification_readiness: BLOCKED`，
`certification_blockers` 42 条，全部是认证类外部条件（语料清单与独立验证、审批与签名、
证据阈值），与上文预测一致。重跑前后的 `gate-result.json` 快照保存在
`.ai-tmp/logs/audit-resume-20260901-234740/02-gate-result-{BEFORE,AFTER}.json`。
本节遗留的唯一事项是决策：v1 修复，还是正式退役让位给已 passed 的 v2。

## 6. 遗留脏产物 · 会被误提交

2026-09-01 19:58–20:04 之间，一次失败的默认 e2e 运行往
`apps/web-console/e2e/frt-external-quality.spec.ts-snapshots/` 写了
**9 个 PNG，合计 12.1 MB**（chromium/webkit 桌面与移动视口）。

`.gitignore` 覆盖了 `test-results/`、`playwright-report/`、`**/_snapshot-*/`，
但**没有覆盖 `*.spec.ts-snapshots/`**——这 9 个文件目前未跟踪，
下一次 `git add -A` 就会提交进去，而项目策略明确禁止「失败后自动更新视觉基线」。

**根因不是 `.gitignore`，是配置**：`playwright.config.ts` 的 `testDir` 是整个 `./e2e`
且没有 `testIgnore`，所以 `frt-external-quality.spec.ts` 会被默认跑收进去——而它需要的
approved 基线根与 `updateSnapshots: "none"` 只在 `playwright.external-quality.config.ts`
里设置。默认跑因此把未审批的候选图写进了 `e2e/*.spec.ts-snapshots/`。
同一个毛病还波及 `vercel-deployment-smoke.spec.ts`（需要 `ELMOS_E2E_BASE_URL` 指向已部署
环境，默认跑必然红），即 §4-B 表里的两行其实是同一类配置缺陷。

**已完成**（2026-09-01）：
- `.gitignore` 补上 `apps/web-console/e2e/*.spec.ts-snapshots/`。
- `playwright.config.ts` 增加
  `testIgnore: [/frt-external-quality\.spec\.ts/, /vercel-deployment-smoke\.spec\.ts/]`；
  `playwright.external-quality.config.ts` 因为 spread 了基础配置，同步加上
  `testIgnore: undefined` 解除继承来的排除，保证专用入口仍能跑到该 spec。

**已完成（2026-09-01 23:47 真机执行）**：9 个 PNG 共 12.1 MB 已删除；`git check-ignore`
确认 `.gitignore:103` 规则命中探针路径；`pnpm exec playwright test --list` 实测默认收集
已不含 `frt-external-quality` 与 `vercel-deployment-smoke` 两个 spec。日志见
`.ai-tmp/logs/audit-resume-20260901-234740/01-dirty-artifacts.log`。本节无遗留待办。

## 7. 未完成 · 实现层面

| 领域 | 当前实测 | 缺口 |
|---|---|---|
| Skills 目录 | 448 个 `normalized-source-incomplete`；752 个 `generated-planning-edition` | 前者缺源/领域契约，后者需领域负责人细化与批准 |
| Project Intelligence 包 | 50 个名字：21 `LOCAL` · 24 `PARTIAL` · 5 `PLAN` | 500 条源任务全 `todo`，248 个验收场景全 `NOT_RUN` |
| Foundry v3 包 | 1,310 个原子 Skill 中仅 26 个有仓库语义 handler | 其余 1,284 个停在 `PREPARE_ONLY` |
| Database & BigData 包 | 29 个技术记录全部 `catalog-only` | 无运行时 handler / 适配器 / 模板，实现状态 `DECLARED` |
| 跨语言转换 M29 | 156 条受治理路线：90 `limited` · 66 `research` | 全部执行证据 `NOT_RUN`；对象图、异常、异步、I/O、并发、依赖迁移未闭合 |
| ChinaDB 迁移 M31 | `SPEC_ONLY / BLOCKED`，78 条规划路线 | 13 个国产目标 renderer 一个都没实现 |
| SQL 方言转写 | 自动候选 1,173/1,485 = 79.0%；四目标 emitter 可达 343/1,173 = 29.2%（显式 `dbo` profile 下 33.5%） | 处置覆盖已 100%，但跨方言语义大头仍需人工迁移 |
| 组件转写 | 对 `apps/web-console` 实测预检 8/33 = 24.2% 在子集内 | 54 条方向对中仅 20 对有行为等价证据；ArkUI / Flutter 只能作目标端 |
| 死代码簇 | `modules/` 下 7 个模块零 `apps/` 引用 | 仍在每次 `make backend` 编译并跑测试。退役必须与 `ArchitectureRulesTest` 的 ArchUnit 规则同批下线 |

## 8. 阻塞认证的到底是什么

`mature_product_toolkit.py` 的 `manifest` 子命令在下列四项缺失时**拒绝生成清单**。
这是刻意设计——任何 Agent 都不满足独立性，不能签发这些证据。

1. **验证人独立性**——执行人与验证人必须是不同身份，且验证人确实在自己环境独立复现过。
   `run_strict_test_gate.py:256` 显式拒绝自验证。
2. **语料作者隔离**——holdout 与代表性负载在实现阶段对实现者不可见。文件系统证明不了，
   只能由人声明 `--attest-corpus-independence`。
3. **问责审批**——`certification.approvedBy` 必须包含 `program.owner` 且出现在 manifest 的
   `approvals` 里。当前 8 个 B38–45 pack 全部无问责审批人。
4. **离线密钥签名**——认证密钥必须与执行人不同，且在套件之外的信任存储中被授权给该批次。
   信任库放套件内会被 `run_strict_test_gate.py:242` 拒。私钥不进仓库。

外部环境类缺口：真实客户源仓与目标环境、生产等价部署、授权物理设备矩阵、真实 IdP 与
凭证轮换、外部 Secret Provider、跨区 DR 演练、渗透测试与供应链评估、
至少两个独立设计伙伴的客户验收。

## 9. 建议执行顺序

按「先便宜后昂贵、先能自证后需授权」排。前三步不需要任何外部授权。

1. **清掉 12.1 MB 脏产物并封堵复发**——~~待办~~ **已全部完成并真机验证**
   （2026-09-01 23:47，见 §6）。
2. **复核 §5 结论**——比对 19/19 全通过，门禁已于 23:49 重跑、结构失败清零（见 §5 附记）；
   **仅剩决策：v1 修复还是退役给 v2**。
3. **跑一次全量基线并与已知失败集对账**——`make verify` + 各 batch `validate_*` +
   `pnpm test:e2e`。先 `pnpm exec playwright install`（firefox 缓存构建曾损坏，
   必要时 `--force`），再逐条对照 §4-B——只有表外的红才是新增回归。
4. **攻两条疑似真缺陷**——三条已逐条定位（§4-C）：两条夹具过期**已修**，
   剩 `/translation` 不渲染覆盖图表这一条真缺口待产品决策。
5. **分诊 Batch 40 的 11 条凭据发现**——现场证据、逐条建议判定与允许清单模板已整理进
   `docs/BATCH40-CREDENTIAL-FINDINGS-TRIAGE-2026-09-01.md`。注意扫描证据是
   2026-08-06 的、指纹已漂移，**必须先重跑扫描再落允许清单**。仍需人签字。
6. **给 B38–45 补可本地测量的指标**——75 项指标未测、67 项零容忍未评估、
   16 处全零占位摘要。相当一部分（如 Batch 43 已示范的 Schema 兼容性）能用真实本地检查
   产出，不必等外部环境。`make batchNN-gaps` 随时可跑且不改变任何状态。
7. **再谈外部门禁**——指定问责审批人、准备离线签名密钥与套件外信任库、找独立验证人和
   隔离语料作者。这一步之前，任何 `CERTIFIED` 都是伪造。

## 10. 附记 · 2026-09-01 真机续跑对账（步骤 1–3 全部执行）

`.ai-tmp/resume-audit-2026-09-01.sh` 已在本机跑完步骤 1、2、3（HEAD `765c97fc8`，`main`）。

**步骤 1 — 脏产物，符合预期，§6 关闭。**
12.1 MB 脏快照已删；`.gitignore:103` 命中探针路径；两个 playwright config 的
`testIgnore` 生效；`--list` 实测默认收集不含 `frt-external-quality` 与
`vercel-deployment-smoke`。

**步骤 2 — v1 门禁，符合预期，§5 的「过期」判断成立。**
`GATE PASS`，结构失败 4 → 0；`certification_decision` 仍 `NOT_CERTIFIED`
（blockers 42，全部外部条件）。至此全仓没有任何结构门禁处于 `failed`。

**步骤 3 — `make verify` 是假红，不算证据。**
它死在 `uv --directory engines/database-data-engine/sql-transpiler run --locked pytest`，
报 “The lockfile at `uv.lock` needs to be updated, but `--locked` was provided”，
紧接在 “Removed virtual environment at `~/.cache/elmos-survey/venv-fa`” 之后。
根因是同一个 shell 里先前为 functional-assurance-engine 导出的
`UV_PROJECT_ENVIRONMENT=~/.cache/elmos-survey/venv-fa` 泄漏进了 `make verify`：
uv 拿另一个工程的共享 venv 去解 sql-transpiler 的锁，必然对不上。
**这正是 `.ai/CODE_LEVEL_BACKLOG.md` #11 记的那类假红**，与 chinadb 代码无关。
复跑前先 `unset UV_PROJECT_ENVIRONMENT`（或换新 shell），`make verify` 才有判据价值。

**步骤 3 — 全量 e2e：895 条，约 82 红。逐类归因如下。**

| 类别 | 现象 | 判定 |
| --- | --- | --- |
| **新真缺陷** | `multimodal-intake.spec.ts:26` `gotoIntake` 自递归 → `RangeError: Maximum call stack size exceeded`，chromium 约 22 条 + webkit/mobile 若干 | **本次红灯最大单一来源**；已修（`await gotoIntake(page)` → `await page.goto("/intake")`） |
| **环境** | firefox 全线 `libnss3.dylib` 加载失败 | 非产品缺陷；`pnpm exec playwright install firefox --force` |
| **已知** | `generation-runner.spec.ts:253` ruff 架构不匹配 | §4-B 原有条目，未变 |
| **已确认真缺口** | `project-evidence-charts.spec.ts:254` 找不到转换覆盖图表 | 与 §4-C 第三条同源：`TranslationEvidenceCharts` 无任何 importer，`/translation` 根本不渲染语义/行为覆盖。**待产品决策** |
| **待归类** | `experience-quality.spec.ts:30`（webkit + mobile-webkit）、`spring-real-journey-ui.spec.ts:525`/`:637`（mobile-webkit，1.0m 超时） | 疑似 webkit 专属渲染/时序问题，本次首次可见；需单跑 `--project=webkit --repeat-each=3` 判定是真缺陷还是抖动 |

**§4-C 三条的最终状态：**

- 选择器（`project-evidence-charts` 的 `直接行为等价` 前缀匹配）——**已修并实测绿**
  （chromium + mobile-chromium）。
- 夹具（`translation-evidence-adversarial` 的 V3 契约 11 条 capability 文案）——
  **已修并实测绿**（5 个 project 全绿，含 `:597` 与 `:1076`）。
- `/translation` 不渲染覆盖图表——**确认是真缺口，不是测试问题**。`project-evidence-charts:254`
  这次红得和预测一模一样。修法是把 `TranslationEvidenceCharts` 挂进
  `TranslationStudio`；挂不挂是产品决策，本报告不代签。

**下一步（按收益排序）：**

1. `unset UV_PROJECT_ENVIRONMENT` 后重跑 `make verify`——现在完全没有后端判据。
2. `pnpm exec playwright install firefox --force`，消掉整条 firefox 假红。
3. 单跑 webkit 三条待归类用例，确定真缺陷还是抖动。
4. 带上 `gotoIntake` 修复重跑 e2e，取一条干净基线，替换 §4-B 的已知红表。
5. 提交这批改动（`git status` 20+ 个改动文件 + 本报告）。
6. Batch 40 分诊签字（§9.5），以及 §9.6 起不变。

---

证据来源：`mature-product-packs/batch{38..45}/*/gate-result.json`、
`verification-packs/*/certification/gate-result.json`、
`client-packs/frt-g01-g30-platform/certification/{gate-result,frt-gate-result,gap-inventory}`、
`test-suites/batch38-45-strict-gate-output.json`、
`docs/{BATCH38-45-GAP-INVENTORY,BATCH38-45-CERTIFICATION-PATH,BUSINESS_LINE_CLOSURE_MATRIX,INDEPENDENT_VERIFICATION,CLIENT_EXPERIENCE_READINESS,batch-skills-completion-audit-2026-07-22}.md`、
`AGENTS.md`。§5 的摘要比对为现场计算，可用 `shasum -a 256` 复算。

本报告不修改任何证据文件、不推进任何认证状态。
