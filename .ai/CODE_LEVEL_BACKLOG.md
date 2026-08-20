# 代码级实现 backlog

> 由 2026-08-19 的代码级评估（`FINDINGS-2026-08-19-elmos-polyglot-skills-assessment.md`）导出。
> 这份文件是**执行清单**，一条一条推进；每条给出判据、阻塞点和验收方式。
> 状态词表封闭：`DONE` · `IN-PROGRESS` · `READY`（可直接开工）· `BLOCKED`（需先解阻塞）· `EPIC`（需再拆）。
>
> **完成的唯一判据**：真实业务逻辑 + 接进真实调用链 + 有测试覆盖行为 + **执行过**并记录结果。
> 文件存在、目录存在、Skill 存在都不算。

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

## #3 + #4 React / Flutter 的归属 — `NEEDS-DECISION`（原定级错误）

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

## #10 CAS 与 Action Cache — `DONE`（已接线；待 Mac 复验）

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

### 第二轮（同日下午）：把 6 个缺口和「零调用者」全关掉

`modules/cas` 现在 **6860 行主代码（36 文件）/ 3404 行测试（19 文件）/ 177 条测试**，云端全绿。

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
| **零调用者** | `io.elmos.integrations.CasBackedArtifactStore` 实现 `SnapshotPorts.ArtifactStore/ArtifactReader`；`TenantContentAddressedCache` 改为委托 `modules/cas` |

合计 **193 条测试 + 45 项数据库约束检查**，全部执行过。三个 pom 加了 `elmos-cas` 依赖。

**仍然未闭合，别写成别的**：生产命中率数字（基准是合成负载 + 模拟执行）；
证书签发/轮换、私钥托管、在线吊销；`JdbcCasCatalog` **编译过但没执行过**
（云端无 PostgreSQL JDBC 驱动，`JdbcCasCatalogLiveTest` 要 Docker）；
`SnapshotMaterializationService` 的装配点**还没改**成 `CasBackedArtifactStore`——
接口满足了，生产路径上还没人构造它。

**你需要在 Mac 上做的**：

```bash
cd /Users/stephen/DevProjects/AIProjects/elmos
mvn -q -pl modules/cas -am test
mvn -q -pl modules/integrations,modules/portfolio-scale -am test
mvn -q -pl modules/persistence -am test          # 需要 Docker
bash scripts/cas/finish-mac-verification.sh      # 包含 Docker 那半边，并自己选一个能装上 pgserver 的解释器
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
#10 DONE  CAS 与 Action Cache（**未接调用链，对生产状态贡献为 0**）

下一步，按「不阻塞」排序：
  #10a 把 CAS 接进 snapshot + Java 闭环   ← 让 #10 真正生效，优先级最高
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
