# 会话进度同步 — 2026-08-20

口径：**「代码存在」不等于「能力存在」。** 下表只把跑过、留下证据的算作完成。

## 一、已完成且已在 Mac 上验证

| 条目 | 证据 |
|---|---|
| #1 PHP 模块枚举（`--inventory`） | Mac 全量测试通过 |
| #2a Kotlin 作目标（发射侧） | `test_kotlin_target.py` 等 6 文件 **165 项绿** |
| #5b Go/Rust else-if 链 | 同上（`test_else_chain.py`） |
| Go emitter 的既有语法缺陷（`}` 与 `else` 分行） | 同上；此缺陷影响它产出过的**每一个** if/else |
| #10 CAS 底层与 V65 schema（工程验证） | `modules/persistence` 15/15 测试类共 **60 项 0 失败**；`verify_v65_migration.py` **45 项约束检查全绿**。这只证明底层与 schema，不证明生产调用链、持久 Action Cache 或跨实例索引 |

顺带查出并修掉的缺陷（均已随提交落库）：

- `analyze()` 对 pending 语言按「工具链未 pin」而非「分析器不存在」拒绝，
  错误信息指向一个不管用的修法 → 改为 `SOURCE_ANALYZER_NOT_IMPLEMENTED`
- emitted-target relift 闸门按路由成员资格判定，javascript 弃用后整门语言
  失去 relift → 补 `DEPRECATED_LANGUAGES`，并断言该闸门结构性不可达
- kotlin 返回点缺 integer→number 加宽（`fun f(v: Long): Double { return v }` 不编译）
- `_FORBIDDEN["kotlin"]` 保留了发射器从不写的名字、漏了它每次都写的名字
  → 新增跨语言不变量测试
- `exact_toolchain` 裸 `KeyError`、`_DIALECT` 条数硬编码

## 二、Python `let` 已接前端，但真实仓库的**观测增益仍为 0**

`let`（单赋值局部绑定）已有：IR 定义、类型检查（块作用域，取严不取松）、
11 个目标的发射、标识符 `local` 角色与分配、34 项测试。

此前——

```
grep -rln '"let"' native/ python_analyzer.py   →   (空)
```

**没有任何前端分析器会产出 `kind=let`**，所以此前系统实际接受的输入范围没有变宽。
本轮已经让 Python 前端产出 `let`（`ast.AnnAssign`），并把新增拒绝码接进 discovery
分类；但在干净的 LangGraph 固定提交上，447 个 tracked Python 文件只有 2 个结构
候选，完整分析器通过仍为 0。证据见
`python-let-real-repository-measurement-2026-08-20.json`。因此当前只算实现闭环，
**不声称真实能力增益，不把 `typed-pure-function-v1` 升到 v2**。

## 三、未完成

| 条目 | 状态 | 阻塞在什么上 |
|---|---|---|
| #2b Kotlin 作**源** | BLOCKED | 需先装 kotlinc 并纳入精确工具链 |
| #3/#4 react/flutter | 待拍板 | 移出矩阵（13→11，156→110 条路由）还是保留 |
| #5 子集扩容其余（5a 多函数、5c–5g） | EPIC | 5a 的前提我判断错过一次，需先用能力探针重量边界 |
| #6 执行平面 | EPIC | `modules/secure-execution-plane` 仍只有 127 行准入检查器 |
| #7 六个骨架引擎 | READY | 建议先回答「它们是否该独立存在」再动手 |
| #8 R10 独立验证 0/90 | BLOCKED | 需外部方 |
| #9 C 档 34 项 | EPIC | — |
| #10 CAS 生产闭环 | IN-PROGRESS | 已实现 capture roots 的 generation-safe 原子批次、unresolved graph 全 sweep fail-closed、多仓 `ResourceBinding`、verified legacy/CAS dual-read、JDBC metadata 精确读回、默认关闭的 tenant-local AES-GCM、durable JDBC ActionCache index 与完整 v2 subject/envelope 绑定；本轮 focused/module/static 验证已通过，但生产调用链/共享 tier/密钥与信任重验仍未闭合 |
| Execution Intelligence readiness | BLOCKED / NOT_CERTIFIED | 入口退出已 fail-closed；当前 280 passed / 18 skipped、Ruff 与 strict MyPy 通过，真实 `make certify` 正确返回 `BLOCK`/exit 2；本地 synthetic evidence 仍可手写且没有签名 provenance，不能作为 readiness 或生产证据 |

`certified_route_count` 仍为 **0**。

## 四、环境侧（本轮实际耗时最多的地方）

Mac 磁盘 926 GB 用满、可用一度只剩 112 MB，连锁挡住 Docker、surefire 报告、
`tempfile.mkdtemp`。根因是一个孤儿 APFS 快照挂载，`umount` 与 `deleteSnapshot`
互锁，只能重启解决。详见 `FINDINGS-2026-08-19-cas-wave2-closing-the-gaps.md`。

`scripts/cas/finish-mac-verification.sh` 因此加固了三处**同一失效类**——
「环境挑了个不对的东西，而报错发生在离原因很远的地方」：

1. `pip` 与 `python3` 不同源 → 选定一个解释器，装与跑用同一个
2. PATH 上的 `java` 是 openjdk 26 而项目要 [21,22) → 用 `java_home -v 21` 选定
3. `docker info` 在 Docker 未运行时无限等待 → 20 秒限时 + 明确出口

## 五、提交

- `5351a91f0` 路由引擎一整块（467 文件）
- `fe30628a6` 165 项绿的记录与磁盘阻塞说明
- `5b6cb5468` JDK 选择修正 + 首次可信的 CAS 全绿记录

---

## 六、Python 前端产出 `let` — 原子闭环完成，真实仓库增益 0

`python_analyzer._statements` 现在接受 `ast.AnnAssign`：

- **只接受带注解的形式**。裸 `x = 1` 没有声明类型，在这里推断出一个类型就等于
  「IR 的类型来自分析器的猜测而不是源语言自己的类型系统」——而这恰恰是 `let`
  被设计出来要避免的事。裸赋值单独给一个拒绝码
  `PYTHON_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET`，因为
  `PYTHON_UNSUPPORTED_STATEMENT:Assign` 会读成「赋值完全不支持」，那已经不是事实。
- `x: int`（无值）是声明不是绑定 → `PYTHON_ANNOTATED_DECLARATION_WITHOUT_VALUE`
- `(x): int =`、`obj.x: int =`、`a[0]: int =` → `PYTHON_ASSIGNMENT_TARGET_OUTSIDE_CERTIFIED_SUBSET`
- 非规范类型注解 → `PYTHON_UNSUPPORTED_LOCAL_TYPE:<注解原文>`

同时修了两处闭环缺口：

1. Python 独有算术的复核从参数环境开始，按源码顺序绑定 `let`，分支拿副本；不能
   使用 `types.check_function` 已经被顶层局部变量污染的最终环境。
2. `PYTHON_*` 局部绑定拒绝、`LET_TYPE_MISMATCH`、`LET_NAME_ALREADY_BOUND` 和
   `UNDECLARED_NAME` 现在归为明确的 `UNSUPPORTED`，不再误报成分析器未执行的
   `NOT_RUN`。同文件一个 READY 函数和一个拒绝函数也保持逐 symbol 分类。

**原子证据**：

- `test_python_local_bindings.py`、`test_type_semantics.py`、`test_local_bindings.py` 与
  discovery classifier 精确节点：**116 collected，退出码 0**
- Ruff（2 个源文件 + 2 个测试文件）：PASS
- strict MyPy（2 个源文件）：PASS
- scoped `git diff --check`：PASS

两套旧的重复全量诊断均不作为证据：一套持久日志在 55% 已有多组 F/E、没有摘要或
退出码，停止前日志 SHA-256 为
`3faebea221bfce325db4807c1051207f6aeb764c08ba284be617deca7b8802c5`；另一套没有
持久日志。本任务按共享协调边界没有重启 full pytest 或 repository matrix。

后续矩阵 owner 回传：唯一 `fixed2` repository matrix **223/223 PASS**（`19699.03s`），
post-freeze **503/503 PASS**；Python 四文件与矩阵闭环分别提交为 `a1d842042`、`fe836aab9`，
local/tracking/remote SHA 一致且 index empty。ArkUI/Harmony device runtime 仍为 `NOT_RUN`，
上述结果不构成设备、外部、客户或认证证据。

**真实仓库测量**：干净的
`/Users/stephen/DevProjects/AIProjects/langgraph@49ae27c2ae983cfb92091b0dea9f7bc37a716479`
有 447 个 tracked `.py`、2 个结构候选、0 个完整 analyzer READY；拒绝原因分别是裸
`Assign` 与 docstring `Expr`。观测增益为 **0**，继续 v1 / `NOT_CERTIFIED`。

## 七、Execution Intelligence 入口已 fail-closed

- `make certify` 去掉 `--min-calibration-samples 10` 与 `|| true`，恢复 CLI 默认门槛 20
- `make all` 与 CI readiness step 均传播非零退出码
- 本地证据 JSON 与 synthetic harness 仍可由同一执行者手写，缺少内容绑定的签名 provenance、
  独立 verifier 与不可变原始证据链
- 共享矩阵释放后已执行当前源码：入口回归 `3 passed`，全包 `280 passed, 18 skipped`，
  Ruff 与 strict MyPy（26 个源码文件）通过，workflow YAML 解析通过
- 真实 `make certify` 返回 make exit **2** 并打印
  `Decision: BLOCK (pass 9 · fail 2 · not executed 0)`；没有伪造样本来抬高状态
- readiness 继续 `BLOCK / NOT_CERTIFIED`；上述本地结果不是外部、客户、生产或认证 evidence

这项修复只保证入口把失败传播给调用者；它不证明输入 evidence 可信，也没有把 readiness
改成通过。

## 八、CAS 快照接线 — 默认关闭的本机工程切片，不是生产闭环

当前源码已把上一轮“六项全未实现”纠正为以下本地实现：

1. snapshot capture 在 DB 可见前登记 archive/manifest reference roots；根集合为原子批次，
   root reactivation 使用新 generation，延迟释放不能隐藏新一代活根
2. immutable object metadata 与 `ResourceBinding` 分离，同一 tenant 下同一 digest 可绑定多个
   repository/project 资源，读取要求精确资源绑定
3. legacy `cas:sha256:` 与 `cas://sha256/<hex>/<size>` 已有摘要校验的 dual-read 与显式迁移模式
4. JDBC catalog 精确读回 labels 与 provenance digest size，不再用 `0` 伪造未知 size
5. 新增默认关闭的 tenant-local AES-GCM 本机层；随机 nonce、tenant/key/digest AAD 与版本化
   operator-mounted key 文件均为本地工程边界，不是生产 KMS
6. 新增 durable JDBC `ActionCacheIndex`，持久化可重建 metadata、隔离/失效状态与信任决策。
   v2 subject 绑定完整 key/result/producer/risk/writer，verified receipt 不可由包外直接构造或跨
   Entry 重放，JDBC 读回会重算 envelope digest

共享 223-node 矩阵释放 CAS 源码后，本轮当前源码已通过：`modules/cas` 全模块测试；catalog/GC、
ActionCache/encryption、snapshot/integrations、persistence migration 与 portfolio 的 focused Maven
验证；control-plane main compile/package；task-scoped diff/XML/YAML/JSON 静态检查。普通
control-plane testCompile 仍被任务外 ChinaDB 测试的过期构造器调用阻断，记录为
`BLOCKED_BY_UNRELATED_TEST_COMPILE`。live PostgreSQL、真实双进程共享 object tier 与 Docker
provider 验证仍为 `NOT_RUN`，不能从本地单进程测试推导。

仍未闭合的生产边界：

1. snapshot delete/archive caller 未接 `releaseReferenceRoots`；commit-unknown provisional root
   reconciliation 未接。GC 已在任何未解析完整引用图时阻断 full sweep，但没有生产 collector/delete
   caller，且 catalog load 后新增 legal hold 与后续 object-store delete 之间仍有竞态；因此不能据此
   声称完整 retention/deletion 生命周期闭环
2. legacy reader 仍是 digest-only、tenant-unscoped；workspace-service materializer 仍只理解 legacy 路径
3. tenant-local AES-GCM 默认关闭，缺生产 KMS、密钥托管/轮换与真实 provider 证据
4. 缺 live PostgreSQL 与真实两进程共享 object tier 的重启/跨实例命中证据
5. `ActionCache` 无生产 execution caller；持久化的签名/attestation trust decision 没有在命中时
   依最新吊销/信任状态重新验证
6. `TenantContentAddressedCache` 的 portfolio key→digest 索引仍为进程内状态

因此这条路径继续默认关闭，只能报告 `SINGLE_HOST / NOT_CERTIFIED`；当前本地测试通过不能
转换为 production、scale 或认证证据。

## 九、2026-08-24 CAS / Snapshot / EI 收口

本轮把上一节仍列为未实现的本地代码路径继续闭合：

- CAS reference roots 已持久化 generation；多仓资源绑定、legacy/sized CAS 双读与显式迁移、
  JDBC metadata 完整读回均已接入。
- tenant envelope encryption 接入 production-facing KMS provider 端口，启动时缺 provider 即拒绝；
  本地测试只使用受控 provider，**没有生产 KMS/HSM、密钥托管或轮换证据**。
- ActionCache 持久索引保存 detached signature bytes，并在每次命中重新执行当前 key/trust/revocation
  判定；`CachedActionExecutor` 已成为生产调用切片。真实外部 trust/revocation authority 仍缺失。
- snapshot archive/root release 与 crash-stale PENDING reconciliation 已接入；DB lifecycle 为
  append-preserving，只有 `AVAILABLE -> ARCHIVED`。读取 lease 与并发 archive/GC 的生产协调、
  全租户 scheduler/reconciler 仍未证明。
- snapshot capture 的 organization/repository/installation 来自受 RLS 保护的数据库绑定；Git clone
  限制为精确 credential-free HTTPS origin/path 并禁止实例级 redirect。
- V70 对历史 SCM/snapshot tenant 冲突和非法 snapshot status 先 fail closed，再建立复合 FK、CHECK
  和不可变 lifecycle trigger。
- V71 为已验签 GitHub webhook 建立无直接 runtime table 权限的 installation/repository tenant route，
  delivery/outbox 显式写 tenant；未知、失活、payload 不同的 duplicate 与跨租户资源组合均拒绝。

当前实测：Java focused **197/197 PASS**（34 个测试类）；真实 PostgreSQL 17
上 CAS 10/10、snapshot/RLS/reconciliation/webhook 5/5，Flyway **71/71**；外部 MinIO 的两个独立
JVM（PID 35250/35273）完成同 digest 读回。该 MinIO 证据仍是同一宿主机，明确标记
`SINGLE_HOST_EXTERNAL_PROCESS / LOCAL_EXECUTED_SELF_ATTESTED / NOT_CERTIFIED`。

EI 当前源码：`299 passed, 11 skipped`；把生产 schema 应用到独立 PostgreSQL 17 后，store
conformance `22 passed, 0 skipped`；Ruff 与 strict MyPy（28 个源码文件）通过；安装 wheel 在源码
目录外读回 25 schemas / 7 config / 2 templates。有效但仅 3 个样本且无双签 provenance 的受控
负例使真实入口返回 `BLOCK`/make exit 2；空 evidence 返回 `NOT_CERTIFIED`，没有把未执行伪装成
失败或通过。EI 运营口径继续 `BLOCK / NOT_CERTIFIED`。

仍需保留的外部/生产阻塞：真实多主机共享 tier、生产 KMS、独立 trust/revocation authority、
snapshot 读 lease 与 GC 原子协调、全租户 reconciliation 调度、已有 V9 前 audit row 的受控升级
bootstrap、真实 GitHub App/webhook、ArkUI/Harmony 设备运行。`hdc` 当前不可用，设备证据为
`NOT_RUN`。因此 CAS 仍严格是 `SINGLE_HOST / NOT_CERTIFIED`，EI 仍是
`BLOCK / NOT_CERTIFIED`。
