# 独立验证证据：如何真正产生它

## 为什么需要这份文档

仓库里有 **98 个 `certification_status: NOT_CERTIFIED`**、**11 个 `decision: BLOCKED`**、
**124 个 `independent_verifier: NOT_RUN`**。这些状态的共同前置只有一个：**独立验证**。

在本文档之前，仓库**没有任何一处说明独立验证者应当产出什么**。
后果不是「还没找到验证者」，而是**即使有人愿意做也无从下手** —— 要求分散在
`scripts/batch29/run_route_gate.py`、`scripts/test-suite/run_strict_test_gate.py`
等多个 gate 实现里，从未汇总。

因此这条不是排期问题，是**规格缺口**。本文档补上这个缺口。

下面每一条要求都**从 gate 代码反推**，不是新发明的流程。每条都标注了强制它的代码位置，
所以这份文档过时的时候，gate 会先失败，而不是悄悄放行。

## 不可协商的前提

**执行者与验证者必须是不同主体。** 这是整套证据体系的根基。
本仓库的任何本地运行 —— 包括 `make verify` 全绿、`run_production_matrix.py` 16/16、
四条 Spring 路线的 `PASSED_LOCAL` —— **都由执行者产生，因此永远不能充当独立验证证据**。
自验证会被 gate 显式拒绝（`run_strict_test_gate.py:256`）。

同理：**任何 Agent（包括生成本文档的这个）都不能签发独立验证证据。**
Agent 与执行者共享同一环境和同一意图，不满足独立性。Agent 可以准备材料、复算摘要、
起草报告，但**签名必须由一个独立的、可追责的人类或机构主体完成**。

## 三条业务线各自需要什么

### 跨语言转换路线（`routes/*/certification/`）

由 `scripts/batch29/run_route_gate.py` 强制。当前 30 条路线全部 `status: limited`，
`gate_results.independent_verification: NOT_RUN` —— 这是**合法的中间态**（第 166 行允许
`NOT_RUN` 或 `PASSED`，其它值一律判失败）。

要把一条路线推到 `certified`，第 174–178 行要求同时满足：

- `gate_results.independent_verification == "PASSED"`
- `gate_results.external_execution == "PASSED"`

且 `status: certified` 时仍需通过 `limited` 的全部检查：本地执行 `PASSED_LOCAL`、
独立 holdout 语料、真实仓库语料、evidence_refs 与 negative_refs 齐全
（第 155–160 行，`validate_independent_corpus` / `validate_evidence_refs`）。

**注意语料的独立性要求**：holdout 与 real-repository 语料必须与开发语料互不重叠。
用开发语料复跑一遍不构成独立验证。

### 严格测试套件（`test-suites/batch1-37-strict/`）

由 `scripts/test-suite/run_strict_test_gate.py` 强制，要求最完整：

1. **逐用例验证者身份**：每个 passed 用例的 `manifest.verifier.id` 必须存在（第 160–162 行）
2. **签名者即验证者**：`certification-request.json` 的 `signer_id` 必须与**全部** passed
   用例的验证者 id 完全一致（第 255–256 行）。混用多个验证者会直接 blocker
3. **套件外信任锚**：`trust_store` 中必须**恰好一个**未吊销的 anchor 匹配该 `signer_id`
   （第 267–270 行）。零个或多个都失败
4. **签名可验证**：`certification-request.sig` 由该 anchor 的 `public_key` 验签通过（第 282 行）
5. **信任库位于套件之外**：`--trust-store` 指向套件目录内会被拒（第 242–244 行的相对路径检查）

第 5 条是防自签的关键：信任库若在套件里，执行者就能自己造锚。

### Spring 路线与生成线

`evidence/spring-routes/*.json` 与 `docs/project-synthesis/*.json` 目前是
`independent_verification: NOT_RUN` / `independent_verification_status: NOT_RUN`。
它们没有独立的 gate 脚本，晋级路径是：由独立验证者在**自己的环境**重放
`replay` 字段记录的命令，产出与执行者互不共享的证据，再更新对应状态字段。

各自的 `replay` 命令已经记录在证据文件里，例如：

- 生成线：`uv --directory engines/project-synthesis-engine run --locked python scripts/run_production_matrix.py`
- Spring 线：`ELMOS_MAVEN_EXECUTABLE=<path> python3 scripts/batch30/run_spring_boot_reference.py --repo-root .`

## 建议的最小起步

不要试图一次推进 98 个 gate。**选一条路线打穿**，验证整套证据体系真的能往前走：

推荐 `routes/java-to-csharp`。理由：它的 `typed-pure-function-v1` 范围最小、
本地证据最完整、所需外部工具链只有 JDK 21 与 .NET 10，独立验证者的环境成本最低。

一次成功的晋级会同时证明两件事：证据格式可被第三方复现，且 gate 的
`NOT_RUN → PASSED` 通路确实通畅。在此之前，**98 个 `NOT_CERTIFIED` 的真实含义是
「未经检验」，而不是「已检验待批」** —— 这个区别对任何依赖本仓库做决策的人都是实质性的。

## 本文档不做什么

不授予任何认证，不改变任何 gate 状态，不把静态检查折算为独立验证。
写下流程不等于走完流程；在真实独立证据产生之前，全部状态仍然是 `NOT_RUN`。
