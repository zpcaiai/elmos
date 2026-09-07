# 子集扩展：SQL DDL 的两处，以及一个不该做的

日期：2026-08-25
状态：`LOCAL_EXECUTED` / `NOT_CERTIFIED` / 独立验证 `NOT_RUN`
承接：[`FINDINGS-2026-08-25-fixes.md`](FINDINGS-2026-08-25-fixes.md) §6 里列为「不是 bug」的四项

---

## 0. 结果

上一轮把四项判为「profile 决定而非缺陷」，并给了每项的实测收益。这一轮按那份收益
排序，把**能拿到真库执行证据**的两项做完了，并把**最像是该做**的一项测出了
「不该做」的结论。

| 项 | 上轮判断 | 这轮做法 | 结果 |
| --- | --- | --- | --- |
| `IF NOT EXISTS`（54 例） | 投入产出比最高 | 实现 + 逐目标失败关闭 + **真库执行验证** | 覆盖率 **+1.9pp** |
| CHECK 谓词（458 例） | 未列 | `IS [NOT] NULL` / `IN` / `BETWEEN` / 冗余括号 | 覆盖率再 **+2.0pp** |
| `UNANNOTATED_ASSIGNMENT`（25 例） | 有据的设计决定 | 按 `ir_local_bindings` 指定的路径**量出收益** | **净收益 0，决定维持** |
| 规范类型 / 单实体 / 关系 | 特性工作 | 未动 | — |

SQL 方言线 schema 语句覆盖率：**37.15% → 41.09%**，进入子集的语句 **659 → 729**。

---

## 1. `IF NOT EXISTS`：做了，而且是真库验证的

### 为什么它不能「顺手加上」

`IF NOT EXISTS` 不是装饰，它决定**迁移第二次跑的时候发生什么**：源里是空操作，
去掉修饰符的目标里是报错。所以问题不是「能不能解析」，而是「每个目标能不能说这句话」。
四个方言的答案不一致，而且**表和索引还不一致**：

| | `CREATE TABLE IF NOT EXISTS` | `CREATE INDEX IF NOT EXISTS` |
| --- | --- | --- |
| PostgreSQL | ✅ | ✅ |
| MySQL | ✅ | ❌ **没有这个写法** |
| Oracle | ❌ 拒绝 | ❌ 拒绝 |
| SQL Server | ❌ | ❌ |

Oracle 是 23ai 才有这个语法，而 `Dialect` 枚举**不带版本**——引擎分不出 23ai 目标和
19c 目标。按本仓库对未钉死版本的一贯做法：要么精确元组，要么拒绝。

SQL Server 任何在售版本都没有 `CREATE ... IF NOT EXISTS`。常见的绕法
（`IF NOT EXISTS (SELECT ... FROM sys.tables) BEGIN ... END`）是**另一条语句**，
事务与权限行为都不同，合成它就是引擎在发明语义而不是翻译语义。

不支持的目标一律 `CERTIFIED_DDL_IF_NOT_EXISTS_UNSUPPORTED_BY_TARGET`，
且 `emitted` 为 `None`——**一句都不给**。给出去掉修饰符的版本会通过所有语法检查，
然后在第二次运行时炸掉。

### 支持表不是查文档查出来的，是跑出来的

在容器里起了**真的 PostgreSQL 16.15 和真的 MySQL 8.0.46**，对每个格子执行验证：

```
supported cells                    第一次执行   第二次执行（应为空操作）
  postgres  CREATE TABLE           EXECUTED     EXECUTED
  postgres  CREATE INDEX           EXECUTED     EXECUTED
  mysql     CREATE TABLE           EXECUTED     EXECUTED

refused cell（证明拒绝是对的）
  mysql     CREATE INDEX IF NOT EXISTS
      服务器是否接受： False
      服务器原话：     ERROR 1064 (You have an error in your SQL syntax ...)
      引擎判定：       BLOCKED / CERTIFIED_DDL_IF_NOT_EXISTS_UNSUPPORTED_BY_TARGET
      结论：           CONSISTENT
```

**刻意用 MySQL 而不是 MariaDB**：MariaDB 接受 `CREATE INDEX IF NOT EXISTS`，MySQL 不接受。
拿 MariaDB 取证会给 `mysql` 方言一个相反的答案。

Oracle 与 SQL Server 没有免费的 root-less 本地服务器，所以它们**没有执行证据**——
但这两个格子是被拒绝的，压根没有语句可执行，所以不需要。

证据：`.ai/measurement-2026-08-21/if-not-exists-execution-evidence.json`

---

## 2. CHECK 谓词：458 条里的 429 条是同三个操作符

上一轮只知道 CHECK 被拒 458 次。这轮拆开看，**6 个不同原因**：

| 次数 | 原因 |
| --- | --- |
| 376 | `Is`（`IS NULL` / `IS NOT NULL`） |
| 49 | `In`（`IN (字面量, ...)`） |
| 21 | `RegexpLike` |
| 6 | 右侧不是纯字面量 |
| 4 | `Between` |
| 2 | `Like` |

profile 原本收窄的**理由**写在模型注释里：「不要函数调用、不要子查询，因为函数名正是
方言分歧最大的地方」。而 `IS NULL` / `IN` / `BETWEEN` 是**操作符不是函数调用**——
SQL-92 核心，四个方言拼写相同、含义相同。**收它们符合那条理由，而不是它的例外。**

仍然拒绝的，每一条都有真实分歧：

- `RegexpLike`（376，见下）— PG 是 `~`，MySQL 是 `REGEXP`，Oracle 是 `REGEXP_LIKE`，T-SQL 没有
- `Like`（2）— MySQL 默认排序规则大小写不敏感，**同一个谓词在不同目标上放行不同的行**
- `IS TRUE` — 也解析成 `Is` 节点，但 Oracle 没有布尔类型也没有 `IS TRUE`
- `BETWEEN SYMMETRIC` — PostgreSQL 独有
- `NOT IN` — 测量语料里一次都没出现，不做没测过的东西

另加一条纯语法的：**冗余括号**（`CHECK ((a > 0))`，19 次）。零语义，四方言渲染一致，
带深度上限地剥掉。

### 一个只有真跑四个方言才会发现的坑

sqlglot 对 `IS NOT NULL` 的**节点形状随读入方言而变**：

```
postgres  ->  Is(negate=True)
mysql     ->  Not(this=Is(...))
oracle    ->  Not(this=Is(...))
tsql      ->  Not(this=Is(...))
```

只处理第一种，就等于「从 PostgreSQL 源接受、从另外三个源拒绝」——而 `IS NOT NULL`
正是最常见的那 376 条。第一版实现就是这样，是把四个源方言都跑一遍才发现的。
现在两种形状都处理，并且**只对空值判断解包 `Not`**，`NOT IN` 和其他取反照旧拒绝。

真库执行验证（PostgreSQL 16.15 + MySQL 8.0.46，六个用例全部 EXECUTED）：
`.ai/measurement-2026-08-21/check-predicate-execution-evidence.json`

### 剩下的 407 条 CHECK 是什么

```
376x  RegexpLike        <- 全部是同一个 idiom
 19x  Paren             <- 已解包，但这些语句还卡在别的阻塞码上
  8x  右侧不是纯字面量
  2x  Like
  2x  Not
```

那 376 条不是 376 个问题，是**一个 copy-pasted 的哈希校验写法**
（`CHECK (h IS NULL OR h ~ '^[0-9a-f]{64}$')`）铺满整个 schema。
引擎自己的 caveat 说「按次数排会指错方向，要看 distinct」——这里正好印证。

---

## 3. `UNANNOTATED_ASSIGNMENT`：按指定路径测了，结论是**别做**

`ir_local_bindings` 写着两件事：一是「类型是声明的不是推断的」这个设计决定，
二是重新考虑它的**指定路径**——「先在 Python 前端接受赋值，量出多少真实函数因此入子集，
拿那个数字决定要不要升 profile」。

这轮把那个数字测了出来，**没有改引擎**：把候选函数复制一份，按 `types.infer` 已经在用的
同一套推断规则给 `x = <expr>` 补上 `x: T = <expr>`，再用真实分析器重跑。

```
因这条码被拒的候选            25
  其中的赋值点               61
      NOT_INFERABLE          53   <- 右侧是调用 / 属性访问 / 推导式
      ANNOTATABLE_FROM_LITERAL 7
      ANNOTATABLE_FROM_OPERANDS 1

补完注解后重跑 25 个候选
      仍然 PYTHON_UNANNOTATED_ASSIGNMENT   24
      转为 PYTHON_UNSUPPORTED_STATEMENT     1
      READY                                 0

净新增 READY 单元：0
```

**收益是 0。** 每一个候选都至少含一个推不出类型的赋值（右侧是函数调用或属性访问），
所以放宽这条码之后它们照样卡在同一处。

结论：**设计决定维持，而且现在它有证据而不只是理由。** 这同时省掉了整个
`typed-pure-function-v1` → `v2` 的升版工作——真正挡路的是
`PYTHON_UNSUPPORTED_EXPRESSION`（调用 / 属性访问，58 例），不是赋值注解。

脚本：`.ai/measurement-2026-08-21/measure_unannotated_assignment_payoff.py`

---

## 4. 覆盖率变化（同一语料，89 文件 / 5,297 语句）

```
schema 语句覆盖率   0.3715  ->  0.4109      (+3.94pp)
进入子集的语句         659  ->     729      (+70)
```

阻塞码分布：

| reason_code | 之前 | 之后 |
| --- | --- | --- |
| `CERTIFIED_DDL_UNSUPPORTED_STATEMENT` | 3942 | 3942 |
| `CERTIFIED_DDL_UNSUPPORTED_CHECK` | 450 | **407** |
| `CERTIFIED_DDL_UNSUPPORTED_TYPE` | 66 | 86 |
| `CERTIFIED_DDL_QUOTED_IDENTIFIER` | 66 | 72 |
| `CERTIFIED_DDL_UNSUPPORTED_STATEMENT_MODIFIER` | 54 | **0** |
| `CERTIFIED_ALTER_UNSUPPORTED_ACTION` | 20 | 20 |
| `CERTIFIED_DDL_UNSUPPORTED_IDENTIFIER_SHAPE` | 19 | 20 |
| `CERTIFIED_DDL_PARSE_FAILED` | 15 | 15 |
| `CERTIFIED_DDL_UNSUPPORTED_DEFAULT` | 6 | 6 |

**TYPE 从 66 涨到 86 不是回归。** 一条语句只按它遇到的**第一个**阻塞码计数；
解开修饰符和 CHECK 之后，原本被它们挡住的语句往前走了一步，撞上了下一个阻塞码。
54 条修饰符里 33 条直接进了子集，21 条撞上下一个。这是「拆掉一堵墙、看见下一堵」，
和 docstring 那次的现象一样。

分语料：

| 语料 | 之前 | 之后 |
| --- | --- | --- |
| elmos-build-cache-migrations | 0.3583 | **0.5333** |
| elmos-p0-sql | 0.3562 | 0.3973 |
| elmos-persistence-migrations | 0.1886 | 0.2347 |
| external-postgres-schemas | 0.8894 | 0.8894 |
| external-mysql-schemas | 0.0000 | 0.0000 |

外部 MySQL 仍是 0：它卡在带引号标识符和整文件解析失败上，这两条都没动。

---

## 5. 零回归

| 引擎 | 基线 | 之后 | FAILED 集合 |
| --- | --- | --- | --- |
| sql-dialect-engine | 167 passed / 0 failed | **245 passed / 0 failed** | 一致（都为空） |
| polyglot-route-engine | 818 passed / 1198 failed+errors | 相同 | **1198 条完全一致** |
| sql-transpiler | 99 passed / 1 failed | 109 passed / 1 failed | 一致 |

新增测试 **32 条**（`test_if_not_exists.py` 16 + `test_check_predicates.py` 16），
其中 CHECK 那组对**全部 12 个有向方言对**逐一断言渲染结果逐字一致。

polyglot 与 transpiler 的源码与上一轮已验证过的完全一致（逐文件 diff 确认），
所以那两份零回归证据继续成立。

---

## 6. 改动清单

```
engines/sql-dialect-engine/src/elmos_sql_dialect/models.py     Table/Index.if_not_exists；
                                                                CheckOperator 加 4 个；CheckLiteral
engines/sql-dialect-engine/src/elmos_sql_dialect/parser.py     收 IF NOT EXISTS；IS/IN/BETWEEN；
                                                                两种 IS NOT NULL 形状；括号解包
engines/sql-dialect-engine/src/elmos_sql_dialect/emitter.py    逐目标 IF NOT EXISTS 失败关闭；
                                                                新谓词渲染
engines/sql-dialect-engine/tests/test_if_not_exists.py         新增 16 条
engines/sql-dialect-engine/tests/test_check_predicates.py      新增 16 条
.ai/measurement-2026-08-21/apply_fixes-2026-08-25.py           FIX 1-4 的可复现 patch 脚本
.ai/measurement-2026-08-21/verify_if_not_exists.py             真库执行验证
.ai/measurement-2026-08-21/measure_unannotated_assignment_payoff.py
.ai/measurement-2026-08-21/*-execution-evidence.json           真库证据
.ai/measurement-2026-08-21/sql-admission-after-fixes.json
```

## 7. 还需要在 Mac 上做的

`verify-on-mac.sh` 把这些收成一条命令。它做四件云端做不了或做不准的事：
polyglot 全量测试（云端那 1198 条失败全是工具链缺失）、sql-dialect 与 transpiler 套件、
重生成 capability probe（docstring 与 CHECK 两处都改变了准入面）、
以及提示如何把准入率测量铺到其余 12 门语言。

## 8. 边界

- 覆盖率是**源侧上界**。`IF NOT EXISTS` 在源侧现在通过，但目标是 Oracle 或 SQL Server 时
  会在发射侧被拒——引擎自己的 caveat 已经写明这一点，这次的改动让这条 caveat 更重要而不是更轻。
- 执行证据只覆盖 PostgreSQL 16.15 与 MySQL 8.0.46。Oracle 与 SQL Server 仍然只有语法级验证，
  这正是本次只收「四方言拼写与含义完全一致」的谓词、而不收逐方言谓词的原因。
- 全部仍为 `NOT_CERTIFIED`，独立验证 `NOT_RUN`。
