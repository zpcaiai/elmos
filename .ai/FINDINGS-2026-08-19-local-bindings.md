# Findings — 2026-08-19 · IR 新增 `let`：单赋值局部绑定

> 追加文件，不写入 `HANDOFF.md`。本文件不含任何认证声明。

## 为什么先做这一条

探针把 IR 的白名单量了出来：`name / literal / binary / return / if`。
**没有局部变量**——所以任何带中间量的函数都无处安放，这就是「几乎没有真实函数能进 profile」的直接原因。

在所有加宽项里，局部绑定是**价值最高、牵连最少**的一条：不涉及跨函数、跨文件、异常或对象模型。
而且我此前推迟的 `#5b2 if-init` 正是它的特例。

## 三个设计决定

**一、单赋值，不是赋值。** 名字只绑一次，且只对其后的语句可见。
允许重绑会让函数的含义依赖语句顺序，而等价性模型没有办法比较这种依赖——
profile 的整个主张是「函数是一棵有类型的纯表达式树」。

**二、块作用域，而且是刻意取更严的一侧。**
Python 是函数作用域，`if c: x = 1` 之后 `x` 仍可读；
Go/Rust/Java/C#/C++/Swift 是块作用域，同样的写法根本不编译。
**一份 IR 不能同时是两种含义**，所以它取在所有目标上都安全的那一种：
分支内引入的绑定在分支结束时消失，依赖 Python 函数作用域的源码在此被拒，
而不是被发射进一个编译不过的目标。

**三、类型是声明的，不是推断的。** 前端已经用源语言自己的类型系统解析过了，
把它写进 IR 才使得 `types.check` 有资格**反对**，而不是默默接受表达式恰好算出来的东西。

## 落地范围

| 层 | 改动 |
|---|---|
| `models.py` | `Statement` 新增 `let` 种类（`name` / `type` / `expression`），往返映射 |
| `types.py` | 环境随 `let` 增长；`if` 分支拿环境副本（块作用域）；五类拒绝 |
| `emitter.py` | 11 个目标的拼写表；分支拿环境副本 |
| `identifier_hygiene.py` | 新增 `local` 角色：绑定分配、plan 校验、重命名、生成名前缀 `elmos_l###` |

**关键的安全细节：局部与参数共用同一张 `occupied` 冲突表**，
因为它们在目标语言里同处一个作用域——局部若取到参数的目标名，
在每一种花括号语言里都会遮蔽它，在其中几种里直接是重复声明错误。
共用一张表使这种冲突**不可能发生**，而不是「不太可能」。

各目标的不可变拼写按语言自己的说法：Java `final`、Rust/Swift `let`、Kotlin `val`、
TypeScript `const`、C++/Objective-C `const`。C#/Go/Python/PHP 没有局部不可变关键字，用朴素声明。
IR 已经保证只绑一次，能说出来的目标就该说出来——既让人读得懂，也让目标自己的编译器
去强制 IR 只是承诺的事。

## 验证

**五个目标真编译、真运行、逐输入比对**——不是断言字符串：

```
  input        python     java       go     rust   kotlin  verdict
  area(10,3)         16       16       16       16       16  ok
  area(7,3)          10       10       10       10       10  ok
  area(-7,3)         -8       -8       -8       -8       -8  ok
  area(0,5)           1        1        1        1        1  ok
```

`area(-7,3) = -8` 是截断除法的边界，五个目标一致。

五类拒绝各有精确码，逐条实测：

| 场景 | 拒绝码 |
|---|---|
| 分支内绑定泄漏到分支之后 | `UNDECLARED_NAME:t` |
| 遮蔽参数 | `LET_NAME_ALREADY_BOUND:a` |
| 同名重复绑定 | `LET_NAME_ALREADY_BOUND:x` |
| 声明类型与表达式不符 | `LET_TYPE_MISMATCH:number:integer` |
| 自引用 `let x = x + 1` | `UNDECLARED_NAME:x` |

保留字改写在 java/go/rust/kotlin/python/php 六个目标上实测有效
（`final`/`var`/`match`/`val`/`class`/`list` 全部被改写为 `elmos_l000_…`，理由记为 `TARGET_RESERVED`）。

`tests/test_local_bindings.py` 34 条，**纯 Python 任何机器可跑**。

## 没有做，以及为什么

**没有任何前端产出 `let`。** 这是有意的：
不含 `let` 的既有 IR 发射结果**字节不变**，90 条路由的证据一个都不动。

前端要不要开始产出 `let`，是一个**独立的、需要你拍板的决定**，因为它会改变
discovery 的判定（原本被拒的文件开始产生单元），进而改变证据。
而且模块清单那段代码写得很清楚：「profile 是有意封闭的，新增字段改变契约，
因此需要新 profile/schema 而不是被忽略」——所以那一步很可能意味着
`typed-pure-function-v1` → `v2`。

**建议的下一步**：先只在 Python 前端接受赋值语句，跑一遍完整路由证据，
量出「有多少原本被拒的真实函数因此进入子集」，再拿那个数字去决定要不要升 profile。

## 你需要在 Mac 上做的

```bash
cd engines/polyglot-route-engine
uv run --locked python -m pytest tests/test_local_bindings.py -q
uv run --locked python -m pytest -q          # 全量回归，确认既有证据未变
```
