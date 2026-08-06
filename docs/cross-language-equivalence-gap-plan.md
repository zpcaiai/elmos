# ELMOS 跨语言仓库级转换 —— 语义 / 语义块 / 特殊语法 / 行为等价 补齐计划

> 基线核对日期：2026-08-06
> 核对对象：`routes/`（30 条有向路线）、`engines/polyglot-route-engine/`、`modules/{uir,semantic,lowering,behavior-equivalence}/`
> 本文只依据仓库内实际代码与证据文件，不采信 README 的叙述性描述。

---

## 0. 先更正一处判断

初读时我低估了引擎质量。`engines/polyglot-route-engine/src/elmos_polyglot_route/types.py` 与
`emitter.py` 里的**跨语言语义补偿是认真做过的**，而且是本仓库最有价值的资产：

| 已处理的分歧 | 补偿手段 | 位置 |
| --- | --- | --- |
| 整数 `/` 在 Python 是真除、在 Java/C# 截断 | 注入 `_elmos_truncating_div` / `Math.trunc` | `emitter.py:200` |
| `%` 在 Python 取下整、其余截断；浮点 `%` 同理 | `_elmos_truncating_mod` / `math.fmod` | `emitter.py:211` |
| Java `String ==` 是引用比较 | 改写为 `.equals()` | `emitter.py:224` |
| TypeScript `==` 有隐式转换 | 强制 `===` / `!==` | `emitter.py:250` |
| TS `number` 无法精确表示 > 2^53 的整数 | 字面量超界直接 `RouteError` | `emitter.py:132` |
| Java/C# 无后缀字面量默认 `int`，`long` 会编译失败 | 补 `L` 后缀 | `emitter.py:138` |
| Rust 混合 `i64`/`f64` 不隐式提升 | 显式 `as f64` | `emitter.py:193` |
| ObjC `NSString` 无 `+`、`==` 比地址 | 改写为消息发送 | `emitter.py:232` |

**这套"canonical 语义 + 目标语言偏差补偿"的架构是对的，应当保留并沿用。**
问题不在方法，在**覆盖面**：它只覆盖 5 种构造（`if` / `return` / 名字 / 字面量 / 二元运算）和 4 种类型。

所以本计划的定位不是"推倒重来"，而是**把这套已被证明有效的方法，沿一条明确的阶梯往上推**。

---

## 1. 现状事实基线

### 1.1 语义 profile

`routes/*/lowering/profile.json` **30 份文件 md5 完全一致**（`eb10149d0e6a84efd2c6e00d3f7f2ed6`）：

```json
{ "statements": ["if", "return"],
  "expressions": ["name", "literal", "binary"],
  "operators": ["+","-","*","/","%","<","<=",">",">=","==","!=","&&","||"],
  "profile": "typed-pure-function-v1", "fail_closed": true }
```

类型：`integer` / `number` / `boolean` / `string`，`unknown_type_policy: BLOCK`。

**尚不支持**：局部变量声明与赋值、任何循环、任何函数调用、递归、null/可空、
异常、聚合类型、集合、泛型、闭包、模式匹配。
即 `long t = a + b; return t;` 目前也是 `UNSUPPORTED`。

### 1.2 行为等价证据

每条路线 3 个语料 × 3 个用例 = **9 个断言**，30 条路线合计 270 个。
全仓库的语料只有三个函数（各语言直译版）：

| 语料 | 函数 | 行数 |
| --- | --- | --- |
| development | `calculate(subtotal, tax)` — 负数返回 0，否则相加 | 5 |
| holdout | `clamp(value, upper)` | 7 |
| real-repository | `difference(left, right)` | 5 |

`certification/*.json` 记录的是真实的目标语言 build + run（例如 `dotnet build RouteHarness.csproj`），
这部分是**真证据**。但它证明的命题是"这 9 个输入上输出一致"，不是等价。

### 1.3 形式化论证

全仓库无 SMT / 符号执行 / bisimulation 应用于转换。
`docs/batch35/PRODUCT_IMPLEMENTATION.md` 自述：
*"does not prove behavioral equivalence for a real migration route"*，
外部 SMT/符号执行 `NOT_RUN`。

### 1.4 两套互不连通的栈

| 栈 | 语言 | 规模 | 是否接入 30 条路线 |
| --- | --- | --- | --- |
| `engines/polyglot-route-engine`（Python + 原生分析器） | Python | 4,096 行 + 分析器 865 行 | **是**，这是实际执行路径 |
| `modules/uir` + `modules/semantic` + `modules/lowering`（Java） | Java | 875 + 726 + 911 行 | **否**，grep 无引用 |

Java 侧的 UIR 是模型 + 校验器，没有 6 语言的 lifting/lowering 实现。
`single_unit.py` 的注释确认二者是并行而非同一条链路。

### 1.5 语言集不一致

`models.py` 声明 9 种语言（新增 `cpp` / `objc` / `swift`，emitter 也已有对应分支），
但 `routes/` 只有 6 语言 × 5 = 30 条。**cpp/objc/swift 是无路线、无语料、无证据的影子能力。**
9 语言的完整有向对是 72 条。这个不一致要先解决，否则后续所有计数都是错的。

---

## 2. P0：L0 子集内的等价缺陷（已修复）

以下缺陷全部发生在**当前已声明支持**的构造上。30 条路线每条 9 个用例、全是小正数，
没有一个能触发它们；`certification.json` 里 `critical_unknown_semantics: 0` 与
`p0_behavior_pass_rate: 1.0` 在这些输入下不成立。

修复已落在 `engines/polyglot-route-engine/src/elmos_polyglot_route/emitter.py`，
回归测试在 `tests/test_arithmetic_equivalence.py`。

### P0-0 Rust 丢失括号 —— 静默错值（最严重）

`_binary` 对其余八个目标都加括号，唯独 Rust 走
`f"{left} {rendered} {right}"`。IR `(a + b) * c` 因此发射为 `a + b * c`：

```
f(1, 2, 3)   其余目标 = 9      Rust = 7
```

**普通输入、无诊断、结果错误**。这是四类缺陷里唯一一个不报错就给错值的。

同一处还有第二个后果：整数 `/` 与 `%` 发射为 `return (a / b);`，而路线 harness 自己用
`rustc -D warnings` 编译，`unused_parens` 直接是错误——**任何含整数除法的函数在 Rust 目标上
根本编译不过**。五条 `*-to-rust` 路线从未碰到过，因为语料里没有除法。

修法：引入 `top_level` 参数。嵌套位置照常加括号，最外层（`return` 表达式与 `if` 条件）
对 Rust 不加，同时满足正确性与 `-D warnings`。

### P0-1 整数溢出（`+` `-` `*`）—— 规则 R1

IR 定义 `integer` 为 64 位有符号，但运行时溢出未补偿：

| 目标 | `add(2^63-1, 1)` |
| --- | --- |
| Java / C# / Go / C++ / Objective-C | 回绕为 `-9223372036854775808`（C/C++ 是 UB） |
| Rust | debug 构建 panic，release 回绕 |
| Python | 任意精度，得到精确的 `9223372036854775808` |
| TypeScript | 已有的 `_elmosRequireSafeInteger` 在返回处拦下，抛 RangeError |

**canonical 规则 R1：整数溢出即错误。** 各目标补偿方式：
Java `Math.addExact/subtractExact/multiplyExact`；C# `checked(...)`；
Rust `checked_*().expect(...)`；Swift 原生 trap；
Python / Go / C++ / Objective-C 注入检查辅助函数；
TypeScript 沿用 2^53 的安全整数守卫——**域更窄，失败更早，但永远不会给错值**，
这是本 profile 记录在案的唯一一处非对称。

### P0-2 除零与取模零 —— 规则 R2

整数侧：TypeScript `Math.trunc(a / 0)` 是 `Infinity`、`a % 0` 是 `NaN`。
返回类型为 `integer` 时安全整数守卫会拦下，但**结果不进入返回位置时不会**：

```
positive(a, b) = (a / b) > 0
positive(1, 0)   Java 抛 ArithmeticException      旧 TypeScript 返回 true
```

C 与 C++ 的整数除零是 UB。另有 `INT64_MIN / -1` 与 `INT64_MIN % -1` 溢出结果类型：
Java 静默回绕、C# 抛、Rust panic、Go 回绕、C++ SIGFPE。

浮点侧方向相反：`1.0 / 0.0` 在其余八个目标是 IEEE Infinity，**只有 Python 抛异常**；
`math.fmod(x, 0.0)` 抛 ValueError 而 Java/C#/TypeScript 给 NaN。

**canonical 规则 R2：除数为零即错误，整数与浮点一致。**
九个目标就此统一。Python 侧原生已经是错误，无需守卫；其余八个注入除数非零检查。

### P0-3 C/C++ 最负字面量

`-9223372036854775808LL` 在 C/C++ 里是一元负号作用于放不进有符号 64 位的常量，
GCC/Clang 报 `integer constant is so large that it is unsigned`，而 harness 用 `-Werror`。
改为发射 `INT64_MIN` / `LLONG_MIN` 宏。

### 修复后的实测结果

用 5 个算子 × 16 组边界参数（`0` / `±1` / `2^53±1` / `INT64_MAX` / `INT64_MIN` 的组合），
以 Python 目标为 oracle，对**真实编译并执行**的 Java、Go、Rust、C++、TypeScript 逐条比对：

| | 修复前 | 修复后 |
| --- | --- | --- |
| 分歧 / 编译失败 / 崩溃 | **18** | **0** |

400 次比对全部一致。这是这批路线第一次有超出 9 个手写用例的执行证据。

### P0-4 用例强度（已做，S1）

三层叠加，全部进 CI，只依赖 CPython 与 Node：

**属性/差分测试** —— `tests/test_property_differential.py`。
覆盖 L0 全部产生式的 5 个单元（混合优先级算术、双除法、嵌套 if/else 的 clamp、
difference、布尔连接词），每个单元 600 组输入：225 组边界值对全排列 +
固定种子的分层随机（小值 / 2^k±1 / 安全整数域 / 全宽）。
另有一条测试断言这个分布**确实到达**了各个区域——否则上面所有断言都是空转，
这正是 9 个手写用例的失败模式。

**可执行的 canonical 语义** —— `src/elmos_polyglot_route/canonical.py`（新增）。
差分测试需要一个参照物；拿某个 target 当参照，等于把一份实现悄悄提升成规范。
这个模块就是规范本身：R1/R2 的解释器。它还报告**每个中间值**的最大量级，
而这正是把 TypeScript 的收窄说准确所必需的——
`(a + b) * a - b` 在 a=1, b=2^53−1 时答案是 1（完全在安全域内），
但第一个中间值是 2^53，TypeScript 必须失败。只看操作数和结果会把这误判为分歧。

**突变测试** —— `tools/run_emitter_mutation_campaign.py`。
23 个突变体，每个撤销 emitter 的一处补偿（重构或合并真的可能引入的那种）。

| 轮次 | 突变得分 | 幸存者 |
| --- | --- | --- |
| 首轮 | 89.5%（17/19） | Rust 括号、Go 溢出谓词 |
| 补齐后 | **100%（23/23）** | 无 |

两个幸存者各自暴露了一个真实的测试空洞，都不是猜出来的：

1. **Rust 括号**：去掉 `_group` 的 Rust 分支，测试全绿。因为受检算术调用
   （`checked_add(...)`）自带括号，重结合只在**中缀发射的算子**上显形——
   即比较和布尔连接词。`(a || b) && c` 在 Rust 里去括号后是 `a || b && c`，
   即 `a || (b && c)`，a=true b=false c=false 时答案由 false 变 true。已补测试。
2. **Go 溢出谓词**：改坏 Go 的四个溢出守卫，测试全绿——因为**没有一个测试执行 Go**。
   SMT 证明本该抓住它，但没有：证明读的是手工转写的模型，不是 emitter 的文本。
   这是"模型漂移"，一个纯装饰性证明的典型死法。已用**转写锁定**关闭（见下）。

### 已修复后的实测

| | 修复前 | 修复后 |
| --- | --- | --- |
| 5 语言 × 5 算子 × 16 组边界参数，真实编译执行 | **18 处分歧/编译失败/崩溃** | **0** |
| emitter 突变得分 | 未度量 | **100%（23/23）** |

## 3. 缺口一：语义 —— 分级 profile 阶梯

不要试图一步到"全语言"。定义一条每级都可独立验收、可失败关闭的阶梯，
每一级都必须同时交付：profile 扩展 + 补偿矩阵条目 + 语料 + 属性测试 + 门禁。

| 级别 | 新增构造 | 核心难点 | 量级 |
| --- | --- | --- | --- |
| **L0**（现状） | `if` / `return` / 名字 / 字面量 / 二元运算 | — | 已有 |
| **L1** | 局部变量声明、赋值、多语句块、`else if` | 作用域与遮蔽规则（Python 无块级作用域，Rust 有 shadowing，Go 有 `:=` 重声明） | 数周 |
| **L2** | `while` / `for` / `break` / `continue` | 循环变量作用域、Go 闭包捕获、终止性对属性测试的影响（需超时预算） | 数周 |
| **L3** | 函数调用、递归、多函数单元 | 工作单元不再是单函数；调用图、栈深度限制（Python 默认 1000 vs JVM 数万） | 数周 |
| **L4** | 可空 / Option | **范式转换**：Java `null` / Rust `Option<T>` / TS `null\|undefined` / Go 零值 / C# 可空引用类型 —— 无法一一对应 | 数月，需设计决策 |
| **L5** | 错误与异常 | **范式转换**：Java checked exception / Go `(T, error)` 返回 / Rust `Result` / Python 异常 —— 控制流形状不同 | 数月，需设计决策 |
| **L6** | 聚合类型（struct/record，无继承、无可变别名） | 值语义 vs 引用语义、相等性定义、字段顺序与序列化 | 数月 |
| **L7** | 集合与迭代 | 迭代顺序（Go map 随机、Python dict 插入序、Java HashMap 未定义）、相等性、可变性 | 数月 |
| — | 对象图 / 可变别名 / 并发 / I/O / 框架 / 数据库 | 每一项都是独立产品级投入，且部分不存在保等价的通用解 | 不建议在本阶梯内承诺 |

**L4 和 L5 是真正的分水岭。** L1–L3 是同一套方法的机械扩展；
L4/L5 起，源语言和目标语言的错误处理范式不同构，"翻译"会退化为"重新设计"，
必须先做出并写下明确的设计决策（例如：Go→Rust 时 `(T, error)` 映射到 `Result<T, E>`，
但 Rust→Go 时 `Result` 的 `?` 传播链要展开成什么形状），而不是让 emitter 临时发挥。

---

## 4. 缺口二：语义块 / 作用域

L1–L3 的核心不是语法，是**作用域与生存期模型**。当前 IR（`models.py`）里没有任何
作用域概念——`_expression` 用一个扁平 `environment: dict[str, str]` 查名字。

需要在 IR 层新增：

1. **词法作用域树**：块进入/退出、遮蔽（shadowing）判定、名字解析结果显式化到 IR，
   不留给 emitter 现场推断。
2. **各语言作用域偏差的补偿规则**，例如：
   - Python 无块级作用域：`if` 块内声明的变量在块外可见 → 发射时需提升到函数顶部声明；
   - Rust 允许同名 shadowing 且类型可变 → 从无 shadowing 的语言过来要保证不意外遮蔽；
   - Go 的 `:=` 在内层块会创建新变量而非赋值 → 从有赋值语义的语言过来必须用 `=` 而非 `:=`；
   - C# / Java 禁止内层块遮蔽外层局部变量 → 从 Rust 过来的 shadowing 必须重命名，
     且重命名必须记进 source map。
3. **赋值与求值顺序**：当前只有纯表达式所以无所谓；一旦有赋值和调用，
   参数求值顺序（Java/C# 左到右确定，C++ 未指定）就成为可观察行为。

这一块的产出物应当是一份显式的 **`构造 × 语言` 补偿矩阵**（见第 6 节），
而不是散落在 emitter 里的 `if language == ...` 分支——现在只有 5 种构造还能读，
到 L3 就会不可维护。

---

## 5. 缺口三：特殊语法

现状：`routes/*/mappings/` 每条路线只有一个 `types.json`，内容是那 4 个原始类型。
**各语言独有构造零映射。**

正确的做法**不是**为 30（或 72）个语言对各写一份映射表——那是 N² 灾难。
沿用现有架构，做成 **N + M**：

```
源语言 Analyzer ──► Canonical IR ──► Target Emitter
   (N 个)          (语义唯一)         (M 个)
                        ▲
                        └── 补偿矩阵：构造 × 目标语言（条目数 = 构造数 × M）
```

对每个语言独有构造，判定必须落到三档之一，且**默认档是"拒绝"**：

| 档位 | 含义 | 例子 |
| --- | --- | --- |
| **可规范化** | 能无损降解到 canonical IR | Rust `match` 的穷尽整数分支 → `if/else if` 链；TS 可选参数 → 显式重载 |
| **需补偿发射** | canonical 能表达，但目标语言要注入辅助代码 | Java `String ==` → `.equals()`（已有）；Go 缺三元 → `if` 语句 |
| **拒绝（默认）** | 无保等价的映射 | Rust 生命周期/借用检查、Java 反射、Python 元类与鸭子类型、Go `unsafe`、C# `dynamic`、TS 结构化类型的宽松性 |

**关键纪律：新构造的默认判定必须是"拒绝"，由人显式提升到前两档并附证据。**
现有 `unknown_type_policy: BLOCK` 和 `discovery.py` 的
`UNSUPPORTED` / `NO_CANDIDATE_DECLARATION` 三态判定已经是这个纪律，
只要把它从"类型"推广到"构造"即可，不需要新机制。

同时需要一份**逐语言的"未判定构造清单"**：对 6（或 9）种语言各自列出语言规范里的全部构造，
标注当前档位。清单的完成度本身就是一个可度量的覆盖率指标——
比现在的"30 条路线 PASSED_LOCAL"有意义得多。

---

## 6. 缺口四：等价论证方法

按强度从低到高，四层叠加使用，**每层的适用范围要显式声明**：

### 6.1 差分执行（Differential Execution）—— 覆盖面最广

源与目标同输入同运行，比对输出。是主力手段。
要求：≥ 10,000 组生成输入 + 全量边界值，而非 9 个手写用例（见 P0-4）。
局限：只能证伪，不能证明。

### 6.2 变形 / 性质测试（Metamorphic & Property Testing）

对函数的代数性质（幂等、交换、单调、值域约束）在两侧同时校验。
能覆盖差分测试难以生成的关系型缺陷。

### 6.3 突变测试（Mutation Testing）—— 度量前两层的强度

对 emitter 和补偿规则注入突变，统计被杀死比例。
**这是唯一能给"我们的用例够不够"一个数字的手段**，应作为门禁指标（建议起步阈值 ≥ 80%，逐级提高）。

### 6.4 形式化验证（已做，S2）

`tools/prove_arithmetic_compensation.py`，45 条义务（9 目标 × 5 算子），用位向量理论。
证的是：对**全部 2^128 组 64 位输入**，发射出的补偿形式与 canonical 规则
要么同时报错、要么给出相同的值。

```
13 proved at 64 bits, 2 bounded to narrower widths, 30 axiomatised, 0 unresolved
```

**四种强度必须分开读，这比总数重要：**

| 强度 | 目标 | 含义 |
| --- | --- | --- |
| THEOREM | go、python（8 条） | 真正的内容。这两个目标靠**手写的 helper 函数体**补偿——是会写错的普通代码，被转写成模型后由求解器判定 |
| THEOREM（较弱） | typescript（5 条） | 证的是守卫**结构**刻画了 binary64 精确域，不是某个函数体 |
| AXIOM | java、csharp、rust、swift、cpp、objc（30 条） | **完全没证**。它们的补偿就是语言原语（`Math.addExact`、`checked()`、`checked_add`、Swift trap、`__builtin_*_overflow`），义务是一条语言规范引用，求解器无从判定。靠差分执行覆盖 |
| BOUNDED | go `*`、python `%`（2 条） | 只在 8 位宽判定，64 位超预算。位向量乘法配位向量除法在全宽下打不过预算。**这是证据不是证明**，单列 |

两处工程细节值得记下：

- **求解器状态会改变结论。** 同一条义务（`python /`）在干净进程里 2.4 秒判定，
  在跑过三次超时查询之后就变成超时。所以每条义务在**独立子进程**里跑——
  否则报告的答案取决于提问顺序，这不是一份证明报告该有的性质。
- **证明必须锁定到代码。** 模型是手工转写的，求解器看不见它和 emitter 漂移。
  `MODELLED_SOURCES` 把每个模型钉到它所描述的 emitter helper 文本上，
  改一个 helper 就是"代码 + 模型"两处编辑，而不是无声分叉。突变测试验证了这一点：
  加锁前 4 个 Go 突变体全部存活，加锁后全部被杀。

**范围声明**：这些证明只覆盖 L0 的整数算术。之所以求解器能判定，
恰恰因为这个子集小到在真实代码上几乎没用。诚实的读法是：**证明了地基是稳的，
不是证明了楼已经盖起来。**

**用词纪律**：只有 6.4 的产出可以叫"等价证明"，且必须附带其适用范围声明。
6.1–6.3 的产出只能叫"未发现反例"。当前所有 `certification.json` 的措辞需要按此复核。

---

## 7. 分阶段路线图

每一阶段的完成定义（DoD）统一为五条，缺一不可：
**profile 扩展** + **补偿矩阵条目（构造 × 全部目标语言）** + **语料** + **属性/差分测试通过** + **突变得分达标**。

| 阶段 | 内容 | 前置 | 产出的可信断言 |
| --- | --- | --- | --- |
| **S0** ✅ | 语言集边界显式化：`ROUTED_LANGUAGES`(6) / `ENGINE_ONLY_LANGUAGES`(3) 写进 `models.py`，`tests/test_language_set.py` 校验划分穷尽、30 条路线包齐全、engine-only 语言不得声称路线证据 | — | 路线计数与证据自洽 |
| **S1** ✅ | 属性 + 变形 + 突变测试，可执行 canonical 语义 | S0 | 突变得分 **100%**，L0 子集内首次有强度可度量的等价证据 |
| **S2** ✅ | 45 条 SMT 义务，13 条 64 位证明 / 2 条有界 / 30 条公理化 | S1 | L0 整数算术的**真正等价证明**（附强度分级） |
| **S3** | L1 局部变量与作用域，含作用域补偿矩阵 | S1 | — |
| **S4** | L2 循环（含有界展开的 SMT 验证） | S3, S2 | L0–L2 内的等价证明 |
| **S5** | L3 函数调用与递归，工作单元从"单函数"升级为"调用图" | S4 | 差分证据（SMT 不再适用递归） |
| **S6** | L4/L5 设计决策文档（可空、错误范式）—— **先出决策，再写代码** | S5 | — |
| **S7+** | L4–L7 实现 | S6 | 逐级 |

**S1 和 S2 已完成。** 下一步是 S3（L1 局部变量与作用域），而不是继续加宽 L0。 理由：现在扩范围，是在一个未经强度验证的
证据体系上叠加更多未验证的东西；先把 L0 这个最小子集做到"有 SMT 证明 + 突变得分达标"，
这套方法论就被验证了，后面每一级都是同一套动作的重复，可预测、可估时。

---

## 8. 需要你决策的三件事

1. **整数溢出的 canonical 语义**：回绕 / 溢出即错误 / 缩窄值域（第 2 节 P0-1）。
   建议"溢出即错误"，但如果目标场景是迁移金融/嵌入式老代码，回绕可能才是保真的选择。

2. **语言集定为 6 还是 9**。6 = 30 条路线，9 = 72 条。补偿矩阵的条目数随目标语言数线性增长，
   但语料、工具链、CI 时长随路线数增长。建议先锁 6，把 L0–L2 做扎实再扩。

3. **是否合并两套栈**。Java 侧 `modules/uir` (875 行) 与 Python 侧 route engine 目前并行且互不引用。
   继续并行会导致语义定义有两个真相源。建议：以 Python route engine 的 IR 为唯一真相源，
   Java 侧 UIR 退化为该 IR 的 schema 校验与证据模型，或直接标注为 deprecated。

---

## 9. 一句话总结

已有的"canonical 语义 + 目标语言偏差补偿"架构是正确的且质量不错，
但它目前覆盖 5 种构造、4 种类型、9 个测试断言。在这个已声明支持的范围内，
本次找到并修复了四类缺陷，其中 Rust 丢括号是普通输入下的静默错值。
修复前后同一组边界差分：**18 处分歧 → 0**。

S0/S1/S2 已完成：语言集边界显式化，突变得分 100%，L0 整数算术拿到 64 位 SMT 证明。
剩下的每一级（L1 局部变量 → L7 集合）都是同一套动作的重复：
**profile 扩展 + 补偿矩阵条目 + 语料 + 属性测试 + 突变门禁 + SMT 义务**。
方法论已经在最小子集上被验证过了，后面可估时。
