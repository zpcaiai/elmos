# ELMOS SQL 转换线的准确度与完整度——实测评估

日期：2026-08-21
状态：`LOCAL_EXECUTED` / `NOT_CERTIFIED` / 独立验证 `NOT_RUN`
配套文件：[`FINDINGS-2026-08-21-accuracy-completeness-measurement.md`](FINDINGS-2026-08-21-accuracy-completeness-measurement.md)
（跨语言转换 / 项目生成 / Spring 现代化三条线）

---

## 0. 一句话结论

**SQL 线是四条线里唯一一条准确度可以直接拿数字回答的。** 原因不是它更成熟，
而是它的工具链钉的是**库版本**（`sqlglot==30.14.0` / `30.13.0`）而不是 macOS 路径，
所以测量到哪都带同一份工具链背书——跨语言引擎在非 Darwin/arm64 上直接拒绝执行。

它由三块组成，成熟度差三个数量级：

| 块 | 干什么 | 完整度实测 | 准确度实测 |
| --- | --- | --- | --- |
| `sql-dialect-engine` | DDL/ALTER 方言转写 | 89 文件 5,297 语句：全语句 **12.4%**，只算 schema 语句 **37.2%**；且 **15/89 文件（992 KB）连词法都过不了** | 未测（本次只测准入） |
| `sql-transpiler`（Batch 31） | 类型化查询转写，7 profile / 42 路由 | 只覆盖查询，不覆盖 DDL/存储过程/触发器 | **TPC-H 22 条 × 42 路由 = 924/924 通过**，但发现 **8/42 路由会崩** |
| ChinaDB M31 | 13 个国产目标 | 78 条路线全部 `SPEC_ONLY` | 实跑 13/13 `BLOCKED`，`target_sql = None` |

---

## 1. `sql-dialect-engine`：DDL 方言转写准入率

### 1.1 仪器

引擎自带 `scan.scan_repository`——用真实的 certified parser 逐语句判定
`IN_SUBSET` / `OUT_OF_SUBSET` / `SCAN_ERROR`，并带 blocker 目录。
这是本仓库里工程质量最高的测量面：它自己就把 `count` 和 `distinct_reasons` 分开报，
并在 caveat 里写明「这是上界」。本次只补了语料和聚合。

### 1.2 语料

| 语料 | 来源 | 文件 |
| --- | --- | --- |
| `elmos-persistence-migrations` | 仓库自己的 Flyway 迁移 | 67 |
| `elmos-build-cache-migrations` | build-cache-engine postgres 迁移 | 8 |
| `elmos-p0-sql` | `docs/p0-implementation/sql` | 6 |
| `external-postgres-schemas` | pagila / sakila / northwind / chinook / Matrix Synapse | 5 |
| `external-mysql-schemas` | sakila / osTicket / employees | 3 |

外部 8 个文件全部从 `raw.githubusercontent.com` 原样拉取，未做任何清洗。

### 1.3 结果

```
89 文件 / 5,297 条语句
  全语句上界覆盖率        659 / 5,297 = 12.44%
  只算 schema 语句        659 / 1,774 = 37.15%
  引擎自身缺陷 (SCAN_ERROR)          0
  整文件无法词法切分     15 / 89 文件（992,408 字节）
```

**两个口径必须一起看。** 12.44% 那个分母里塞了 3,500 多条 `INSERT` 种子数据
（chinook / northwind 是带数据的 dump）。对「schema 迁移」这个主张，
37.15% 才是有意义的数字。反过来，只报 37.15% 会掩盖「客户给的 dump 里大部分不是 DDL」。

**分语料（只算 schema 语句）：**

| 语料 | schema 语句 | 进入子集 | 覆盖率 | 整文件解析失败 |
| --- | --- | --- | --- | --- |
| external-postgres | 452 | 402 | **88.94%** | 3 / 5 |
| elmos-build-cache | 120 | 43 | 35.83% | 0 / 8 |
| elmos-p0-sql | 73 | 26 | 35.62% | 4 / 6 |
| elmos-persistence | 997 | 188 | **18.86%** | 6 / 67 |
| external-mysql | 132 | 0 | **0.00%** | 2 / 3 |

### 1.4 三个只有跑真实语料才看得见的事实

**（1）引擎处理"普通第三方 schema"远比处理 ELMOS 自己的迁移好。**
Matrix Synapse 的完整生产 schema 单独测是 **366 / 417 = 87.8%**。
而 ELMOS 自己的迁移只有 18.9%——因为它们塞满了 `DO $$` 块、行级安全策略、
触发器函数、`COMMENT ON`、带正则的 `CHECK`。

README 里那个 **17.1%** 就是在这个最难的语料上测的（本次复现为 188/1093 = 17.2%，
口径内一致）。**这个数字低估了引擎在普通 schema 上的能力，同时准确反映了它在
ELMOS 自己这种重 RLS/触发器 schema 上的能力。** 拿它对外说「SQL 转换覆盖率 17%」
两头都不对。

**（2）15 个文件连语句都切不开。**
钉死的 sqlglot 对 pagila / sakila(pg) / sakila(mysql) / chinook / employees 直接抛
`ParseError`（如 `pagila-schema.sql` 第 221 行、`sakila-mysql` 第 292 行）。
`scan_repository` 对这种情况记**一条** `CERTIFIED_DDL_PARSE_FAILED`——
一个 87 KB 的 schema 因此在分母里只占 1。所以任何百分比都必须和
`files_parse_failed` 一起读。这 5 个都是最常见的公开示例库。

**（3）blocker 分布验证了引擎自己的告诫：看 distinct，别看 count。**

| reason_code | 出现次数 | 不同原因数 | 占被拒 |
| --- | --- | --- | --- |
| `CERTIFIED_DDL_UNSUPPORTED_STATEMENT` | 3,942 | **5** | 85.0% |
| `CERTIFIED_DDL_UNSUPPORTED_CHECK` | 450 | 11 | 9.7% |
| `CERTIFIED_DDL_QUOTED_IDENTIFIER` | 66 | **63** | 1.4% |
| `CERTIFIED_DDL_UNSUPPORTED_TYPE` | 66 | 12 | 1.4% |
| `CERTIFIED_DDL_UNSUPPORTED_STATEMENT_MODIFIER` | 54 | 4 | 1.2% |
| `CERTIFIED_ALTER_UNSUPPORTED_ACTION` | 20 | 2 | 0.4% |
| `CERTIFIED_DDL_UNSUPPORTED_IDENTIFIER_SHAPE` | 19 | 4 | 0.4% |
| `CERTIFIED_DDL_PARSE_FAILED` | 15 | 15 | 0.3% |
| `CERTIFIED_DDL_UNSUPPORTED_DEFAULT` | 6 | 1 | 0.1% |

85% 的被拒来自 **5 个**不同原因（DML、`CREATE TRIGGER`、`COMMENT ON`、
`CREATE EXTENSION`、`SET`）。而 `QUOTED_IDENTIFIER` 只占 1.4% 却有 63 个不同原因——
那是 osTicket 每张表名都带引号。按次数排会把路线图指错方向，引擎的 caveat 说对了。

**MySQL 0% 的成因是可解释的，不是通用结论**：osTicket 用 `` `%TABLE_PREFIX%xxx` ``
反引号标识符（sqlglot 归一化成带引号标识符，被子集拒绝）＋ `UINT(10)` / `AUTO_INCREMENT`；
另外 2/3 个 MySQL 文件整文件解析失败。**样本只有 3 个文件，不足以支撑「MySQL 完全不行」**——
但足以说明当前没有任何一条真实 MySQL schema 通过。

---

## 2. Batch 31 类型化查询转写器

### 2.1 复现既有证据

`qualification.run_qualification` 在云端一次跑通，数字与 `docs/batch31/SQL_TRANSPILATION.md` 完全一致：

```
syntax:  eligible 248 / ready 248 / successRate 1.0 / goal 0.995 / goalMet true
negative: total 44 / blocked 44 / failClosedRate 1.0 / gateMet true
routeCoverage: covered 42 / required 42 / minimumPositiveCasesPerRoute 5 / gateMet true
localDecision: READY_FOR_ENGINE_EXECUTION
sourceExecution / targetExecution / resultEquivalence: NOT_RUN
certification: NOT_CERTIFIED
```

但语料是**合成**的，而且它自己在 JSON 里就这么写着：
`"authority": "ELMOS synthetic representative workload; real customer workload NOT_RUN"`。
四个语料合计 51 个 case（development 28 / holdout 7 / negative 9 / representative 7），
248 是它们在 42 条路由上的扇出。

### 2.2 新测量：TPC-H 22 条真实查询 × 42 条路由

用引擎没见过的 TPC-H 基准查询（业界标准分析型负载，替换点绑定为字面量）
跑 `transpiler.transpile`，判定取**返回结果的 `state`**，并要求
`target_reparse == PASSED` 且 `metadata.silentFallbackUsed == false`：

```
42 路由 × 22 查询 = 924 格
SUPPORTED   924   (100.0%)
UNSUPPORTED   0
SOURCE_PARSE  0
ENGINE_ERROR  0
```

**这是真结果，不是没测出来。** 负向对照同时跑了：引擎自己的 9 条 negative 语料
全部落到 `SOURCE_PARSE` / `UNSUPPORTED`，手写的 plpgsql 函数落到
`UNSUPPORTED_SEMANTICS`，垃圾输入落到 `SOURCE_PARSE_FAILED`。分类器能出非 SUPPORTED。

### 2.3 但负向对照顺手挖出一个真缺陷

手写用例里这条把引擎打崩了：

```sql
SELECT SUM(a) FILTER (WHERE b) OVER (ORDER BY d ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) FROM t
```

```
AttributeError: 'Filter' object has no attribute 'sql_name'
  sqlglot/generator.py:3163 in ordered_sql
```

**已最小化**：
- `SUM(a) FILTER (WHERE b)` 单独 → `SYNTAX_READY`
- `SUM(a) OVER (... ROWS BETWEEN ...)` 单独 → `BLOCKED`（正确的失败关闭）
- `FILTER + PARTITION/ORDER`（无 frame）→ `SYNTAX_READY`
- **`FILTER + 显式窗口帧` → 崩**

**影响面**：42 条路由里 **8 条**，正好是所有目标为 MySQL 8.4.10 或 SQL Server 2022 的路由
（这两个目标不原生支持 `FILTER`，要走 `CASE WHEN` 改写）。其余 34 条正常。

**根因**：上游 sqlglot 缺陷，在本仓库**两个 pin 上都复现**
（`sql-transpiler` 的 30.13.0 和 `sql-dialect-engine` 的 30.14.0，裸调 sqlglot 即可复现）。
**不是 ELMOS 的逻辑错误。**

**但仍然要修**：Batch 31 的契约写明「target emission raises on unsupported semantics」
并失败关闭。这个上游异常没有被拦，调用方拿到的是 AttributeError 而不是带诊断码的
`BLOCKED` 结果。升级 pin 不解决——发射路径需要把非 `UnsupportedError` 异常
转成失败关闭的诊断。

顺带：**同一个仓库里 sqlglot 有两个不同的 pin**（30.13.0 与 30.14.0）。

### 2.4 本次测量自身的一个错误（记录在案）

第一版脚本用 try/except 判定成败，报出 924/924。
那个数字是**对的但理由是错的**——`transpile` 遇到拒绝时**不抛异常**，
而是返回 `state="BLOCKED"` / `target_sql=None` 的结果对象。
只看异常等于把每一次拒绝都记成成功。是负向对照发现的，脚本已改成读返回态。
若不做负向对照，这个报告会给出一个无法证伪的 100%。

---

## 3. ChinaDB M31 商业扩展

`data/chinadb-commercial-v1.json`：

- 13 个目标：`dm8`、`kingbasees`、`opengauss`、`tidb`、`gbase-8s/8c/8a`、
  `highgo-hgdb`、`oceanbase-oracle/mysql`、`gaussdb-oracle/m`、`goldendb`
- 78 条 plannedRoutes，`state` **全部 `SPEC_ONLY`**
- 3 个显式排除：PolarDB、PolarDB-X、TDSQL
- 包级 `implementationStatus: SPEC_ONLY` / `externalExecution: NOT_RUN` / `certification: NOT_CERTIFIED`

**实跑验证**（不是读文档）：拿正确的 `capabilitySnapshotDigest` 对 13 个目标各发一次
`assess_commercial`，最简单的 `SELECT id, name FROM customers WHERE id = 1 ORDER BY id`：

```
13 / 13  state = BLOCKED,  target_sql = None
每个都带两条 blocker：
  TARGET_CAPABILITY_SNAPSHOT_NOT_EXTERNALLY_VERIFIED
  VERIFIED_TARGET_RENDERER_UNAVAILABLE  ("target SQL emission is prohibited")
```

digest 不对时更早一步就 `ValueError` 拒绝。**这条线一行目标 SQL 都不产出，
行为与声明完全一致。** 它是规格层，不是能力层。

---

## 4. 把 SQL 线放回四条线里

| 业务线 | 完整度 | 准确度 | 工具链背书 |
| --- | --- | --- | --- |
| 跨语言/跨库转换 | **0 / 16,046**（真实 Python 项目无一进入子集） | 366 次单函数比对全过 | 云端不可测（钉 Darwin/arm64） |
| SQL 方言转写 | schema 语句 **37.2%**；普通 schema 可达 88.9%，自家迁移 18.9% | 未测 | **可测，带 pin 背书** |
| SQL 查询转写 | 仅查询；不含 DDL/存储过程/触发器 | **924/924** 真实 TPC-H；8/42 路由有崩溃缺陷 | **可测，带 pin 背书** |
| 多语言项目生成 | 24/48 组合；6/8 语言单实体；关系 4 选 1 | 16/16 实跑通过 | Mac 实跑证据 |
| Spring 现代化 | 4 个精确元组；参考工程 1 个控制器 | 4/4 通过 / 3 个探针 | Mac 实跑证据 |
| ChinaDB | 78 路线全 SPEC_ONLY | 13/13 BLOCKED，零输出 | — |

**结论顺序变了。** 之前三条线里，跨语言线是"宽而浅"、Spring 是"窄而深"。
把 SQL 线放进来之后，最成熟的其实是 **Batch 31 查询转写器**：
它在没见过的真实基准负载上 42 条路由全过，且能被独立复现——
这是四条线里唯一一个「拿新语料测、数字仍然好看」的。

它的边界也很清楚：**只有查询**。DDL 归 `sql-dialect-engine`（schema 37.2%），
存储过程/触发器两边都不管，执行级等价（行值/类型/基数/顺序/空值/错误）
在两块里都是 `NOT_RUN`。

---

## 5. 交付物与复现

```
.ai/measurement-2026-08-21/
  measure_sql_admission.py        # DDL 准入率（含整文件解析失败与 DDL/DML 拆分）
  measure_transpiler_real.py      # Batch31 真实查询 × 42 路由
  sql-admission.json              # 5 语料 / 89 文件 / 5,297 语句
  sql-transpiler-tpch.json        # 924 格结果
  sql-transpiler-defect.json      # FILTER + 窗口帧崩溃，含最小复现与影响路由
  sql-corpus-manifest.txt         # 外部 8 个 schema 的来源 URL 与 SHA-256
```

复现（任意 Python 3.12，无需 macOS）：

```bash
# DDL 准入率
pip install "sqlglot==30.14.0"
PYTHONPATH=engines/sql-dialect-engine/src python measure_sql_admission.py \
  --corpus "elmos-persistence-migrations=<dir>=postgres" \
  --corpus "external-postgres-schemas=<dir>=postgres" \
  --output sql-admission.json

# Batch31 真实查询
pip install "sqlglot==30.13.0" duckdb
PYTHONPATH=engines/database-data-engine/sql-transpiler/src python measure_transpiler_real.py \
  --queries <tpch-dir> --output sql-transpiler-tpch.json
```

---

## 6. 本次评估自身的边界

- `sql-dialect-engine` 那一半是**源侧上界**：引擎自己的 caveat——进入子集的语句在
  目标侧发射时仍可能被拒。本次没跑目标侧发射。
- Batch 31 那一半是**语法级**：转写 + 目标重解析。
  源执行 / 目标执行 / 结果等价三项在引擎里就是 `NOT_RUN`，本次也没跑。
  `SUPPORTED` 不等于两条查询返回相同的行。
- 外部语料 8 个 schema 是按可获取性选的，不是统计抽样。
  MySQL 只有 3 个文件，**0% 不足以支撑「MySQL 不行」这种通用结论**。
- TPC-H 是分析型负载，偏 `SELECT`。它没有覆盖 DML、DDL、存储过程、游标、
  厂商函数——这些恰恰是真实迁移里最难的部分。**924/924 只对 TPC-H 这一类查询成立。**
- 三块都是 `NOT_CERTIFIED`，独立验证 `NOT_RUN`。

参见 [[capability-probe]]、[[backlog-premise-discipline]]、[[admission-rate-measurement]]。
