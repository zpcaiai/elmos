# 17 个全量失败的归因：0 条来自 `let`

日期 2026-08-19。触发：`let` 落盘后跑全量，17 个失败。
问题是「哪些是我造成的」。答案是 **0 条**，但这个结论是查出来的，不是假定的。

## 无法在容器/设备 VM 里跑

`engines/polyglot-route-engine/.venv/bin/python3` 指向 Mac 的解释器；device VM 是
aarch64-linux 且**无网**，`uv` 想下载 CPython 直接失败。**这一层只能读调用链，
执行必须在你的 Mac 上。** 下面每条结论都标了「读出来的」还是「待你跑一遍确认的」。

## 三组失败，三个不同的原因

### A. 15 × `test_javascript_node.py` —— javascript 弃用漏掉了一个闸门（**已修**）

全部炸在 `native.py::analyze` 的同一行：

```
RouteError: EMITTED_TARGET_REANALYSIS_UNSUPPORTED:javascript
```

闸门原文只看**路由成员资格**：

```python
if emitted_target and language not in ROUTED_LANGUAGES and language not in NATIVE_RELIFTABLE_LANGUAGES:
```

`ROUTED_LANGUAGES = COMPLETE_MATRIX_LANGUAGES = SUPPORTED_LANGUAGES`，而并行线程这次把
javascript 从 `SUPPORTED_LANGUAGES` 移到了 `DEPRECATED_LANGUAGES`。于是 javascript
一夜之间从「能 relift」变成「每次调用都抛」。

**这跟 `let` 无关是可判定的**：该闸门只判语言身份，不看任何语句种类；`let` 的改动
在 `models.py` 里只碰 `Statement`，没有增删任何语言元组（见 `git diff models.py`）。

弃用注释自己写着机器还在：「Kept in the type so the Node.js analyzer, emitter,
assembly and evidence machinery that still ships in this engine remains typed.」
`models.py:644` 也已经用了正确的写法：`not in SUPPORTED_LANGUAGES and not in DEPRECATED_LANGUAGES`。
**只有这一行漏了。** 修法就是补齐同一个判据：

```python
if (
    emitted_target
    and language not in ROUTED_LANGUAGES
    and language not in DEPRECATED_LANGUAGES
    and language not in NATIVE_RELIFTABLE_LANGUAGES
):
```

这个闸门**此前一条测试都没有**（全仓 grep `EMITTED_TARGET_REANALYSIS_UNSUPPORTED`
只有抛出点自己）。这正是它能悄悄改变一整门语言的能力而没有一条断言指名原因的
原因——15 条测试各自红在自己的主题上，没有一条指向这一行。新增
`tests/test_emitted_target_reanalysis_gate.py`：pending 语言必须被拒（按名字断言），
deprecated 语言**不许**在这个闸门上失败，`NATIVE_RELIFTABLE_LANGUAGES` 与
`PENDING_ANALYZER_LANGUAGES` 必须不相交。

### B. 1 × `test_identifier_hygiene.py::…deterministic_and_round_trips` —— kotlin 进了 `_DIALECT`（**已修**）

`assert 12 == 11`。该断言的**本意是「每个方言的 policy 摘要互不相同」**，却被写成了
硬编码条数，于是每落一门语言就要改一次测试——而恰恰是落语言的时候，碰撞才最该被抓住。
改成 `assert len(policy_digests) == len(hygiene._DIALECT)`，语义不变，不再随语言数漂移。

`let` 没有新增任何方言。

### C. 1 × `test_javascript_esm_descriptor.py` —— `PIPELINE_NO_VERIFIED_UNITS`（**已知遗留，待复跑**）

记忆 `polyglot_pre_existing_failures.md`（08-18）已把它记为「仍未解释」的遗留失败，
早于 `let`。

排除了一条假线索：我一度怀疑 `project_graph.py:302/1583` 的
`not in SUPPORTED_LANGUAGES` 会因弃用而拒掉 javascript。**不成立**——
`project_graph.py:74` 有自己的一份本地 `SUPPORTED_LANGUAGES` 元组，里面 javascript 还在，
而且该文件相对 HEAD 未被修改。（顺带记一笔：这份本地元组**没有** kotlin/react/flutter，
是 13 语言扩展留下的另一个缺口，属并行线程的地界。）

A 的修复有可能连带修好它（若 `PIPELINE_NO_VERIFIED_UNITS` 是 relift 抛错被吞掉的结果）。
**待复跑确认**，不预设。

## `let` 的非 let 路径为何是恒等的（读调用链的部分）

四个被改的模块里，除去 `kind == "let"` / `role == "local"` 分支，只有三处改到了既有路径：

1. `types.py::_check_statements` 给 if 分支传 `dict(environment)` 而不是原字典。
   没有 `let` 时**没有任何东西写 environment**，拷贝即恒等。
2. `emitter.py::_statements` 同上。
3. `identifier_hygiene.py::_rename_statements` 同上（`names` 同理）。

外加两处纯重构：`_generated_candidate_name` 拆成 if/else 后，`role == "parameter"`
仍产出 `elmos_p{ordinal:03d}_{digest}`，逐字节相同；`role not in {...}` 放宽只是放宽。
`_local_bindings()` 无条件调用，但无 `let` 时两侧长度均为 0，直接返回空元组。

唯一**有意**改变既有发射的是 Go 的 `} else {`（`}` 与 `else` 分行是 Go 语法错误），
Go-only，且 17 个失败里没有一条是 go。

## 结论

| 组 | 条数 | 归属 | 状态 |
|---|---:|---|---|
| A javascript relift 闸门 | 15 | 并行线程的 javascript 弃用 | 已修 + 补测试 |
| B `_DIALECT` 条数硬编码 | 1 | 并行线程的 kotlin 落地 | 已修 |
| C esm descriptor | 1 | 08-18 起的遗留 | 待复跑 |
| **`let`** | **0** | — | — |

## 待你在 Mac 上执行

```
cd ~/DevProjects/AIProjects/elmos
uv run --directory engines/polyglot-route-engine --locked python -m pytest -q \
  tests/test_javascript_node.py \
  tests/test_javascript_esm_descriptor.py \
  tests/test_identifier_hygiene.py \
  tests/test_emitted_target_reanalysis_gate.py \
  tests/test_local_bindings.py
```

预期：A、B 组转绿，新增的闸门测试绿；C 组要么随 A 一起绿（说明它一直就是同一个原因），
要么仍红（说明确实是另一件事，那就按记忆里说的单跑它、看保留下来的 tmp 目录）。

---

# 复跑结果与一处自我更正（同日）

`uv run --directory engines/polyglot-route-engine --locked python -m pytest -q tests/test_javascript_node.py tests/test_javascript_esm_descriptor.py tests/test_identifier_hygiene.py tests/test_emitted_target_reanalysis_gate.py tests/test_local_bindings.py`

- **A 组 15 条：全绿。** 归因与修复成立。
- **B 组 1 条：绿。**
- **C 组 `test_javascript_esm_descriptor`：仍红**，`PIPELINE_NO_VERIFIED_UNITS` 抛在
  `pipeline.py:851`（`passed < 1`）。**这条确认与 A 组无关**，是独立的遗留问题——
  A 组修好后它没跟着好，正好排除了「同一个原因」的假设。
- **我新写的闸门测试：3 条红。** 前提写错了。

## 自我更正：我把闸门的边界又假定了一次

我断言 kotlin/react/flutter 会被 `EMITTED_TARGET_REANALYSIS_UNSUPPORTED` 拒掉。**不会。**
它们在 `SUPPORTED_LANGUAGES` 里，因而在 `ROUTED_LANGUAGES` 里，闸门根本不看它们；
它们一路走到 `exact_toolchain` 才死：

```
EXACT_TOOLCHAIN_KOTLIN_NOT_PINNED:run tools/pin_kotlin_toolchain.py on the pinning host
EXACT_TOOLCHAIN_UNREGISTERED:react
EXACT_TOOLCHAIN_UNREGISTERED:flutter
```

这正是我自己反复记过的那条毛病——**中间层的一个拒绝码不是系统的边界**——这次犯在我
自己新写的测试上。测试红了是它在干活：它把我的假定和真实行为的差量指出来了。

### 修正一：kotlin 的错误信息在骗人（真缺陷）

`EXACT_TOOLCHAIN_KOTLIN_NOT_PINNED` 指名了一个修法（「去 pinning host 上跑
`tools/pin_kotlin_toolchain.py`」）。照做会得到一个 pin 好的工具链和**一模一样的
「仍然不能 lift」**——缺的是分析器，不是 pin。而 `SemanticIR.from_mapping`
（`models.py:650`）早就为这个状态起好了名字：`SOURCE_ANALYZER_NOT_IMPLEMENTED`。

在 `analyze()` 入口补上，放在 `exact_toolchain` 之前：

```python
if language in PENDING_ANALYZER_LANGUAGES:
    raise RouteError(f"SOURCE_ANALYZER_NOT_IMPLEMENTED:{language}")
```

kotlin 的工具链仍从**目标**路径可达，那条路上 pin 确实是真前置。

顺带：能力探针的口径因此变好了——kotlin 从
`NOT_PROBED:EXACT_TOOLCHAIN_KOTLIN_NOT_PINNED`（「换台机器再跑」，误导）变成
`REJECTED:SOURCE_ANALYZER_NOT_IMPLEMENTED`（引擎属性，与机器无关）。

### 修正二：relift 闸门补完之后是**结构性死代码**

`ROUTED_LANGUAGES ∪ DEPRECATED_LANGUAGES` 覆盖了 `Language` 字面量的**全部**成员，
所以那个闸门今天永远不会触发。我选择**保留并把这件事写成断言**，而不是删掉：

```python
assert set(get_args(Language)) == set(ROUTED_LANGUAGES) | set(DEPRECATED_LANGUAGES)
```

它是一个兜底：唯一能让它活过来的排布，是有人往 `Language` 里加了一门语言却没把它
放进任一集合——而那种情况下，控制流会掉进一条没有对应分支的 dispatch 链，
最后 `return value` 时 `value` 未绑定。断言失败的含义是「该给新语言安个家」，
不是「把这个检查删了」。

### 测试改成了什么

- pending 语言 × `emitted_target ∈ {False, True}` → 断言 `SOURCE_ANALYZER_NOT_IMPLEMENTED:{lang}`
- deprecated 语言 → 断言**不**在 relift 闸门上失败
- relift 闸门的不可达性 → 上面那条 `get_args(Language)` 断言
- `NATIVE_RELIFTABLE_LANGUAGES ∩ PENDING_ANALYZER_LANGUAGES == ∅`

## 待跑

```
cd ~/DevProjects/AIProjects/elmos
uv run --directory engines/polyglot-route-engine --locked python -m pytest -q \
  tests/test_emitted_target_reanalysis_gate.py tests/test_language_set.py \
  tests/test_kotlin_target.py tests/test_capability_probe.py \
  tests/test_repository_pipeline_language_matrix.py
```

剩下的独立问题：`test_javascript_esm_descriptor` 的 `PIPELINE_NO_VERIFIED_UNITS`。
按记忆里的办法单跑它，`tmp_path_retention_policy = "failed"` 会保留 tmp 目录，
读里面的 `batch/` 与 `repository-discovery-report.json` 看是哪一单元没过。

---

# 第二轮复跑：闸门测试转绿，kotlin 目标侧查出两处真缺陷

`test_emitted_target_reanalysis_gate.py`、`test_language_set.py` 全绿——
`SOURCE_ANALYZER_NOT_IMPLEMENTED` 与不可达性断言都成立。
新的 4 条红全在 `tests/test_kotlin_target.py`：并行线程在我上次适配之后又改了 kotlin 发射器。
逐条判过，**3 条是我的测试过度指定，1 条是发射器真错**。

## 我的测试错了（3 条，已改测试）

| 我断言的 | 发射器实际 | 谁对 |
|---|---|---|
| `return Long.MAX_VALUE` | `return 9223372036854775807L` | **发射器** |
| `elmosCheckedAdd(left, right)` | `Math.addExact(left, right)` | **发射器** |
| `elmosNonZeroDouble(right)` | `elmosNonZero(right)` | **发射器** |

- `9223372036854775807L` 是合法的 Long 字面量，最大值不需要常量；**最小值需要**——
  Kotlin 没有负字面量，`-9223372036854775808L` 是「一元负号作用在超出 Long 范围一位的
  量级上」，编译器直接拒绝。这个不对称正是关键，我上一版把两端写成一样，是**对语言的
  事实判断错了**。
- `java.lang.Math` 在 Kotlin/JVM 是默认导入，`Math.addExact` 自己就抛。`+ - *` 不需要
  我们的 helper，只有 `/ %` 需要（`Math` 没有 checked 除法）。与 Java 目标同构。
- helper 叫 `elmosNonZero`，与 Java 同名。

## 发射器错了（1 条，已修发射器）

`test_integer_to_number_widening_is_explicit` **第一版就是对的**：

```kotlin
fun widen(v: Long): Double { return v }   // 不编译：Kotlin 没有隐式数值加宽
```

返回点的 integer→number 加宽只对 `rust` 和 `swift` 做了，**kotlin 漏了**
（`emitter.py:1250` 的 `language in {"rust", "swift"}`）。已加：

```python
elif language == "kotlin":
    context.normalization_rules.add("kotlin.return.integer-to-number")
    value = f"({value}).toDouble()"
```

加括号是因为 `.` 比一元负号结合更紧，裸写 `-5L.toDouble()` 会解析成 `-(5L.toDouble())`。

**为什么它能活到现在**：kotlinc 未纳入精确工具链 ⟹ 发射出来的文件从不被编译 ⟹
只有对发射文本的断言能看见它。这是「没有可执行证据的目标语言」的典型失效模式。

## 顺手查出的第二处：标识符策略与发射器名字对不上

`_FORBIDDEN["kotlin"]` 保留了 `elmosNonZeroDouble`（发射器从不写），却**没有保留
`elmosNonZero`（发射器每次浮点除法都写）**，也没有 `Math`。Kotlin 的 migrated 函数与
emitted helper 共用一个顶层命名空间——一个叫 `elmosNonZero` 的源函数会是重复声明错误，
而标识符规划器**整个存在的意义就是让这不可能发生**。Java 的列表是对的，照它补齐。

### 这次不靠人盯：新增跨语言不变量

`tests/test_emitted_names_are_reserved.py` —— 对每门语言，把
`emitter._CHECKED_INTEGER_CALL` 和 `emitter._FLOAT_NON_ZERO_GUARD` 里能发射出去的调用名
逐个比对 `_FORBIDDEN`（限定名 `Migrated.elmosCheckedDiv` 只要 `Migrated` 被占即可）。
外加 `set(_FORBIDDEN) == set(_DIALECT) == set(_RESERVED)`——三张表同键索引、同一次规划里
一起读，缺一个会在规划时 `KeyError` 而不是 fail-closed。

**保留一个不再发射的名字，代价是一次多余改名；漏保留一个正在发射的名字，代价是构建失败。**
不变量按后者的方向定。

## 待跑

```
cd ~/DevProjects/AIProjects/elmos
uv run --directory engines/polyglot-route-engine --locked python -m pytest -q \
  tests/test_kotlin_target.py tests/test_emitted_names_are_reserved.py \
  tests/test_identifier_hygiene.py tests/test_capability_probe.py \
  tests/test_repository_pipeline_language_matrix.py
```
