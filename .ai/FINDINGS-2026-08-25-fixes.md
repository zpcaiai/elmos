# 2026-08-21 评估里的缺陷——修复记录

日期：2026-08-25
状态：`LOCAL_EXECUTED` / `NOT_CERTIFIED` / 独立验证 `NOT_RUN`
前置：[`FINDINGS-2026-08-21-accuracy-completeness-measurement.md`](FINDINGS-2026-08-21-accuracy-completeness-measurement.md)、
[`FINDINGS-2026-08-21-sql-line-measurement.md`](FINDINGS-2026-08-21-sql-line-measurement.md)

> **本文档更正前一份报告里的一个数字。** 见 §0。

---

## 0. 更正：TPC-H 是 918/924，不是 924/924

`FINDINGS-2026-08-21-sql-line-measurement.md` 写的
「TPC-H 22 条 × 42 路由 = 924/924 全过」**不成立**，正确结果是 **918 / 924（99.35%）**。

复测在四种组合下一致给出 918：

| 源码树 | sqlglot | 结果 |
| --- | --- | --- |
| 08-21 快照 | 30.13.0 | 918 SUPPORTED / 6 UNSUPPORTED |
| 当前源码 | 30.13.0 | 918 / 6 |
| 当前源码 + 本次修复 | 30.13.0 | 918 / 6 |
| 当前源码 + 本次修复 | 30.14.0 | 918 / 6 |

**这 6 格全部是同一条查询、同一个原因**：TPC-H **q13** 用了带列名的表别名

```sql
) as c_orders (c_custkey, c_count)
```

SQLite 不支持它（`Named columns are not supported in table alias`），
所以目标为 `sqlite-3.53.3` 的 6 条路由返回 `BLOCKED / UNSUPPORTED_SEMANTICS`，
`target_sql = None`。**这是正确的失败关闭，不是缺陷**——而且外层查询正是靠这个
别名列表定义 `c_count` 的，静默丢掉它会改变查询语义。

原先那个 924 我无法在任何配置下复现，判定为测量失误，以本次结果为准。
教训与 §3 里那个分类器 bug 同源：**没做负向对照就不该相信一个满分。**

---

## 1. 已修复 · 转写器的失败关闭漏洞

**缺陷**：`transpiler.transpile` 的 `except` 只覆盖
`(ParseError, TokenError, UnsupportedError)`。目标发射路径抛出的任何其他异常
直接穿透到调用方，绕过 Batch 31「target emission raises on unsupported semantics
并失败关闭」的契约。

实例（最小复现）：

```sql
SELECT SUM(a) FILTER (WHERE b) OVER (ORDER BY d ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) FROM t
```

→ `AttributeError: 'Filter' object has no attribute 'sql_name'`
（sqlglot `generator.py` 的 `ordered_sql` 对 `Filter` 节点调 `sql_name()`）。
**上游 sqlglot 缺陷，30.13.0 与 30.14.0 裸调都复现，升版本不解决。**

**修复**（`transpiler.py`）：

```python
    except RuntimeError:
        # 适配器身份完整性违规不是子集边界，必须保持喧闹
        raise
    except Exception as error:  # 刻意的失败关闭兜底
        return _blocked_result(..., code="TARGET_EMISSION_FAULTED", ...)
```

三条设计约束，都有测试守着：

1. **独立的诊断码**。`TARGET_EMISSION_FAULTED` 与 `UNSUPPORTED_SEMANTICS` 分开——
   否则一次引擎崩溃会被统计成一条「已声明的子集边界」，正是 2026-08-21 报告里
   反复强调的那类塌缩。
2. **完整性违规仍然抛出**。`RuntimeError`（注册表与发射对「谁产出了这段 SQL」
   不一致）在广义 `except` 之前重新抛出，不会被洗成一个 BLOCKED 结论。
3. **不泄漏源 SQL**。诊断只记异常**类型名**，不记 message——message 可能带客户
   SQL 片段，而 `rawSourceSqlPersisted` 按契约为 false。

`commercial.py` 的 `assess_commercial` 有同型缺口（只接
`ParseError/TokenError`），一并加了 `SOURCE_PARSE_FAULTED` 兜底。

**验证**：

```
修复前：42 路由中 8 条抛未捕获 AttributeError
修复后：uncaught exceptions = 0
        34 条 SYNTAX_READY / 8 条 BLOCKED，错误码全部 TARGET_EMISSION_FAULTED
        target_sql=None，target_emit=FAILED
```

新增回归测试 10 条（`tests/test_transpiler.py`）：8 条路由参数化 + 不泄漏源 SQL +
完整性违规仍抛出。

---

## 2. 已修复 · 一个 docstring 就让函数出局

**缺陷**：Python docstring 是裸字符串表达式，撞在通用的
`PYTHON_UNSUPPORTED_STATEMENT:Expr` 上，把整个函数一起拒掉。
实测在 20 个真实 PyPI 项目上，**109 个已经过了类型闸门的候选里有 94 个死于此**——
Python 前端最大的一处可避免拒绝。这条拒绝在代码里没有任何理由说明
（对比 `let` 的「类型是声明的不是推断的」是有据的设计决定）。

**修复**：`analyze_python` 剥离首个 docstring，并把文本作为
`Function.documentation` 带进 IR。四条不变量，全部有测试：

| 不变量 | 为什么 | 验证 |
| --- | --- | --- |
| 出现在 `to_mapping` | 源码声明过的东西不被静默丢弃，产物摘要如实反映 | ✅ |
| **不**出现在 `semantic_mapping` | 跨语言等价不该拿 Python `__doc__` 去比一个没有该概念的 Java 方法 | ✅ 有/无 docstring 的 `semantic_mapping` 完全相同 |
| 无 docstring 的函数字节不变 | **此前记录的 IR 摘要仍然成立** | ✅ 键集仍是 `{name,parameters,return_type,body}` |
| 发射目标再分析仍拒绝 docstring | 本引擎的发射器从不产出 docstring，出现即说明目标不是它产的——这正是再分析门禁存在的意义 | ✅ |

边界行为：整个函数体只有 docstring → `PYTHON_FUNCTION_BODY_IS_ONLY_DOCUMENTATION`
（自己的码，失败关闭）；非首位的裸字符串仍拒（它是死代码不是文档）；
`b"bytes"` 仍拒；空 docstring `""` 与「没有 docstring」保持可区分。

**对既有证据零影响**：扫过 `fixtures/` 全部 4 个 Python 夹具，**没有一个带 docstring**，
所以 discovery 判定与路由证据不变（这一条是实测的，不是假定的——
`ir_local_bindings` 记忆里 `let` 前端开关刻意没开，正是因为它会改变 discovery 判定）。

**准入率实测（同一语料，20 个真实项目）**：

| | 覆盖主体 | 候选 | 进语义检查 | READY |
| --- | --- | --- | --- | --- |
| 修复前 | 16,046 | 2,609 | 1,469 | **0** |
| 修复后 | 16,046 | 2,609 | 1,469 | **1** |

语义拒绝码分布随之变化，这才是真正的收获——被 docstring 掩盖的真实阻塞浮出来了：

| 拒绝码 | 修复前 | 修复后 |
| --- | --- | --- |
| `PYTHON_UNSUPPORTED_STATEMENT` | 94 | **21** |
| `PYTHON_UNSUPPORTED_EXPRESSION` | 14 | **58** |
| `PYTHON_UNANNOTATED_ASSIGNMENT_...` | 1 | **25** |
| `PYTHON_FLOORED_MODULO_...` | 0 | 3 |
| `PYTHON_UNSUPPORTED_LOCAL_TYPE` | 0 | 1 |

**要诚实说清楚**：0 → 1。这个修复是**必要但远不充分**的。
它的价值不在那 1 个函数，而在于把 94 条假阻塞换成了 105 条真阻塞——
下一步该修哪里，现在才有依据。

---

## 3. 顺带修掉的一个测量脚本 bug

`measure_transpiler_real.py` 第一版用 try/except 判成败。
但 `transpile` 遇到拒绝时**不抛异常**，而是返回 `state="BLOCKED"` / `target_sql=None`
的结果对象——只看异常等于把每一次拒绝都记成成功。

已改成读返回态，并要求 `target_reparse == PASSED` 且
`metadata.silentFallbackUsed == false`。新版还识别 `TARGET_EMISSION_FAULTED`
并归入 ENGINE_ERROR 而非 UNSUPPORTED。

---

## 4. 零回归验证

方法：同一测试集在**未改动的当前源码**与**改动后源码**上各跑一遍，比对 FAILED 集合。

| 引擎 | 基线 | 修复后 | FAILED 集合 |
| --- | --- | --- | --- |
| polyglot-route-engine | 818 passed / 1173 failed / 25 errors | 818 passed / 1173 failed / 25 errors | **1198 条完全一致** |
| sql-transpiler | 99 passed / 1 failed | 109 passed / 1 failed | 一致，新增 10 条全绿 |

那 1198 条失败与 1 条失败全部是**云端缺少钉死的 macOS 工具链**导致的既有失败
（`RunnerBlockedError: requires the declared darwin-arm64 host` 等），与本次改动无关。

新增测试：polyglot 10 条（`test_python_documentation.py`）+ transpiler 10 条，全绿。

---

## 5. sqlglot 双 pin：查清了，但**没有**动

`sql-transpiler` 钉 30.13.0（`data/profiles-v1.json` + `pyproject.toml`），
`sql-dialect-engine` 钉 30.14.0。实测两者在**云端可测的全部表面**上等价：

| 检验 | 30.13.0 | 30.14.0 |
| --- | --- | --- |
| 合成资格套件 | 248/248 语法、44/44 失败关闭、42/42 路由 | 完全相同 |
| 单元测试 | 109 passed / 1 failed(darwin gate) | 完全相同 |
| TPC-H × 42 路由 | 918/924 | 918/924 |

**但我没有改这个 pin**，理由是：`runner.py` 的执行级矩阵（真 PostgreSQL 17.5 /
SQLite / DuckDB，2000 行确定性夹具，行值/类型/基数/回滚等价）**只能在 darwin-arm64 上跑**，
云端跑不了。在没跑过运行时矩阵的情况下改一个证据绑定的 pin，正是这个仓库不允许的操作。

**建议的收敛步骤（在你 Mac 上）**：

```bash
# 1. 改两处
#    engines/database-data-engine/sql-transpiler/pyproject.toml      sqlglot==30.14.0
#    .../src/elmos_sql_transpiler/data/profiles-v1.json   parser.version 30.14.0
# 2. 资格套件 + 单元测试
uv --directory engines/database-data-engine/sql-transpiler run --locked pytest
# 3. 执行级矩阵（只有这一步云端做不了）
uv --directory engines/database-data-engine/sql-transpiler run --locked \
    elmos-sql-transpiler qualify corpus/*/queries.json
# 4. 通过后重录 parserVersion 相关证据
```

---

## 6. 没有修的部分——以及为什么不算 bug

2026-08-21 报告里其余的「问题」经查是**已声明的子集边界或 profile 决定**，
不是缺陷。逐条给出实测收益，供决定是否投入：

| 项 | 性质 | 实测收益 | 为什么这次不动 |
| --- | --- | --- | --- |
| `PYTHON_UNANNOTATED_ASSIGNMENT`（25 例） | **有据的设计决定** | 最多 25 个候选 | `ir_local_bindings` 明确记着「类型是声明的不是推断的」，并说明放宽前端很可能意味着 `typed-pure-function-v1` → `v2`。单方面改会违反一个写明理由的决定 |
| 规范类型只有 `int/float/bool/str` | profile 边界 | 683 个参数注解已标但类型在四类之外（`bytes` 61、`Path` 47、`str\|None` 35…） | 每加一个类型都要在 13 门语言上定义等价语义 + 重跑证据。是路线图不是补丁 |
| `PYTHON_UNSUPPORTED_EXPRESSION`（58 例，调用/属性访问） | profile 边界 | 58 个候选 | 跨函数调用语义未闭合，README 已显式列为不支持 |
| 生成线 6/8 语言单实体 | 发射器能力 | — | `*_PRODUCTION_PROFILE_SINGLE_ENTITY_ONLY` 是**显式拒绝**而不是静默降级，行为正确；补齐是六个发射器的实现工作 |
| 生产 profile 关系 4 选 1 | 已声明约束 | — | `many-to-many` 需要中间表建模 + 迁移生成，是特性 |
| certified DDL 不收 `IF NOT EXISTS`（54 例 / 4 个不同原因） | **有语义分歧** | 54 条语句 | Postgres/MySQL/SQLite/DuckDB 支持，**Oracle 与 SQL Server 不支持**。加它必须给这两个目标定义失败关闭行为——是 profile 决定不是补丁。**四条里投入产出比最高的一条**，建议优先 |
| `CERTIFIED_DDL_QUOTED_IDENTIFIER`（66 例 / **63 个不同原因**） | profile 边界 | 66 条 | 63 个不同原因说明是 osTicket 每张表都带引号这一种写法，引擎自己的 caveat 就是「按次数排会指错方向」 |
| 15/89 个 SQL 文件整文件解析失败 | **上游 sqlglot 能力** | 992 KB 源码 | pagila/sakila/chinook 等公开示例库，钉死的 sqlglot 直接 ParseError。要么等上游，要么换前端——不是本仓库能补的 |

---

## 7. 改动清单

```
engines/database-data-engine/sql-transpiler/src/elmos_sql_transpiler/transpiler.py   失败关闭兜底
engines/database-data-engine/sql-transpiler/src/elmos_sql_transpiler/commercial.py   同型兜底
engines/database-data-engine/sql-transpiler/tests/test_transpiler.py                 +10 条回归测试
engines/polyglot-route-engine/src/elmos_polyglot_route/models.py                     Function.documentation
engines/polyglot-route-engine/src/elmos_polyglot_route/python_analyzer.py            剥离并保留 docstring
engines/polyglot-route-engine/tests/test_python_documentation.py                     新增，10 条
.ai/measurement-2026-08-21/apply_fixes-2026-08-25.py                                 可复现的 patch 脚本
.ai/measurement-2026-08-21/measure_transpiler_real.py                                判定改读返回态
```

`apply_fixes-2026-08-25.py` 每处替换前都 `assert` 精确匹配数——这个仓库有多个会话
并行写入，一个匹配不到的 `str.replace` 看起来和成功一模一样。

## 8. 还需要在 Mac 上做的

1. `uv --directory engines/polyglot-route-engine run --locked pytest` —— 云端 1198 条
   失败全是工具链缺失，Mac 上才能看到真实结果。
2. `make capability-probe-json` 重生成能力矩阵（docstring 修复改变了 Python 前端的准入面）。
3. 若要收敛 sqlglot pin，按 §5 的四步走。
4. 用 `tools/measure_repository_admission.py` 把准入率测量铺到其余 12 门语言。
