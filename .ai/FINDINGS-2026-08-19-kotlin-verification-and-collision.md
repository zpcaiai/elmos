# Findings — 2026-08-19 · Kotlin 发射侧：撞车、验证与两个发现

> 追加文件，不写入 `HANDOFF.md`。本文件不含任何认证声明。

## 0. 先说撞车

10:00–10:20 之间，**两个会话同时实现了 Kotlin 发射侧**。
我从 backlog `#2a` 出发写了一版；另一会话同期写了一版并先落盘。
发现时我的版本已完成并通过 kotlinc 真编译 + 与 Java 的 17/17 行为差分。

**处置：不提交我的版本。** 他们的设计在一处明显更好（见 §2），
我改为用已装好的 kotlinc 去**验证他们的实现**，只提交两点实测出来的增量。

这次重复劳动是 `.ai/CODE_LEVEL_BACKLOG.md` 没有「认领」机制导致的。
建议：动手前在对应条目下写一行 `IN-PROGRESS by <session> @ <time>`。

## 1. 他们的实现踩过的四个陷阱：3 / 4

我先列出 Kotlin 相对 Java 会**静默出错**的点，再逐个对照他们的实现：

| 陷阱 | 后果 | 他们的实现 |
|---|---|---|
| `Int` 不隐式加宽到 `Long` | `Math.addExact(a, 90)` 找不到 `(Long, Int)` 重载，**编译失败** | ✅ 无条件加 `L` 后缀 |
| `Long.MIN_VALUE` 无负字面量 | `-9223372036854775808L` 是对越界字面量取负，**编译失败** | ✅ 发 `Long.MIN_VALUE` |
| `$` 开启字符串模板 | `"cost is $amount"` 变成对 `amount` 的引用；名字恰好存在时**静默返回别的字符串** | ✅ 转义为 `\$` |
| `kotlin.*` 默认导入占用顶层函数名 | 同名函数遮蔽 stdlib | ⚠ 见 §2 |

## 2. 唯一的缺口：`maxOf` / `minOf` 签名完全撞上

他们用**定点禁用表**而不是像 Java/C#/Swift 那样一刀切改名——
这个设计比我的更好，保住了可读的函数名。但表里只放了自家 helper 用到的
`error`/`require`/`check`，漏掉了签名可被精确匹配的那一类。

kotlinc 2.1.21 实测：

```kotlin
fun maxOf(a: Long, b: Long): Long { return a / b }   // 迁移函数
// 同模块别处：
maxOf(7L, 2L)                       // → 3   （拿到迁移函数）
kotlin.comparisons.maxOf(7L, 2L)    // → 7   （stdlib 只剩全限定名可达）
```

**编译通过，无任何诊断。** `maxOf`/`minOf` 是 `kotlin.*` 顶层函数里
唯一在规范类型上签名精确相同的（`(Long,Long):Long`、`(Double,Double):Double`）。

已加入 `_FORBIDDEN["kotlin"]`。**只加这两个**：其余默认导入面
（`run`/`let`/`repeat`/`apply`…）都收 lambda，重载解析能区分，
改名只会白白牺牲可读性。`repeat`、`clamp`、`grade` 实测仍保留原名。

## 3. 差分跑出的第二个发现：**Java 和 C# 才是异类**

同一份 IR 发射到 Kotlin 与 Java，编译运行 18 项对照：

- **值 18/18 全部一致**（含 `MIN_VALUE/-1`、除零、取余、`Long.MIN_VALUE` 字面量、
  `$` 字符串、浮点除零、else-if 链）
- **溢出异常消息 3 项不同**：Kotlin `ELMOS_INTEGER_OVERFLOW` vs Java `long overflow`

逐目标核对后，方向和直觉相反：

| 发规范消息 `ELMOS_INTEGER_OVERFLOW` | 泄漏运行时自带消息 |
|---|---|
| kotlin, go, rust, cpp, php, python, objc | **java（`Math.addExact`）、csharp（`checked()`）** |

**Kotlin 是对的，Java 和 C# 是异类。** 它们借用语言内建的溢出检查，
因而把 JDK/CLR 自己的消息泄漏到了可观察行为里。

这条要不要修，取决于**行为 harness 是否比对异常消息**。
如果比对，那么任意源到 java 与到 kotlin 的差分会在所有溢出用例上分歧——
而原因不在 Kotlin。若不比对，则这只是不一致，不是缺陷。
**这是既有的 Java/C# 行为且已有证据背书，不应由本次单方面改动**，
列为待你裁决项。

## 4. 交付

- `identifier_hygiene.py`：`_FORBIDDEN["kotlin"]` 增加 `maxOf minOf`（含实测依据注释）
- `tests/test_kotlin_target.py`：13 条，纯 Python 任何机器可跑，覆盖上述四个陷阱 +
  「该改名的改名、不该改的保留」两组参数化

**你需要在 Mac 上做的**：

```bash
cd engines/polyglot-route-engine
uv run --locked python -m pytest tests/test_kotlin_target.py -q
```

## 5. 仍未解除的限制

Kotlin 现在**只能作目标**。作源仍需 kotlinc 纳入 `toolchains.py` 的
symlink-free 精确工具链树；行为验证还需 `validation.py` 的 kotlin harness。
云端这次用的 kotlinc 2.1.21 不是钉死版本，**上述差分是原型证据，不是路由证据**。
