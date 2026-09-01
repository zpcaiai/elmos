# 演示线执行清单（乙方案）

> 日期：2026-08-25 · 由 Claude（Cowork 会话）起草 · **尚未认领任何一条**
>
> 口径：把 **Spring 老项目翻新**、**SQL 转换**、**代码理解/流程图/学习演示** 三条线推到
> **可学习、可演示**的程度。**不是**可收费、**不是**认证、**不是**独立验证。
>
> 状态词表封闭（沿用 `CODE_LEVEL_BACKLOG.md`）：
> `DONE` · `IN-PROGRESS` · `READY`（可直接开工）· `BLOCKED`（需先解阻塞）·
> `NEEDS-DECISION`（等用户拍板）· `EPIC`（需再拆）。
>
> **完成的唯一判据**：真实业务逻辑 + 接进真实调用链 + 有测试覆盖行为 + **执行过**并记录结果。
> 文件存在、目录存在、Skill 存在都不算。
>
> ⚠️ **动手前必须在下面的认领表里写上你的会话标识。** 这个仓库有过整块功能被实现两遍的前科
> （2026-08-19 Kotlin、2026-08-25 09:00 合并各一次）。

---

## 0. 明确不做的事（写在最前面，防止范围蔓延）

| 不做 | 理由 |
| --- | --- |
| 在线调试工作台（DAP / JDWP / 断点 / 单步） | 单独就占演示级总量一半以上；作第二阶段 |
| ChinaDB 13 个国产目标 renderer | 每个都要真实实例，+40–65 agent-日，且不影响"能演示" |
| 独立验证 / 认证 / GA | 按 `docs/INDEPENDENT_VERIFICATION.md`，**Agent 不能签发独立验证证据**；与本清单无关 |
| 跨语言转换线（M29）的子集扩容 | 不在本轮三条线内 |

演示级**不需要任何外部现金支出**：开源 Spring 工程与真实 schema 都免费；
Oracle / SQL Server 只在想要"真执行"时才需要买实例，演示用 PG/MySQL 真执行 +
另两个方言"解析 + 目标方言严格模式重解析校验"即可。

---

## 1. 执行环境约束（决定每条能在哪做）

| 环境 | 能做 | 不能做 |
| --- | --- | --- |
| 云端会话容器 | 写代码；跑纯 Python 测试；**装真 PostgreSQL / MySQL 取执行证据**；go/rust/php/node/java/clang 原型 | 产出可采信的**原生**证据——版本与架构都不符合钉死的工具链（需 arm64-macOS） |
| `device_bash`（桌面 Linux VM） | 读写挂载的仓库文件 | 没有 Mac 工具链；**不能碰 git**（含 status/diff） |
| 你的 Mac | 唯一能跑 Maven/Gradle/OpenRewrite 真构建、精确工具链门禁的地方 | — |

**并行提示**：C 线主体是 Python + Web，云端能写能跑，只在验收时用 Mac；
A/B 线才抢 Mac。所以 **A/B 与 C 可以真正并行，不互相排队**。

---

## 2. 认领表

> ⚠️ **2026-08-26 更新：认领单位是「引擎」，不是「条目」。**
> 两个会话可以从不同 backlog 条目走到同一个引擎——`engines/sql-dialect-engine` 已经发生过
> （10:23 差点被覆盖，靠写回前对 SHA-256 拦下）。认领 B 线任一条 = 认领整个 sql-dialect-engine。
> 详见 `FINDINGS-2026-08-25-b2-c1.md` 附录 C。


| 条目 | 认领者 | 时间 | 状态 |
| --- | --- | --- | --- |
| A1 | | | |
| A2 | | | |
| A3 | | | |
| A4 | Claude/Cowork | 2026-09-01 | `DONE` —— `.ai/DEMO-2026-09-01-runbook.md`（19 步真跑通 / 3 步需 Mac 或 Office） |
| B1 | | | |
| B2 | Claude/Cowork | 2026-08-25 | `IN-PROGRESS` |
| B3 | Claude/Cowork | 2026-09-01 | `DONE` —— 口径重量为 **44 条**（上游 30 / 可规避 14），6 个可上报缺陷带最小复现；**分诊的覆盖率收益实测 = 0**。见 `FINDINGS-2026-09-01-b3.md` |
| B4 | Claude/Cowork | 2026-09-01 | `DONE` —— 选 Matrix Synapse（重量 **89.93%**，schema 口径 94.46%）；结论不变但理由已换 |
| C1 | Claude/Cowork | 2026-08-25 | `IN-PROGRESS` |
| C2 | Claude/Cowork | 2026-09-01 | `DONE` —— 定自绘 SVG（不做 Mermaid）；确定性与横向滚动均已实测闭合 |
| C3 | Claude/Cowork | 2026-09-01 | `DONE` —— 纯标准库 OOXML，矢量三重机器验证已闭合；**Mac 上真打开过：5 页齐、未报修复**。缩放/选中两项渲染细节未逐项核，记为已知边界 |
| C4 | | | 本轮不做（C0 已定 CLI + 静态报告） |
| C5 | Claude/Cowork | 2026-09-01 | `DONE` —— 全链跑通（flow-discovery→spec→svg/report/pptx），被分析对象换成 `engines/uir-java-python`（sql-dialect-engine 正被改写）；判定标签 3/20→**20/20**；结构比对 20 if/1 while/40 分支边/可达 79/79 全对。见 `FINDINGS-2026-09-01-c5.md` |

---

## A 线 · Spring 老项目翻新（演示级）· 合计 25–40 agent-日

### 已核实的现状（读了 `evidence/spring-routes/*.json`，不是读文档）

四条路线各一份证据，形状一致：

```
route_id                  boot-2.7-maven-to-boot-3.5.3-java-21（另有 1.5 / 2.0-2.6 / 3.0-3.4）
execution_status          PASSED_LOCAL
behavioral_parity         true
probe_ids                 3 个
transformation            OpenRewrite · Maven 3.9.11 · rewrite-maven-plugin 6.44.0 · rewrite-spring 6.35.0
                          recipe io.elmos.openrewrite.SpringBoot2_7_18To3_5_3Java21（recipe_sha256 已钉）
source / target           各自真 build PASSED + jar_sha256 + /actuator/health + 3 条响应
authorized_customer_repository / rootless_runner / independent_verification / external_evidence
                          全部 NOT_RUN
certification_status      NOT_CERTIFIED
```

**参考工程是 `OrderControllerTest` —— 一个 controller。** 行为等价靠 **3 个探针**。
这就是"演示时最容易被问倒"的地方：路线是真的，语料是玩具。

### A1 · 真实开源工程语料（3–5 个）跑通 —— `READY` —— Mac —— 12–18 天

- **做什么**：选 3–5 个真实开源 Spring 工程（候选：spring-petclinic 的 Boot 2.7 分支、
  jpetstore、RuoYi 之类国内常见结构），逐个跑完与 `evidence/spring-routes` 同形状的流程，
  每个产出一份证据 json。
- **验收**：`execution_status` 与失败原因码齐全。
  **失败也算完成** —— 只要失败是显式的、带原因码的、可解释的。
  演示时"这类工程我们明确拒绝，原因是 X"比"没试过"强得多。
- **⚠️ 前提待核实（我没读这个脚本）**：`scripts/batch30/run_spring_boot_reference.py`
  是否只接受内置参考工程、能不能指向任意仓库。**第一步先读它**，再决定 A1 是
  "喂语料"还是"先改脚本"。这条前提没核实之前不要报工期。

### A2 · 探针从 3 条扩到覆盖 CRUD + 事务 + 安全 —— `READY` —— Mac —— 8–12 天

- 现在 3 条响应比对撑起 `behavioral_parity: true`。演示级至少要覆盖：
  分页/排序查询、写入后读一致、事务回滚、鉴权 401/403、异常响应体形状。
- **验收**：新探针在四条既有路线上全绿，且**故意破坏一次**（改 target 的一个行为）能让它变红。
  探针不能证伪就不是探针。

### A3 · Gradle 路线真实 tuple —— `BLOCKED`（先核实）—— Mac —— 5–10 天

- **文档级现状**：`docs/BUSINESS_LINE_CLOSURE_MATRIX.md` 称 Gradle 2.x 区间已精确声明为
  `[2.0.0,3.0.0)`、已接入 Gradle 8.14.3 隔离构建/测试/启动与 OpenRewrite Gradle 插件入口，
  但**精确 tuple 证据保持 `NOT_RUN`**。
- **⚠️ 前提待核实**：接线到什么程度、缺的是执行还是实现。我只读了文档没读代码。
  按本仓库反复吃亏的经验：「代码不存在」这类判断可靠，「行为不支持」这类判断只读一层会翻车。

### A4 · 演示动线 —— `READY` —— 任意 —— 2–3 天

- 一条从 `/spring` 页面进入、到下载并浏览器复算 SHA-256 结束的固定动线；
  失败分支也演一次（这是这个产品最有说服力的部分：它敢拒绝）。

---

## B 线 · SQL 转换（演示级）· 合计 20–30 agent-日

### 已核实的现状

- `certified-ddl-v1` + `certified-alter-v1`，PostgreSQL / MySQL / Oracle / SQL Server
  四方言 12 方向；解析用真 `sqlglot`，发射逐厂商手写，发射结果由**目标方言严格模式真重解析**校验；
  给定 DSN 时对 PG/MySQL 在事务回滚/临时库内**真执行** DDL。
- 覆盖率（`.ai/FINDINGS-2026-08-25-remaining-items.md`）：schema 语句 **908 / 2344 = 38.74%**。
  注意这个数字比上一轮报的 41.09% **低**，因为扫描器修复后分母涨了 32% —— 它更诚实。
- 真正读不了的：**42 条**单语句（带行号），不是"15 个文件"。
- 下一个投入产出比最高的 blocker：**`CERTIFIED_DDL_QUALIFIED_TABLE_NAME` 160 条**
  （pg_dump 的 `public.` 前缀）。
- 语料反差极大：Matrix Synapse 真实 schema **87.8%**，ELMOS 自己的迁移只有 **18.9%**。

### B1 · 模式限定名（160 条）—— ⚠️ `NEEDS-RETRIAGE`（2026-09-01：前提已过期）—— 云端

> **2026-09-01 两条线程独立实测：`CERTIFIED_DDL_QUALIFIED_TABLE_NAME` 出现 0 次**，
> 已被 `NAMESPACE_MAPPING_REQUIRED`（370 条）取代，且 `--namespace-map` 实测可解并留 digest。
> 「160 条」和「四方言含义分歧需先定失败关闭规则」这两个前提都要重新量过再定级。
> 见 `FINDINGS-2026-09-01-b3.md` §1、`FINDINGS-2026-09-01-a4-b4.md`、`FINDINGS-2026-09-01-crosscheck.md` §3。

- **需要你先拍板**：`public.orders` 在四个方言里含义确实有分歧
  （PG 的 schema、MySQL 的 database、Oracle 的 user、SQL Server 的三段式）。
  这是 **profile 决定，不是补丁**。先定失败关闭规则，再写代码。
- **验收**：真 PG + 真 MySQL 执行证据；不可达的组合一律 `BLOCKED` 而非静默降级
  （降级会改变约束的检查时机——这个仓库已经在引用动作上栽过一次）。

### B2 · 覆盖率 38.74% → 60–70% —— `READY` —— 云端 —— 10–15 天

- 方法固定：**每一步都由 blocker 表读数驱动**，不是拍脑袋挑构造。
  blocker 同时报"出现次数"与"不同原因数"——实测有过单个复制粘贴惯用法占某 blocker
  342 次里 340 次的情况，只按次数排名会误导路线图。
- **验收**：更新 `.ai/measurement-2026-08-21/sql-admission-final.json`，
  并给出四个引擎的零回归对比表（基线 vs 之后，FAILED 集合逐条一致）。
- **不要**为了让数字好看而缩分母。上一轮把 41.09% 改回 38.74% 是对的。

### B3 · 42 条真读不了的语句逐条分诊 —— `READY` —— 云端 —— 3–5 天

- 分成"上游 sqlglot 缺陷（可上报）"与"我们可以前置规避"两类，各带行号与最小复现。

### B4 · 演示语料选型 —— `READY` —— 任意 —— 2 天

- 演示用 **Matrix Synapse 的真实 schema**（87.8%），不要用 ELMOS 自己的迁移（18.9%，
  塞满 `DO $$` / RLS / 触发器 / `COMMENT ON`）。
- 同时准备一份"故意超出子集"的语句，现场演示它如何**带原因码拒绝** —— 这是卖点不是缺陷。

---

## C 线 · 静态流程图 + 学习演示（不含在线调试器）· 合计 35–55 agent-日

### 已核实的现状（逐文件读了代码）

- `engines/project-intelligence-engine`：**6364 行源码 + 1758 行测试**。
- `elmos-project-intelligence-skills` 共 **50 个 Skill：21 `LOCAL` / 24 `PARTIAL` / 5 仅规划**。
- **中间归约层有了，两端都没有**。处理器自己声明缺什么：

| 处理器 | 实际做的事 | 自己声明的 unavailable |
| --- | --- | --- |
| `reduce_debug_view` | 归约**已存在的**调试事件 | `browser-debug-workbench`，`ui_rendered: False` |
| `build_debug_mission` | 栈帧排成学习步骤 | `learning-model-adapter`、`interactive-debug-ui`，`model_used: False` |
| `discover_flows` | **只收集 import 边**，`confidence: INFERRED`、`unknown_runtime_branches: True` | `runtime-path-observations` |
| `derive_data_lineage` | 正则扫 `from/join/into/update` | `database-catalog-adapter`、`runtime-lineage-collector` |
| `reconcile_api_event_topology` | 正则扫路由注解 | `runtime-traffic-observer` |
| `compile_diagram_spec` | **唯一 bounded 完成的一个（`LOCAL`）** | — |
| `generate_presentation` | 只产 **manifest**，不产 PPTX | — |

- **完全没有接线**：`apps/web-console` 没有这条线的页面（全仓唯一命中是
  `app/lib/multimodalSkillCatalog.ts` 里的目录条目）；`apps`/`modules`/`services`/`packages`
  对 `project_intelligence` **零引用**。
- 有一个可用入口：`engines/project-intelligence-engine/src/elmos_project_intelligence/cli.py`
  （无依赖 JSON CLI，`manifest` / dispatch）。

### 两个**不能**复用的前提（已实测，别再撞一次）

1. **polyglot 引擎的调用图恒为空**：`engine.py:2972` 写死
   `source_user_call_graph: {"edges": [], "status": "EMPTY_AND_CLOSED"}`、
   `target_call_graph_policy: "UNSUPPORTED_EXCEPT_EXACT_EMITTER_HELPERS"`。
   认证子集里根本没有用户函数调用，所以这不是"还没填"。
2. **仓库自己没有任何 CFG / 基本块 / 支配树实现**。grep 到的
   `BasicBlock` / `control_flow_graph` 全在 `engines/sql-dialect-engine/.venv` 的 mypyc 里，
   是第三方。`pm-b14-*-cfg-ssa-adapter` 那批 Skill 没有 `runtime_handler_id`，是纯规格层。

**真正该复用的**：13 门语言的 analyzer 与 `inventory_module` 整文件枚举。
它比转写子集宽得多 —— 转写准入率 1/16046，但 inventory 能枚举整个文件的
namespace / class / method / 属性 / 语句。**画图走这层，不要走 route/equivalence 层。**

### C0 · 归属决定 —— `DONE`（2026-09-01 已拍板）—— 1 天

> **决定（Ethan，2026-09-01）：先做 CLI + 静态 HTML 报告，不做 web-console 新页面。**
> 因此 **C4 Web UI 本轮不做**；C2 的渲染产物直接喂这份静态报告。

- 这条线是 **web-console 的新页面**，还是先做 **CLI + 静态 HTML 报告**？
  后者能把 C4 从 EPIC 降成小活，先演示先反馈。**建议先 CLI + 报告。**

### C1 · 用 analyzer/inventory 层替换 `discover_flows` 的正则 —— `IN-PROGRESS`（只做完一半）—— 云端

> **2026-09-01 实测状态**：Python 侧是**真 `ast` 解析器**（`origin=PARSED`，控制流与 import 边都是，
> 08-31 已在树上）。**Java 及其余 12 门语言仍是正则**；`derive_data_lineage` 与
> `reconcile_api_event_topology` 仍是纯正则**且输出没有 `origin` 字段**，那两条线上解析与推断仍混着。
> ⚠️ **另一并行会话 09:46–09:47 正在把 origin 标注扩到 Java**（新增 `java_structure.py` +
> `test_java_structure.py`）。**待答**：那份实现是「4 条 `re.compile` + 注释/字符串遮蔽 + 花括号深度」，
> 不是 `ast`，却与 `ast` 产出共用同一个 `ORIGIN_PARSED` 标记——这与本条验收原文
> 「『解析器给出的』与『推断的』两种明确来源，**不能混**」有张力。见 `FINDINGS-2026-09-01-c5.md` 追加节。

- **做什么**：在 analyzer / `inventory_module` 之上产出函数级结构（声明、分支、循环、返回），
  喂给 `compile_diagram_spec`。先做 **1–2 门语言**（建议 Python + Java，两者 analyzer 最成熟）。
- **验收**：拿 elmos 自己的一个引擎当被分析对象，产出的图与人工阅读一致；
  分支/循环缺一个都要能被测试抓到。现有的 `confidence: INFERRED` 必须换成
  "解析器给出的"与"推断的"两种明确来源，不能混。

### C2 · Diagram Spec → 真渲染与导出 —— `READY` —— 云端 —— 8–12 天

- `compile_diagram_spec` 已是 `LOCAL` 完成的，输出 Diagram Spec；缺的是渲染端。
- 建议 SVG（自绘）或 Mermaid（外部渲染器）二选一，**先定一个**，别两套都做。
- **验收**：同一份 Spec 渲染两次字节一致（确定性），大图能横向滚动不撑破页面。

### C3 · `generate_presentation` 从 manifest 到真 PPTX —— `READY` —— 云端 —— 6–10 天

- 现在只产 manifest。接一个真 PPTX 生成，把 C1/C2 的图嵌进去。
- **验收**：生成的 pptx 能被真 PowerPoint/WPS 打开，图不是位图糊的。

### C4 · Web UI —— `EPIC`（C0 选了 CLI 就先不做）—— 8–15 天（若做）

- 只读代码视图 + 图 + 双向联动。**不含断点/单步**——那是第二阶段。

### C5 · 端到端演示 —— `READY` —— 3 天

- 被分析对象就用 elmos 自己（`engines/sql-dialect-engine` 体量合适）：
  读代码 → 出结构图与流程图 → 出一份学习演示 PPTX。自举演示最省语料成本。

---

## 3. 我**没有**核实的前提（照实列出）

这个仓库反复吃亏在"只读一层就下断言"。下面每一条在开工前都要先回读，
**不要**把它们当成已知事实排期：

1. `scripts/batch30/run_spring_boot_reference.py` 能否指向任意外部仓库（影响 A1 的性质与工期）
2. Gradle 路线到底接线到哪一步、缺的是执行还是实现（影响 A3）
3. `compile_diagram_spec` 输出的 Diagram Spec 具体形状，够不够画控制流（影响 C2 的选型）
4. analyzer / `inventory_module` 对 Java 的枚举粒度是否到语句级（影响 C1 能不能画到分支）
5. web-console 现有组件层能不能直接挂一个新页面，还是有注册表要同改（影响 C4）

判断可靠性的经验规则：**「某段代码不存在」可靠；「某个行为不支持」只读一层就断言会翻车。**

---

## 4. 工期与并行

| 线 | agent-日 | 环境 | 可与谁并行 |
| --- | --- | --- | --- |
| A（Spring） | 25–40 | Mac 为主 | 与 C 并行；与 B 抢人不抢机器 |
| B（SQL） | 20–30 | 云端为主 | 与 A、C 都能并行 |
| C（图与演示） | 35–55 | 云端为主 | 与 A、B 都能并行 |
| **合计** | **80–125** | | 2 个 agent 同时跑 ≈ **2.5–4 个月** |

顺序建议：**B2 与 C1 先起**（都在云端、互不相干、都是本轮价值密度最高的），
A1 等 `run_spring_boot_reference.py` 的前提核实结果出来再排。
