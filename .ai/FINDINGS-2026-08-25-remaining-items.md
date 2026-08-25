# 剩余四项：做完两项，并更正其中一项的判断

日期：2026-08-25
状态：`LOCAL_EXECUTED` / `NOT_CERTIFIED` / 独立验证 `NOT_RUN`
承接：[`FINDINGS-2026-08-25-subset-widening.md`](FINDINGS-2026-08-25-subset-widening.md)

---

## 0. 结果

| 上轮结论 | 这轮 | 结果 |
| --- | --- | --- |
| 15/89 文件 ParseError — **上游能力，仓库补不了** | **判断错了** | 每个文件都是**一个**构造害的；扫描器才是丢掉其余的那一环。已修，750 KB 源码回到测量里 |
| 关系 4 选 1 — 特性工作 | **判断太粗** | 3 个可达，已实现并真库验证；只有 many-to-many 是特性工作 |
| 6/8 语言单实体 | 特性工作 | 确认属实，给出逐目标的行数与阻塞点 |
| 规范类型只有四类 | 特性工作 | 确认属实 |
| sqlglot 双 pin | 需 Mac | 未变，步骤已交付 |

**并且这一轮把上轮的一个数字改小了**：SQL schema 覆盖率不是 41.09%，是 **38.74%**——
上轮那个数被 15 个「整文件算 1 条语句」的文件抬高了。见 §1.3。

---

## 1. 更正 · 15 个文件的整文件 ParseError 是**我们自己的**问题

### 1.1 上轮我断错了

上轮我写「上游 sqlglot 能力，本仓库补不了」，但**没看过失败位置的那一行**。
这正是 `backlog_premise_discipline` 记的那种错法：只读一层就下断言。看了之后：

| 文件 | 丢掉 | 真正的原因 |
| --- | --- | --- |
| chinook | **586 KB / 15,876 行** | `\c chinook;` —— 一条 **psql 客户端指令**，根本不是 SQL |
| pagila | 87 KB / 3,035 行 | `CREATE FUNCTION f(timestamp with time zone)` 一句 |
| sakila (pg) | 49 KB / 1,711 行 | 同一句式 |
| sakila (mysql) | 22 KB / 644 行 | `password VARCHAR(40) BINARY` 一个列 |
| employees | 4 KB / 127 行 | `DROP TABLE IF EXISTS a, b, c` 一句 |

**每个文件都是被一个构造整个丢掉的。** 上游确实读不了那几句，
但「因此丢掉整个文件」是 `scan_repository` 的行为，不是上游的。

### 1.2 修法

`scan_repository` 用真解析器切分是**对的**，它的注释也写明了理由：按 `;` 切会数错
字符串字面量、`$$` 包体、`BEGIN ... END` 里的分号。所以真解析器仍是主路径，
**只在它拒绝整个文件时**回退到一个词法切分器：

`statement_splitter.split_statements` 跟踪所有**合法包含分号**的东西——
单引号串（含 `''` 转义）、双引号与反引号标识符、`$$` / `$tag$` 包体、
行注释、块注释——只在顶层 `;` 上切，并记录每条语句的起始行号。
10 条切分用例逐一断言（分号在串里、`''` 转义、带标签的美元引用、注释、反引号…）。

回退后每条语句**独立交给同一个解析器**，能读的照常判定，读不了的单独报告并带行号。
psql 客户端指令另给一个码 `CERTIFIED_DDL_CLIENT_DIRECTIVE`——它不是 SQL，
把它算成解析失败等于把客户端构造赖到方言语法上。

### 1.3 代价：一个被抬高的数字被改回来了

五个文件从 5 条 finding 变成 **769 条真实语句**，其中 125 条进入子集。
但整体覆盖率**下降**了：

| | 整文件解析失败 | schema 语句 | 进入子集 | 覆盖率 |
| --- | --- | --- | --- | --- |
| 原始 | 15 | 1774 | 659 | 37.15% |
| 子集扩展后（上轮报的） | 15 | 1774 | 729 | **41.09%** |
| 再加解析恢复（真实值） | 15 | **2344** | **908** | **38.74%** |

**上轮的 41.09% 被抬高了**，因为最难的 15 个文件在分母里只占 15。
真实值是 **38.74%**，分母大了 32%，进入子集的语句从 659 涨到 **908（+37.8%）**。

这个修复让数字变难看、让测量变正确。两者只能选一个的时候选后者。

### 1.4 现在真正读不了的有多少

```
CERTIFIED_DDL_PARSE_FAILED   15 条（整文件）  ->  42 条（单语句）
```

**42 条**，不是 15 个文件。这 42 条才是真正的上游能力边界，
且都带行号可以直接定位。另外新暴露一个阻塞码：
`CERTIFIED_DDL_QUALIFIED_TABLE_NAME` **160 条**——pg_dump 输出的 `public.` 前缀。
这是下一个投入产出比最高的候选（模式限定名在四个方言里的含义确实有分歧，
所以它是 profile 决定，不是补丁）。

---

## 2. 关系：4 选 1 → 4 选 3，真库验证

### 2.1 上轮的判断太粗

上轮把「关系 4 选 1」整个划进特性工作。看了实现才发现：一个关系在这里就是
**一侧的外键列指向另一侧的 `id`**。按这个定义：

- **one-to-one** ＝ 同一个外键 **加 UNIQUE(tenant_id, fk)**。
  「每个父行至多一个子行」约束的是同一列，不是另一种形状。
- **one-to-many** ＝ **同一个关系从另一端声明**。`A one-to-many B` 与
  `B many-to-one A` 描述的是同一个外键，只是写法不同。
- **many-to-many** ＝ 才是真的特性工作：需要一张不属于任何实体的连接表、
  自己的复合主键、两个外键、以及关联端点。

### 2.2 实现

`RelationSpec.canonical()` 把每个关系摆成「外键在 source、指向 target.id」的朝向；
`one-to-many` 是唯一会翻转的那个。生成侧一律读 `canonical_relations`，
所以四个发射点保持**一条代码路径**；文档侧仍读 `relations`，
因为 ER 图必须画出作者写的那个 kind。

**两处门必须同改。** `intake.create_draft` 也有一份 `!= "many-to-one"` 的判断，
它会生成待答问题从而阻断审批——只改 models 层的话新写法根本走不到。
两处现在用同一条规则（同样的 canonical 朝向，包括**环检测**：
否则一个用 one-to-many 写出来的环会溜过去）。

### 2.3 真库执行验证（PostgreSQL 16.15）

不只是渲染出 DDL，而是把生成的迁移真跑起来，再验证关系语义：

```
关系          迁移执行   同一父行的第二个子行        悬空外键
many-to-one   PASSED    ACCEPTED                   REFUSED
one-to-one    PASSED    REFUSED (UniqueViolation)  REFUSED   <- 这才叫 one-to-one
one-to-many   PASSED    ACCEPTED                   REFUSED
```

`one-to-many` 生成的外键与 `many-to-one` **逐字相同**（都在 `orders` 上），
证明朝向归一是对的。

证据：`.ai/measurement-2026-08-21/relation-execution-evidence.json`

---

## 3. 确认属实的两项，附可执行的分解

### 3.1 6/8 语言单实体 —— 确实是特性工作

不是一个可以翻的开关。六个发射器每个都在 render 函数里绑
`entity = request.entities[0]`，然后按单实体生成模型/仓储/路由/集成测试：

| 目标 | 行数 | `entities[0]` 绑定处 | 多实体循环 |
| --- | --- | --- | --- |
| rust | 1108 | 有 | 1（仅错误信息） |
| php | 1038 | 有 | 1 |
| go | 872 | 2 处 | 1 |
| dotnet | 814 | 3 处 | 1 |
| kotlin | 745 | 有 | 1 |
| typescript | 670 | 有 | 1 |
| *java（已多实体）* | *1171* | — | *3* |
| *python（已多实体）* | *1318* | — | *4* |

每个目标要改的是同样五件事：DTO/模型、仓储、路由注册、集成测试、文件名映射。
java 与 python 已经是可抄的样板。**建议顺序**：go → dotnet → typescript
（结构最接近 java），再 kotlin → php → rust。
每个目标改完都能用现成的 `run_production_matrix.py` 单独验证。

### 3.2 规范类型只有四类 —— 确实是特性工作

`int/float/bool/str`。实测 683 个参数注解已经标了类型但落在四类之外
（`bytes` 61、`Path` 47、`str | None` 35、`t.Any` 31…）。
每加一个类型不是加一行枚举，而是要在 **13 门语言**上定义等价语义
（`bytes` 在 Java 是 `byte[]`、在 Go 是 `[]byte`、在 Rust 是 `Vec<u8>`，
可变性与拷贝语义都不同），并重跑全部路由证据。
按收益排应当从 `bytes` 与可空（`str | None`）开始——但这是路线图不是补丁。

---

## 4. 零回归

| 引擎 | 基线 | 之后 | FAILED 集合 |
| --- | --- | --- | --- |
| sql-dialect-engine | 167 passed / 0 failed | **261 passed / 0 failed** | 一致（都为空） |
| project-synthesis-engine | 135 collected / 43 failed | **148 collected / 43 failed** | **完全一致** |
| polyglot-route-engine | 818 passed / 1198 failed | 未变（源码逐文件相同） | 1198 条一致 |
| sql-transpiler | 109 passed / 1 failed | 未变 | 一致 |

project-synthesis 与 sql-dialect 的既有失败都是云端缺工具链的既有失败，与改动无关。

本轮新增测试 **29 条**：`test_scan_recovery.py` 16 条（含 10 条切分器用例）、
`test_production_relations.py` 13 条。累计本次修复回合新增 **81 条**。

---

## 5. 改动清单

```
engines/sql-dialect-engine/src/elmos_sql_dialect/scan.py                 整文件失败改为逐语句恢复
engines/sql-dialect-engine/src/elmos_sql_dialect/statement_splitter.py   新增，引号/美元引用/注释感知
engines/sql-dialect-engine/tests/test_scan_recovery.py                   新增 16 条
engines/project-synthesis-engine/src/elmos_project_synthesis/models.py             canonical()/enforces_uniqueness
engines/project-synthesis-engine/src/elmos_project_synthesis/intake.py             两处门用同一条规则
engines/project-synthesis-engine/src/elmos_project_synthesis/production_profile.py one-to-one 的 UNIQUE
engines/project-synthesis-engine/src/elmos_project_synthesis/java_production_target.py    读 canonical
engines/project-synthesis-engine/src/elmos_project_synthesis/python_production_target.py  读 canonical
engines/project-synthesis-engine/tests/test_production_relations.py      新增 13 条
.ai/measurement-2026-08-21/apply_fix6_sites.py / apply_fix6_intake.py    可复现 patch
.ai/measurement-2026-08-21/relation-execution-evidence.json              真库关系语义证据
.ai/measurement-2026-08-21/sql-admission-final.json                      更正后的覆盖率
```

## 6. 还剩什么

| 项 | 性质 | 下一步 |
| --- | --- | --- |
| 6/8 语言多实体 | 特性 | 按 §3.1 的顺序逐目标改，每个用 production matrix 验证 |
| 规范类型扩展 | 特性 | 从 `bytes` 与可空开始，每个类型先定义 13 语言等价语义 |
| many-to-many | 特性 | 连接表 + 关联端点 |
| `QUALIFIED_TABLE_NAME`（160 条） | profile 决定 | 模式限定名在四方言含义有分歧，需先定失败关闭规则 |
| 42 条真正读不了的语句 | 上游 sqlglot | 现在带行号，可逐条上报或加前置规避 |
| sqlglot 双 pin | 需 Mac | 步骤见前一份报告 §5 |

## 7. 边界

- 覆盖率仍是**源侧上界**：解析恢复让分母更诚实，没有改变「目标侧发射仍可能拒绝」这一点。
- 关系的执行证据只覆盖**迁移与约束语义**，不包括跑起来的生成应用——那需要钉死的工具链。
- 全部仍为 `NOT_CERTIFIED`，独立验证 `NOT_RUN`。
