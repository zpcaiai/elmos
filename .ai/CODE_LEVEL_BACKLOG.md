# 代码级实现 backlog

> 由 2026-08-19 的代码级评估（`FINDINGS-2026-08-19-elmos-polyglot-skills-assessment.md`）导出。
> 这份文件是**执行清单**，一条一条推进；每条给出判据、阻塞点和验收方式。
> 状态词表封闭：`DONE` · `IN-PROGRESS` · `READY`（可直接开工）· `BLOCKED`（需先解阻塞）· `EPIC`（需再拆）。
>
> **完成的唯一判据**：真实业务逻辑 + 接进真实调用链 + 有测试覆盖行为 + **执行过**并记录结果。
> 文件存在、目录存在、Skill 存在都不算。

## 2026-09-03 当前源码覆盖说明（优先于下方历史快照）

本节按 `main@a350d76c1` 重新核对。下方按日期保留的分析仍用于解释来路，但以下
结论已经被当前源码证伪或替代，不得再作为实施前提：

- 仓库是 **42 个顶层引擎 / 43 个测试步骤**，不是 41 个。现在由
  `scripts/operations/engine-test-registry.json` 逐项登记，统一入口为
  `make test-engine ENGINE=<name>`；`make test-engines-check` 强制新增引擎不能漏登记。
  结果明确区分 assertion failure、collection/internal error、无测试、环境缺失、超时和
  无 pytest 汇总，且 venv、临时目录及日志均在仓库外。#11 因此改为 `DONE`。
- `database-bigdata-engine` **不是零测试引擎**。运行时与安装完整性测试位于
  `tests/database-bigdata-skills/test_runtime.py` 和 `test_integration.py`，共 32 个
  `unittest` 用例，由 `make database-bigdata-skills` 和统一引擎入口执行。它仍是明确的
  bounded plan-skeleton；“没有 Provider/数据库副作用”是契约边界，不是要用模拟执行填掉的测试缺口。
- `composite-engine` 只有 policy/fixtures 是 ADR-0034 的刻意设计；可执行逻辑在
  `modules/composite-modernization`，不得再创建“第四个源码转换 Worker”。
  Batch 22–26 五个 Java Worker 也按 ADR-0051–0055 保持独立，以
  `modules/evidence-bound-engine` 承载共享传输和域策略。它们的 Provider Adapter
  `NOT_CONFIGURED` 是外部执行边界；#7 的“六个骨架逐个补”前提已过期。
- `routes/inventory.json` 当前权威口径仍是 **13 种活动语言 / 156 条路线**，
  `pending_analyzer_languages=[]`、`pending_repository_languages=[]`。Kotlin、React 和
  Flutter 的精确单元分析器及仓库表面已经接入；66 条相关路线仍是
  `research / NOT_RUN / NOT_CERTIFIED`。React UI 与 Flutter framework/UI 继续归
  `component-dialect-engine`，不得把 pure-function 分析器写成 UI 支持。此前“13→11”
  决定发生在这些实现落地之前，未进入当前契约，不能再机械执行。
- CAS、Snapshot、ActionCache 和 tenant API 已有 durable catalog/index、当前 trust
  revalidation 端口、调度队列、租约与控制面装配。当前仓库内的明确闭环缺口是：
  signed `ActionResult` completion write-back、生产 Authorizer/PayloadPolicy 绑定、
  ExecutionJob signed envelope、runner secret/egress/admission 接线，以及 repository
  retirement 的全局驱动和运维可观测性。真实多主机、KMS/HSM、独立 trust/revocation、
  gVisor/Kata/Firecracker、真实 GitHub App 与 R10 仍是外部门禁。

本轮已执行：统一入口 `functional-assurance-engine` **15 passed**，
`python-engine` **32 passed / 1 warning**，测试器单元测试 **12 passed**，
`operations-scripts-test` **70 passed**；这些是本地工程证据，不改变任何
`NOT_RUN / NOT_CERTIFIED` 外部状态。

## 执行环境约束（决定每条能在哪做）

| 环境 | 能做 | 不能做 |
|---|---|---|
| 云端会话容器 | 写代码；跑纯 Python 测试；go/rust/php/node/java/clang 原型 | 产出可采信的原生证据——版本与架构都不符合钉死的精确工具链（需 Apple clang 21 / Swift 6.3.3 / PHP 8.5.9 / Node 26 / Python 3.12.12 / arm64-macOS） |
| `device_bash`（桌面 Linux VM） | 读写挂载的仓库文件 | 没有任何 Mac 工具链（只有 node/java-runtime/python3/uv）；不能碰 git |
| 你的 Mac | 唯一能产出原生证据、跑精确工具链门禁、重生成 inventory 的地方 | — |

**因此每条的收尾动作固定是：云端写代码 → 提交回 Mac → 你在 Mac 上跑门禁。**

---

## #1 PHP 模块枚举 — `DONE`（待 Mac 复验）

`inventory_module()` 此前为 9 种语言实现了整文件枚举，唯独 PHP 落到
`MODULE_INVENTORY_UNSUPPORTED:php`，导致 20 个 php-source 管线节点结构性阻塞
（`HANDOFF.md` 称其为「这个决定在等的那个 blocker」）。

已完成：

- `native/php/analyzer.php` 新增 `--inventory` 模式（`moduleInventory` / `moduleInventorySubjects` /
  `inventoryDeclarationEnd` / `inventorySignatureText` / `inventoryHasStrictTypes`）
- 枚举 namespace / import / trait-use / class / interface / trait / enum / enum-case /
  method / property / class-constant / constant / function / closure /
  declare-directive / include-directive / top-level-statement
- `analyzable` 仅在「文件有 `declare(strict_types=1)` + 非引用返回 + 文件作用域无条件声明」时为真；
  其余一律 false，下游转为 `NATIVE_MODULE_DECLARATION_CONVERSION_UNCOVERED` 显式阻塞
- `native.py`：`inventory_module` 新增 php 分支，走既有的 `_run_trusted_php_analyzer` 可信通道；
  `_PHP_ANALYZER_SHA256` / `_PHP_ANALYZER_BYTES` 已重钉
- 测试：`test_php_target.py` +5（纯 Python，任何机器可跑）、
  `test_native_module_obligations.py` +2（真实工具链，仅 Mac）

云端已验证：5 个夹具（含 namespace/class/enum/trait/闭包/箭头函数/switch/无 strict_types/条件声明）
经**真实的** `_validated_module_inventory` 契约校验全部通过，span 全部字节在范围内；
`test_php_target.py` 除一条因云端未 stage `assembly.py` 而报 ImportError 外全绿。

三个实现期抓到并修掉的真 bug（都写进了注释，防回归）：

1. 函数参数变量被当成顶层语句 —— 有函数体的声明必须**整段跳过**，类体才继续下钻
2. `final class` 被修饰符分支吞掉整个类 —— 修饰符必须落空继续
3. **空 `signature` 在 PHP 编码成 `[]`，而契约要求 object** —— 直接 `MODULE_INVENTORY_SUBJECT_INVALID`；
   已用 `new stdClass()` 强制，并写了一条专门锁这个形状的测试

**你需要在 Mac 上做的**：

```bash
cd engines/polyglot-route-engine
uv sync --locked
uv run --locked python -m pytest tests/test_php_target.py tests/test_native_module_obligations.py -q
```

`test_the_php_analyzer_script_matches_its_recorded_pin` 必须绿——它是内容钉死的守门人。
之后 20 个 php-source 节点应从 `MODULE_INVENTORY_UNSUPPORTED:php` 变为逐声明的显式阻塞。

---

## #2a Kotlin 作**目标**（发射侧）— `DONE`（两个会话撞车，已合并；待 Mac 复验）

⚠️ **本条被两个会话同时实现**（2026-08-19 10:00–10:20）。另一会话的版本先落盘并保留；
另一版不提交。详见 `FINDINGS-2026-08-19-kotlin-verification-and-collision.md`。

已落地的实现（另一会话）+ 两点验证增量（本会话，用 kotlinc 2.1.21 实测）：

- `_TYPE_SPELLING` / `_KOTLIN_HELPERS` / `_CHECKED_INTEGER_CALL` / `_signature` / 文件发射
- `identifier_hygiene`：`_KOTLIN_RESERVED` + `_FORBIDDEN["kotlin"]` + `_DIALECT`
- **增量 1**：`_FORBIDDEN["kotlin"]` 补 `maxOf minOf`——它们是 `kotlin.*` 顶层函数里
  唯一在规范类型上签名精确相同的，实测会静默遮蔽（`maxOf(7L,2L)` 拿到迁移函数的 3 而非 7）
- **增量 2**：`tests/test_kotlin_target.py` 13 条，纯 Python 可跑

**验证**：同一 IR 发射到 Kotlin 与 Java，双双真编译运行，**18 项值全部一致**。
云端 kotlinc 非钉死版本，故为原型证据不是路由证据。

**待你裁决**：差分发现 **Java 与 C# 才是异类**——它们用语言内建溢出检查
（`Math.addExact` / `checked()`），把 JDK/CLR 自己的消息泄漏进可观察行为；
其余七个目标（含 Kotlin）都发规范的 `ELMOS_INTEGER_OVERFLOW`。
要不要统一，取决于行为 harness 是否比对异常消息。既有行为有证据背书，未擅动。

## #2b Kotlin 作**源**（提升侧）— `BLOCKED`（需先装 kotlinc 并纳入精确工具链）

- 参照物：`native/java/Analyzer.java`（816 行，JDK Compiler Tree API）
- 需要：Kotlin 编译器 API；先决是把 kotlinc 纳入 `toolchains.py` 的 symlink-free 精确树契约
  （Homebrew 安装会被拒，见既有 PHP 钉死教训）
- 阻塞点：Mac 上没有 kotlinc，`.sdkmanrc` 只有 java+maven
- 另需 `validation.py` 的 kotlin harness 才能做行为验证

## #3 + #4 React / Flutter 的归属 — `DONE`（2026-09-01 已拍板：移出语言矩阵）

> **决定（Ethan，2026-09-01）：react / flutter 移出语言矩阵，13 → 11。**
> 二者两端均未实现（`IDENTIFIER_POLICY_UNSUPPORTED`），留在矩阵里只让对外数字虚高。
> 连带影响：全矩阵 156 条与 `research_route_count` 66 条都要重算。
> **改数前先跑 `scripts/operations/validate_translation_route_matrix.py` 取当场的值，不要手算。**

**原「#3 React 分析器 READY」是错的。** 详见 `FINDINGS-2026-08-19-kotlin-react-flutter-placement.md`。

React 组件在 `typed-pure-function-v1` 的 IR 里**根本无法表达**——没有 JSX、props/state、节点树，
类型格只有 `{integer, number, boolean, string}`。而 React 的真实实现**已存在于
`engines/component-dialect-engine`**：10 框架、54 方向真转写、目标框架真编译器回验、
五端真 SSR 比对。再给路由引擎写一个 React 前端是造第二套。

- 建议：把 react/flutter 移出 `COMPLETE_MATRIX_LANGUAGES`，矩阵回到 11 语言 / 110 路由
- **这是产品决定，需要拍板**，因为会改变对外的语言数字（13 → 11）
- 无论怎么定，README 的「13 语言」都应注明：10 种双向可用，3 种两端均未实现

## #5 跨语言子集扩容 — `EPIC`（最大一块，需再拆）

`discovery.py` 的拒绝原因码就是当前真实边界。按解锁价值排序拆分：

| 子项 | 当前拒绝码 | 备注 |
|---|---|---|
| ~~5a 单文件多函数~~ **已实现，前提有误** | `MULTIPLE_ELIGIBLE_FUNCTIONS_REQUIRE_EXPLICIT_PARTITION` | 枚举已支持，卡在 assembly/equivalence 只处理单单元；`typed-pure-module-v1` 已存在，是最近的一步 |
| ~~5b else-if 链（Go + Rust）~~ | ~~`GO_ELSE_IF_OUTSIDE_CERTIFIED_SUBSET`、`RUST_ELSE_IF_OUTSIDE_CERTIFIED_SUBSET`~~ | **DONE 2026-08-19**，详见下方 |
| ~~5b2 if-init / 局部声明~~ **IR 侧 DONE 2026-08-19** | `GO_IF_INIT_OUTSIDE_CERTIFIED_SUBSET`、clang `hasInit` | IR 新增 `let`（单赋值局部绑定）+ 11 目标发射 + identifier `local` 角色，34 条测试；五目标真编译差分一致。**前端仍不产出 `let`**，见下 |
| 5c 跨文件调用 | 无（结构性缺失） | 需要真实符号解析，最难 |
| 5d 异常/错误通道 | `CSHARP_UNSUPPORTED_STATEMENT` 等 | |
| 5e async | `ASYNC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET` | |
| 5f 类与对象图 | 无（结构性缺失） | |
| 5g I/O、框架、数据库、并发 | 无 | README 明列未闭合 |

**建议顺序：~~5b~~ → ~~5a~~ → 5d → 5e → 5c → 5f → 5g。**

### 5b2 局部绑定：IR 侧已完成，前端开关待你决定（2026-08-19）

详见 `FINDINGS-2026-08-19-local-bindings.md`。

已落地：`models.py` 的 `let` 语句、`types.py` 的块作用域与五类拒绝、
`emitter.py` 的 11 目标拼写、`identifier_hygiene.py` 的 `local` 角色。
五个目标（python/java/go/rust/kotlin）真编译真运行，四组输入含截断除法边界全部一致。

**刻意没做：没有任何前端产出 `let`。** 因此不含 `let` 的既有 IR 发射字节不变，
90 条路由证据一个都不动。

**待你拍板**：前端开始产出 `let` 会改变 discovery 判定（原本被拒的文件开始产生单元），
进而改变证据；且按封闭 profile 的规矩，很可能意味着 `typed-pure-function-v1` → `v2`。
**建议**：先只在 Python 前端接受赋值，跑一遍完整证据，量出「有多少原本被拒的真实函数因此进入子集」，
拿那个数字再决定要不要升 profile。

### 5a 更正（2026-08-19 10:35）：本条前提有误，能力早已存在

`discovery.discover_repository()` 第 1087–1109 行**已经**把每个文件的
`eligible_candidates` 拆成 N 个独立 READY 单元，多于一个时命名为 `WU-#####-F###`，
恰好一个时保持 `WU-#####`。

我之前读的 `MULTIPLE_ELIGIBLE_FUNCTIONS_REQUIRE_EXPLICIT_PARTITION` 是
**单文件层 `discover_unit()` 的中间结果**，仓库层随后就把它拆开了。
只读单文件层就断言「管线不支持多函数」是错的。

拆分在语义上也是可证明的，不是权宜：`models.py` 的白名单只有
`name / literal / binary / return / if`——**IR 里没有 `call` kind**，
所以同文件两个函数结构上不可能互相调用，`composition.call_graph == []` 恒成立。

另注：`typed-pure-module-v1` 是**另一条**完整路径（`migrate_module` /
`verify_pure_module` / `module_equivalence` / CLI + 33 条测试），其清单的
`composition.input_domain` 只接受两个字面量，绑定 specialized-8 与 nodejs-18 两个路由集。
它与上面的 `-F###` 拆分是并列的两种做法，不是缺失。

### 5b 完成记录（2026-08-19）

审计发现**只有 Go 和 Rust 两个前端拒绝 `else if`**；其余八个（Python/PHP/Swift/TypeScript/
JavaScript/Java/C#/clang）都已产出同一种嵌套 `else: [if]` IR 形状。两个语言的规范里
`else if` 都定义为「else 分支里放一个 if」——是拼写不是构造，所以这是遗漏不是语义决定。

- `native/go/analyzer.go`：抽出 `ifStatement()`，`*ast.IfStmt` 落在 else 位置时递归包成单元素 else 体
- `native/rust/src/main.rs`：抽出 `lift_if()`，`Expr::If(chained) => vec![lift_if(...)]`
- **零 IR 改动、零 schema 版本变更**——发射端本来就递归处理 `else`
- 影响 24 条有向路由（12 条 go-source + 12 条 rust-source）
- `if init` 的检查在递归里保留，嵌套第三层的 init 一样被拒（有专门测试锁住）

**顺带修掉一个此前未知的既有缺陷**（见 `FINDINGS-2026-08-19-go-emitter-else.md`）：
Go emitter 对**任何** `if/else` 都发射语法错误的代码。Go 规范在闭合花括号后的换行处插入分号，
`}` 与 `else` 分行会让 `else` 悬空，`go build` 报
`syntax error: unexpected keyword else, expected }`。
影响全部 12 条 `X → go` 路由，只因语料里从没有过 else 分支才一直没暴露。
已改为 Go 专用的 `} else {` 同行发射；Rust 保持原两行形状（它本来就合法，改了只会作废已有证据）。

云端验证：Go 与 Rust 分析器均真实编译并运行；发射的 Go 通过 `go build`；
发射的 Rust 通过 `cargo build`；**源 Go 与发射 Go 在 12 个含全部边界值的输入上行为完全一致**。
新增 `tests/test_else_chain.py` 18 条测试，其中 14 条纯 Python 任何机器可跑。

**你需要在 Mac 上做的**：

```bash
cd engines/polyglot-route-engine
uv run --locked python -m pytest tests/test_else_chain.py -q
```

四条 `*_lifts_*` / `*_rejects_*` 测试需要钉死的 Go 与 Rust 工具链，只有 Mac 能跑。

## #6 执行平面 — `EPIC`

`modules/secure-execution-plane` 只有 127 行准入检查器，返回 `READY_FOR_EXTERNAL_GATE`，
常量直写 `REAL_RUNNER_AND_SANDBOX_EXECUTION_REMAINS_AN_EXTERNAL_GATE`。
`b100-*` 16 个 Skill 描述的 runner 证明、mTLS 通道、egress 强制、secret broker 均**无实现**。

拆分：6a rootless runner 隔离 · 6b workload identity 与远端证明 · 6c mTLS 通道 ·
6d egress 默认拒绝的真实强制 · 6e secret broker 与租约撤销 · 6f 签名任务信封验证

## #7 六个骨架引擎 — `READY`（逐个补）

> **决定（Ethan，2026-09-01）：先不合并，逐个补。** 合并问题不再阻塞本条。

| 引擎 | 现状 |
|---|---|
| `composite-engine` | **0 行代码**，只有 policy JSON 与 fixtures |
| `ai-platform-engine` | 65 行（Application + Controller，全部转发 `EvidenceBoundDomainEngine`） |
| `edge-iot-industrial-engine` | 64 行，同上 |
| `enterprise-architecture-engine` | 65 行，同上 |
| `operations-sre-itsm-engine` | 65 行，同上 |
| `software-delivery-platform-engine` | 64 行，同上 |

先决问题：**这六个是否真的需要独立引擎**，还是应当合并进已有引擎。补之前先答这个，
否则会产出六份新的骨架。

## #8 R10 独立验证 0/90 — `BLOCKED`（需外部方）

98 个 `NOT_CERTIFIED` gate 的共同前置。要求见 `docs/INDEPENDENT_VERIFICATION.md`。
这条不是写代码能关掉的——需要独立客户仓库与独立验证者。

## #9 C 档 34 项无实现能力 — `EPIC`

绝大多数以 #5 为前置（没有更宽的子集，写迁移器没有输入）。
少数可独立推进：`property-test-generator`（全仓仅 2 个文件命中）、
`data-equivalence-validator`（仅 1 个）、`runtime-topology-correlator`。

---

## #10 CAS 与 Action Cache — `IN-PROGRESS`（历史实现快照，生产闭环未完成）

> 本节保留 2026-08-19/20 的实现与验证快照。其“当前源码”“仍未闭合”和下一步清单
> 不再代表最新代码；本文件末尾的 CAS / Snapshot / EI reconciliation 才是当前口径。

来源不是 polyglot 评估，是 `elmos-infrastructure-foundation-skills-v1.0.0` 的
`elmos-content-addressed-cache`（P0/G3，42 条带 ID 的验收点）。动手前核对：全仓唯一的
「CAS」是 `TenantContentAddressedCache`（**66 行 HashMap**，无落盘/分层/GC/权限校验），
所以这块是从零写，不是补齐。

### 第一轮（2026-08-19 上午）

新模块 `modules/cas`（`elmos-cas`，Java 21，零 JDK 外依赖），已注册进根 `pom.xml`。
抓到两个真 bug，都写了防回归注释：

1. **淘汰会丢掉唯一副本** —— `TieredCasStore.put()` 先 admit 再登记 write-back 债务，
   新对象在 `reclaim()` 眼里是可淘汰的，而它此时只有 L1 一份。登记必须在 admit **之前**。
2. **UTF-16 排序会让两台 runner 算出不同 root digest** —— 目录项用 `String.compareTo` 排序时，
   补充平面字符排在部分 BMP 字符之前，与 UTF-8 字节序相反。已改为按字节比。

### 第二轮（同日下午）：底层能力补齐；「零调用者」只完成本机试验切片

当时 `modules/cas` 为 **6860 行主代码（36 文件）/ 3404 行测试（19 文件）/ 177 条测试**，云端全绿。

| 上一轮的缺口 | 现状 |
|---|---|
| 011 批量 API | `CasStore.putAll/getAll` + `CasBatch`：整批一次存在性探测，单项失败不中止整批 |
| 018 区域放置 | `RegionalPlacement`：未映射 residency 直接拒绝（绝不回落默认区）、写入前裁决、复制积压 |
| 026 mTLS 认证 | `WorkloadIdentity`：PKIX 链校验 + SPIFFE URI SAN + trust domain + clientAuth EKU + 吊销名单；`attested` 只能由它产出 |
| 027 验签 | `ResultSignature`：Ed25519 分离签名，信封绑定 action key/输出/权限域/状态，重放全部拒绝 |
| **014 S3/MinIO L2** | `S3CasStore` + 自写 `AwsV4Signer`，零依赖；进程内 mock S3 **重算签名**才放行 |
| **041 命中率基准** | `ActionCacheBenchmark` 实际跑出：不变输入 **1.0000**、单文件改动 0.9950（恰好一个模块失效）、换工具链 0.0000、降权限 0.0000 |
| 数据库迁移 | `V65__content_addressed_store_and_action_cache.sql`（7 表 + RLS FORCE + append-only 触发器），**在真 PostgreSQL 16.2 上跑过 45 项约束检查**（云端 `pgserver`，无 Docker） |
| OpenTelemetry | `CasTelemetry` + `OtlpExporter`（OTLP/HTTP JSON），埋点接进 `ActionCache` 与 `TieredCasStore` |
| 告警 | `CasAlerting` 六条规则，按不可恢复性定级，按规则+key 节流，webhook 投递 |
| Runbook | `docs/runbooks/cas.md`，八个场景 + 升级矩阵 |
| **调用切片** | `io.elmos.integrations.CasBackedArtifactStore` 实现 `SnapshotPorts.ArtifactStore/ArtifactReader`；快照新增默认关闭的本机 CAS 条件装配；`TenantContentAddressedCache` 的 blob 委托 `modules/cas`，但 portfolio key→digest 仍是进程内索引 |

合计 **193 条测试 + 45 项数据库约束检查**，全部执行过。三个 pom 加了 `elmos-cas` 依赖。

2026-08-20 精确源码已实现上一轮六项结构性缺口中的本地工程部分：

- capture-time archive/manifest roots 使用 generation-safe 原子批次；root reactivation
  不会被旧 generation 的延迟 release 隐藏
- immutable catalog metadata 与 repository/project `ResourceBinding` 分离，支持同租户多仓绑定
- legacy `cas:sha256:` 与 sized `cas://sha256/...` verified dual-read/显式迁移模式
- JDBC 精确读回 labels 与 provenance digest size
- 默认关闭的 tenant-local AES-GCM 本机层（fresh nonce + tenant/key/digest AAD）
- durable JDBC `ActionCacheIndex` 持久化可重建 metadata、隔离与失效状态

共享 223-node 矩阵释放后，当时源码已通过 `modules/cas` 全模块测试，以及 catalog/GC、
ActionCache/encryption、snapshot/integrations、persistence migration、portfolio 的 focused
Maven 验证和 task-scoped 静态检查。ActionCache v2 subject/envelope 已覆盖完整
key/result/producer/risk/writer 并在 JDBC 读回重算 digest，focused 负例已通过。live
PostgreSQL、Docker/provider 与真实双进程共享 object tier 仍为 `NOT_RUN`；上面的 193+45
是历史工程证据，不能替代这些尚未执行的生产等价验证。

**仍然未闭合，别写成别的**：

- snapshot delete/archive caller 未接 root release，commit-unknown provisional roots 没有
  reconciliation；collector 已在未解析完整引用图时阻断 full sweep 且 load 保留 legal hold，
  但缺生产调用者和跨 catalog-check/object-delete 的原子 hold 协调
- legacy reader 仍 tenant-unscoped，workspace-service materializer 仍只接受 legacy 路径
- tenant AES-GCM 默认关闭且只是本机 key-directory 方案；生产 KMS、密钥托管/轮换证据缺失
- 缺 live PostgreSQL 与真实两进程共享 object tier 的重启/跨实例命中证据
- `ActionCache` 仍无 execution caller；persisted signature/attestation trust decision 未按最新
  trust/revocation 状态重新验证
- `TenantContentAddressedCache` portfolio key→digest 仍是进程内索引
- 生产命中率数字、证书签发/轮换、私钥托管、在线吊销仍没有证据

因此 2026-08-20 的条件装配仍只允许报告默认关闭的
`SINGLE_HOST / NOT_CERTIFIED`；durable JDBC index 的存在不等于已有共享 object tier 或
真实跨实例命中。

**该历史快照已执行及当时仍待执行的验证边界**：

```bash
cd /Users/stephen/DevProjects/AIProjects/elmos
mvn -q -pl modules/cas -am test
# 已通过：另有 integrations/snapshot、persistence migration、portfolio focused tests
# NOT_RUN：live PostgreSQL、真实双进程共享 object tier、Docker/provider verification
```

详见 `FINDINGS-2026-08-19-cas-action-cache.md`（第一轮）与
`FINDINGS-2026-08-19-cas-wave2-closing-the-gaps.md`（第二轮）。

与 #6 的关系：`elmos-secure-sandbox-runtime` 与 `elmos-runner-scheduler-execution` 两个 Skill
覆盖了 #6 的拆分项，包已安装到 `.agents/skills/`，可直接按它们的带 ID 清单推进。
本轮的 `WorkloadIdentity` 已经把 6b（workload identity 与远端证明）的**验证侧**做掉了。

---

## 顺序建议

> **动手前先跑探针，再认领。**
>
> ```bash
> make capability-probe          # 仓库根目录
> ```
>
> （`uv run --locked ...` 在仓库根目录会静默回落到系统 python 并找不到文件——
> `--locked` 只在引擎自己的 project 内生效。）
>
> 本文件 9 条里有 3 条前提是错的，全部错在「靠读代码推断能力」。
> 探针从不推断——每项都调真实入口并记录返回，且把「这台机器没有工具链」
> 与「不支持」严格分开（`NOT_PROBED` vs `REJECTED`）。
> 见 `FINDINGS-2026-08-19-capability-probe.md` 与 `FINDINGS-2026-08-19-backlog-premise-audit.md`。
> **新增或复活条目时，把探针输出作为依据附上，不要只写结论。**
>
> **动手前先认领。** 在要做的条目下写一行 `IN-PROGRESS by <session> @ <HH:MM>`。
> 2026-08-19 因为没有这一步，#2a Kotlin 被两个会话各实现了一遍。
>
> **本文件有多个会话在并行编辑。** 改它请整文件读-改-写，别做定点替换：
> 2026-08-19 09:45 一次定点替换因为对方已改过同一段而静默落空，差点丢掉本段更新。

```
#1  DONE  PHP 模块枚举
#5b DONE  Go/Rust else-if + 修 Go emitter 语法缺陷
#10 IN-PROGRESS  CAS 本地结构已补 capture roots/resource bindings/dual-read/metadata/
                 tenant-local encryption/durable JDBC index；仍 SINGLE_HOST / NOT_CERTIFIED
    ↳ 2026-08-25 增量验证（另一会话，未改代码）：V65→V66→V67→V69 迁移链已对
      真 PostgreSQL 16.2 实跑，51 项全过。三次 NO FORCE→FORCE 窗口后 10 张 CAS 表
      的 relforcerowsecurity 全为 true，且 V66 的 RAISE 中止路径会把 FORCE 一起回滚。
      迁移层的 `live PostgreSQL NOT_RUN` 可据此改写；Docker/provider 与真实双进程
      共享 object tier 的跨实例证据**仍然没有**，别一起划掉。
      脚本 scripts/cas/verify_cas_migration_chain.py，
      详见 FINDINGS-2026-08-25-cas-chain-live-postgres.md

2026-08-20 当时的下一步（现由文末 reconciliation 更新）：
  #10a 接 snapshot delete/release 与 commit-unknown reconciliation，证明 unresolved graph
       的 full sweep fail-closed
  #10b 接 ActionCache execution caller、命中时签名/attestation trust 重验与真实共享 object tier
  #10c 替换 portfolio 进程内 key→digest；接生产 KMS/rotation 与 workspace-service CAS 路径
  #2a  Kotlin 发射侧（纯 Python，不需要 kotlinc）
  #5a  单文件多函数
  #7   先回答「六个骨架引擎是否该合并」再动手

需要你拍板：
  #3/#4 react/flutter 是否移出语言矩阵（13 → 11，会改变对外数字）

阻塞中：
  #2b Kotlin 源侧（待 kotlinc 纳入精确工具链）
  #6  执行平面（可按已安装的 elmos-secure-sandbox-runtime 等 Skill 的带 ID 清单推进）
  #8  R10 独立验证（外部依赖，前置最长，建议现在就并行启动）
  #5c/#5d/#5e/#5f/#5g、#9
```

## 路由账目（口径基准，别再算错）

| | 条数 |
|---|---:|
| 13 语言全矩阵 | 156 |
| **10 个真实语言 × 9 = 双向可用** | **90**（`limited_route_count`） |
| 触及 kotlin/react/flutter = 两端均未实现 | **66**（`research_route_count`） |

`certified_route_count` 仍为 **0**。kotlin/react/flutter 不只不能作源，**也不能作目标**
（`IDENTIFIER_POLICY_UNSUPPORTED`）。

每条完成后回写本文件的状态，并按 `.ai/` 约定追加一份 `FINDINGS-<date>-<topic>.md`。

## 08-19 全量 17 个失败的归因（`.ai/FINDINGS-2026-08-19-failure-attribution.md`）

`let`（局部绑定）造成 **0** 条。已修两组、留一组：

- **已修** 15 × `test_javascript_node` —— `native.py::analyze` 的
  `EMITTED_TARGET_REANALYSIS_UNSUPPORTED` 闸门只看 `ROUTED_LANGUAGES`，
  javascript 移进 `DEPRECATED_LANGUAGES` 后整门语言失去 relift 能力。
  补 `and language not in DEPRECATED_LANGUAGES`（`models.py:644` 早就是这个判据）。
  该闸门原先**零覆盖**，新增 `tests/test_emitted_target_reanalysis_gate.py`。
- **已修** 1 × `test_identifier_hygiene` —— `== 11` 改为 `== len(hygiene._DIALECT)`；
  断言本意是「方言摘要互不相同」，不该随语言数漂移。
- **待复跑** 1 × `test_javascript_esm_descriptor`（`PIPELINE_NO_VERIFIED_UNITS`，08-18 遗留）。

顺带记录一处并行线程的缺口：`project_graph.py:74` 有一份**本地**
`SUPPORTED_LANGUAGES`，里面**没有** kotlin/react/flutter。

**环境事实**：`engines/polyglot-route-engine/.venv` 指向 Mac 解释器，Cowork 的 device VM
是 aarch64-linux 且无网，`uv` 会去下 CPython 然后失败——**全量测试只能在 Mac 上跑。**

## 2026-08-24 CAS / Snapshot / EI backlog reconciliation 与当前源码增量

2026-08-24 的 197/197、34/34、live PostgreSQL 与同宿主 MinIO 结果只绑定当时精确源码和
环境。后续 catalog/tiering、ActionKey/dispatcher、workspace materializer/archiver 与 pre-V9
receipt 改动不能复用这些结果作为当前回归证据。

已从结构性 blocker 移出：

- GC reference roots 与跨重启 generation
- repository/project 多资源绑定
- legacy `cas:sha256:` / sized CAS verified dual-read 与显式迁移模式
- tenant envelope encryption 的 KMS provider 端口及缺 provider 的启动拒绝
- JDBC metadata 完整读回
- ActionCache detached signature 持久化、代码级跨实例 JDBC lookup、当前 trust 重验及 fail-closed opt-in caller 绑定端口
- snapshot archive/root release、stale-PENDING reconciliation、不可变 DB lifecycle、fenced materialization lease 与有界全局队列
- snapshot repository/installation/tenant 复合绑定
- 已验签 GitHub webhook 的 pre-principal tenant routing 与 tenant-bound outbox
- EI read-once schema validation、digest-bound 双签 provenance/trust-store 合同、外部 trust snapshot adapter 及 wheel resources
- `CasCatalog` 强制 metadata+roots 单事务发布、统一首发 generation 与 exact-generation release，
  in-memory publish 失败回滚；`TieredCasStore` 支持嵌套 durable tier、失败 flush 保留重试和统一状态锁
- workspace snapshot CAS-first/RLS-bound resolver、默认拒绝的 verified legacy compatibility，以及
  有界 no-follow spool、tar materializer 与 deterministic archiver 安全检查

仍未闭合，状态不得上调：

1. **真实多主机** shared tier、故障切换和并发跨实例压力；现有 MinIO 是同主机两个 JVM。
2. 生产 KMS/HSM、密钥创建/托管/轮换/吊销和灾备；本地 provider 测试不替代它。
3. 外部且独立治理的 ActionCache/EI trust、key revocation 与 verifier；本地 key registry/loopback authority 不独立。
4. ActionCache 的真实生产 tenant-API 与 runner completion write-back：本轮默认关闭的
   durable async hit-or-enqueue dispatcher 已接入 tenant-scoped `ExecutionJobPort` 幂等查询，
   先按持久 request digest 做权威 reconciliation，再允许同 key 重试；查询不可用或摘要不匹配
   仍 fail closed。deployment 仍必须提供 identity-bound authorization grant、typed payload policy
   与 current-trust revalidator；仓库仍没有真实生产 authorizer/payload-policy 实现，tenant API
   也尚未构造 ActionKey，runner completion 合同缺 signed ActionResult/output/provenance，因此
   不能写回缓存。
5. snapshot materialization lease 与全租户 scheduler 的生产部署、稳定 holder/election、archive/GC
   worker 协调，以及生产 KMS/shared tier、legal-hold/object-delete 原子边界、跨主机 Docker 和
   大规模/跨平台/对抗 archive 证据；本地 PostgreSQL 和静态代码检查不替代它们。
6. V9 前已有 `audit_events` 的真实受控升级执行证据：本轮新增 fail-closed pre-V9 bootstrap，
   默认只读且只接受 checksum/顺序完全匹配的 V1..V8，apply 需 target-bound 二次确认并在单事务
   锁内补 `organization_id`/回填 `org-system`/设 NOT NULL，绝不写 Flyway history。apply 在连接
   数据库前必须预留 durable pending `OUTCOME_UNKNOWN` receipt；mutation/commit/rollback ack-loss
   继续 unknown，只有确认 rollback 才能写 `BLOCKED`。`py_compile` 与 focused unittest **18/18
   PASS**，但尚未对真实历史 PostgreSQL 执行 assess/apply/reconciliation，不能用本地单元测试替代。
7. V69/V70/V72 大表 backfill/FK/索引/队列的在线 rollout、锁/WAL 容量与维护窗口证据。
8. 真实 GitHub App installation/webhook/redelivery/revocation 与 provider outage reconciliation；
   本地已验签、租户绑定的删除 webhook sink 和显式 begin/finalize retirement API 不替代真实外部流量。
9. ArkUI/Harmony 真实设备；`hdc` 3.2.0b 已安装但 inventory 为 `[Empty]`，继续 `NOT_RUN`。
10. portfolio cache 的生产授权与规模证据：本轮已把 key→digest 映射改成 durable
    `CasCatalog` ACTION_CACHE logical root，支持仅凭完整 InputManifest 的跨实例 lookup、精确索引
    查询、generation-bound invalidate 与 GC root release。发布前必须 `putDurable`，metadata+root
    在同一 catalog 事务提交，单实例 transient miss 不再撤销全局 root，读取还验证最低 retention；
    snapshot artifact 同样在 root publication 前修复 authoritative tier，并统一 64 字符 lifecycle
    receipt 边界。但 `signatureVerified`/tenant/trust 仍由外层调用者提供，必须由生产 authenticated
    principal/attestation authorizer 绑定，且真实共享 JDBC/object tier 的并发、容量和多主机证据仍缺失。
11. ActionKey v2 的生产 rollout：本轮将 canonical domain 升为 `elmos-action-key/2`，固定 component
    order，复合字段全部结构化摘要，dispatcher 使用同一 verifier 严拒 v1，并把 schema 写入 durable
    queue envelope。由于 v1 存在碰撞且持久行没有可安全自动迁移的原始身份，禁止兼容 fallback；
    上线前必须 quiesce mixed-version caller，并按租户受控 invalidate/expire 旧 ActionCache 行。

当前源码增量的验证边界固定为：pre-V9 `py_compile` + unittest **18/18 PASS**，CAS 窄测
**93/93 PASS**，snapshot lease/reconciliation/archive **35/37 PASS + 2 filesystem skips**，
控制面 dispatcher **33/33 PASS**，以及 Tiered/Compatible targeted `javac` **PASS**。V76/live
PostgreSQL、MinIO、真实多主机与外部 provider 证据仍为 **NOT_RUN**；不得把历史通过数改写成当前源码通过。

当前判定固定为 CAS `SINGLE_HOST / NOT_CERTIFIED`、EI `BLOCK / NOT_CERTIFIED`。
日期绑定的本地 72-migration PostgreSQL、双进程 MinIO 和 focused pass 只能减少当时代码级 backlog，
不能替代上述外部、生产、多主机、设备或独立认证证据。

### 2026-08-26 protocol closure and remaining production wiring

本轮进一步完成的本地代码级协议：

- atomic deletion tombstone 与 `PENDING`/`OUTCOME_UNKNOWN` publication fence；
- GC manifest exact/unique/disjoint accounting 与删除前 overflow refusal；
- repository incarnation epoch、ACTIVE -> RETIRING -> RETIRED、root-to-resource durable edge、
  retirement write fence、全部 root 释放后的 binding batch release 和 stale-token replay refusal；
- JDBC rollback 失败时 abort connection，禁止用恢复 auto-commit 意外提交 unresolved transaction；
- production snapshot source-lease/reuse fail-closed、inode-bound materializer spool、canonical PAX 与固定
  helper ENTRYPOINT/CMD。

聚焦结果为 core 195 PASS / 2 filesystem-assumption skips / 0 fail/error，app 63/63 PASS，pre-V9
18/18 PASS。V76 live PostgreSQL 因非本任务 persistence testCompile 错误未运行。

仍是生产 blocker、不得从 backlog 移出：

1. repository deletion 已由签名且租户绑定的 webhook sink、以及显式 control-plane begin/finalize API
   接入 CAS retirement fence；仍缺生产级 scheduler/reconciliation 对 root 释放、租约和最终 binding release
   的全局驱动，因此生产 bindings 不能宣称自动完成清理。
2. authoritative fenced source adapter 与 durable lease provenance schema 未提供；control-plane 当前安全地
   阻断新 capture 和旧行 reuse。
3. V76 的真实 Flyway/PostgreSQL、线上 rollout、锁/WAL/恢复验证未执行。
4. 真实多主机 shared tier、生产 KMS/HSM、外部 trust/revocation、部署侧 ActionCache
   authorizer/trust 与 signed completion write-back、生产 snapshot election/reconciliation/archive-GC、
   真实 GitHub App/webhook、Docker 跨主机与 ArkUI 设备证据继续缺失。

状态固定为 CAS `SINGLE_HOST / NOT_CERTIFIED`、EI `BLOCK / NOT_CERTIFIED`、ArkUI
`NOT_RUN / NOT_CERTIFIED`。

## #11 引擎测试统一入口 — `DONE`（2026-09-03）

当前实现见本文件顶部覆盖说明及 `docs/ENGINE_TESTING.md`。以下内容保留为问题发现记录；
其中“该做的”已经由 42 引擎完整注册表、统一 Python 结果判定、Makefile/CI 门禁和
CWD 回归测试闭合。

**症状**：仓库里 41 个引擎，**没有任何一个"跑任意引擎测试"的标准入口**。每个人和每个
agent 都要现试，而试错过程会产出**看起来完全像真的假红**。2026-09-01 为了跑通
`functional-assurance-engine` 一个引擎，连着产出三个假红才拿到真结果：

1. `uv run --directory engines/X pytest` —— `--directory` 改了 CWD，uv 报
   「Unable to find lockfile at uv.lock」，**而 uv.lock 就在那儿**。
2. 换成 cd 进引擎目录 —— `pytest` 不在该引擎依赖里，`uv run pytest` 退回去用了
   **PATH 上 Homebrew 的 pytest**（3.11），那个解释器不认识项目的 `src/`，
   报 `ModuleNotFoundError: No module named 'elmos_functional_assurance'`。
   看起来像"这个引擎从来没被导入过"，实际上模块好好的。
3. 加 `--with pytest` 之后能跑了，但在引擎目录里跑仍然 1 failed ——
   那条测试用**相对路径** `skills/...`，依赖 CWD。

**正确姿势（三个要素缺一不可）**：

```bash
cd <仓库根>                              # CWD 必须是仓库根，有测试用相对路径读 skills/
export UV_PROJECT_ENVIRONMENT=~/.cache/elmos-survey/venv-$e   # venv 别落进树里
export TMPDIR=~/.cache/elmos-survey/tmp-$e
uv run --project engines/$e $LOCK --with pytest \
  pytest engines/$e/tests -rfE -o 'addopts=' \
  --basetemp="$TMPDIR/bt" -p no:cacheprovider
# $LOCK：有 engines/$e/uv.lock 才加 --locked，没有则留空
```

**每一条约束都对应一个真踩过的坑**：`--project` 不是 `--directory`（后者弄丢 lockfile）；
`--with pytest` 保证 pytest 和项目同环境；`-o 'addopts='` 防命令行 `-q` 与 pyproject 的
`-q` 叠成 `-qq` 把计数行整行删掉；`--basetemp` 出树；venv 出树（否则污染 `git status`
并被资格收据算成漂移）。

**引擎之间不一致的地方**（都实测过）：`functional-assurance-engine` 有 `uv.lock` 但
**无 `dev` 依赖组**；`polyglot-route-engine` 要 `--group dev`；有的引擎干脆没有 lockfile，
依赖是当场解析的（那些引擎的绿**没有钉住版本**，不能当认证证据）。

**该做的**：一个 `make test-engine ENGINE=<名字>` 目标把上面这套封起来，
并让 CI 用同一个入口。**在那之前，任何"某引擎是红的"的结论都要先复核是不是假红。**

**判据（比修复本身更重要）**：`pytest` 在收集期失败时退出码是 **2**，不是 1，
且日志里没有 `FAILED` 行只有 `ERROR` 行。**只判"有没有 FAILED"或"退出码是不是 1"的
门禁，对这种整个引擎跑不起来的情况完全不报警。**

### 2026-09-01 实测：`functional-assurance-engine` = GREEN

`15 passed in 0.14s`（从仓库根跑）。但其中 `test_all_178_skills_dispatched`
**依赖 CWD** —— 同一份代码同一个环境，在引擎目录跑红、在仓库根跑绿。
**一个测试的通过与否取决于你站在哪儿，这是缺陷不是配置**，单独记一条。
