# 怎样提高准入率：两堵墙的联合测量

2026-08-26。仪器：`.ai/measurement-2026-08-26/measure_admission_headroom.py`、
`headroom_detail.py`、`structural_split.py`、`nested_split.py`。
证据：`admission-headroom.json`。语料与 08-21 完全相同（20 个真实 PyPI 项目，583 文件 / 7.06 MB），
所以数字与 `FINDINGS-2026-08-21` 可直接对比。

工具链背书 **NOT_RUN**（`discover_unit` 只在 Darwin/arm64 跑）；调用的是它下面两层，
与 08-21 的做法一致。

## 0. 这次测量为什么必须换一把仪器

`measure_admission.py` 报的是**每个候选死在哪一条**——但引擎只报**第一个**阻塞码。
拆掉第一堵墙，第二堵墙才显形；原来看着像收益的那个数字其实是个队列。
08-25 的 `UNSUPPORTED_STATEMENT 94→21 / UNSUPPORTED_EXPRESSION 14→58` 就是这个现象。

所以这把仪器做两件不同的事：

1. **穷举**每个函数体内**所有**越界构造，不在第一个停下。
2. 把两道闸门**分开**判定，因为一个函数必须**同时**过两道：

   - **A 墙（签名类型闸门）**：每个参数与返回值都标注为 `int/float/bool/str`。
   - **B 墙（函数体闸门）**：语句只有 `Return` / `If` / 带注解赋值；
     表达式只有名字、字面量、`+ - * / %`、六个比较、二元 and/or。

只放宽一堵墙，函数只是从 A 墙下的尸体变成 B 墙下的尸体，**净准入增量为零**。

仪器自带**自证**：脚本内的子集镜像与真实 `analyze_python` 必须给出**完全相同**的 READY 集合，
不一致就 abort 不出数。第一次跑就 abort 了——镜像多认了 3 个 jinja2 的
`test_even/test_odd/test_divisibleby`，因为我没模型化
`_reject_python_only_arithmetic`（Python 的 `%` 随除数符号，C 系截断）。补上后一致。

---

## 0. 更正：本文第一版的三个数字是错的（仪器缺陷）

第一版发出后我在自查中发现 `measure_admission_headroom.py` 有一个真缺陷：
`expr:Call` 分支只递归 **参数**，**没有递归接收者**。于是
`_PATTERN.sub('-', name).lower()` 只记了外层的 `.lower`，内层的 `.sub` 整个丢掉。

后果是**阻塞集被少记 → 每一个「净新增 READY」都被高估**。已修（走 `func.value`），全部重跑：

| | 第一版（错） | 修正后 |
|---|---|---|
| str 方法 only | 11 | **3** |
| str 方法 + 纯 builtin | 12 | **6** |
| + 用户函数 | 16 | **13** |
| 全部调用 | 27 | 27（不变） |
| `user-function` 出现次数 | 2,540 | **2,623** |
| `module-or-object-method` | 2,056 | **2,133** |

**「两堵墙」的上界与 9.15% 天花板不受影响**——那几个数只看阻塞集空不空，
少记一个阻塞不会把非空变成空。

**自证为什么没抓到它**：镜像与分析器的一致性断言只校验 **READY 集合**，
也就是阻塞集为空的那些函数；一个被少记了阻塞的函数仍然有别的阻塞，永远不会假 READY。
**断言守住了不动点，没守住枚举。** 这是这次最该记住的一条。

我上一轮据此建议「最便宜的一步是 str 方法 + 纯 builtin，1 → 13」。
**修正后是 1 → 7（净新增 6）**，而且下面第 8 节的组合搜索表明这条路本身就选错了。

---

## 1. 结论先说：profile 自己的天花板是 9.15%

```
16,046 coverage subjects
   13,437  连候选都不是        (83.7%)
    1,140  是候选但结构性阻塞   ( 7.1%)
    1,469  真正走到分析器       ( 9.15%)   <- 这就是天花板
        1  READY                (0.006%)
```

把子集放宽到**每一个候选都能过**（`everything` bundle = 1468 净新增），
准入率也只有 **1469/16046 = 9.15%**。

**换句话说：`typed-pure-function-v1` 就算做到完美，也覆盖不了一个完整转换所需的 91%。**
这不是子集宽窄问题，是 profile 形状与真实 Python 代码形状不匹配。

## 2. 两堵墙的上界（这两个数决定该不该做）

| | 已过对面那堵墙的函数数 | 含义 |
|---|---|---|
| 过 A 墙（签名干净） | **109** | 任何 **IR/函数体**放宽的绝对上界 |
| 过 B 墙（函数体干净） | **32** | 任何 **类型面**放宽的绝对上界 |
| 两墙都过 | **1** | 今天的 READY |

**「规范类型只有四类」这一项，天花板是 31 个函数**——占 16,046 的 0.19%。
而它在 08-21 报告里看起来是头号问题（`PARAMETER_TYPE_REQUIRED` 1175 条，92.6% 的死因）。
占比最大 ≠ 收益最大，这是第二次在同一个仓库里踩到。

## 3. 逐个特性的**净新增 READY**（不是出现次数）

净新增 = 该函数**剩余的全部**阻塞码都被这一组特性覆盖。

### 类型面（A 墙）

| 特性 | 出现次数 | **净新增 READY** |
|---|---|---|
| `bytes` | 62（参数注解里排第 1） | **0** |
| `T \| None` 可空 | 35 + 25 | **0** |
| `-> None` 返回 | 69（返回注解里排第 1） | **0** |
| `list[str]` 等规范容器 | 24 + 9 | **13**（见下） |
| **整个类型面全放宽** | — | **31** |

那 13 个「容器」函数，**全部**是同一个 idiom：

```
packaging/{dependency_groups,direct_url,errors,licenses,markers,metadata,
           pylock,ranges,requirements,specifiers,tags,utils,version}.py
    def __dir__() -> list[str]:
```

13 个文件里 13 份复制粘贴的模块自省桩。**真实收益 ≈ 1 个 idiom，且没人想转它。**
（count vs distinct_reasons，第三次。）

`-> None` 排返回注解第 1（69 次）却净收益 0，原因很干脆：
**纯函数不返回任何东西＝空操作**。这 69 个全是有副作用的过程，
放开返回类型只会把它们推到 B 墙下。

### 函数体 / IR（B 墙）

| 特性 | **净新增 READY** |
|---|---|
| 未注解赋值 `x = 1` | **0** ← 与 08-25 独立复现一致 |
| 一元 `not` / `-x` | **0** |
| f-string | **1** |
| `None` 字面量 + `is/is not` | **0** |
| Python 特有算术（`%`、int `/`） | **3** |
| **函数调用（全部）** | **27** |
| **整个函数体面全放宽** | **108** |

## 4. 唯一真正付钱的东西：IR 里根本没有 `call`

`_expression` 的白名单里没有 `ast.Call`（只有发射目标的两个内部 helper 例外）。
一个不能调用任何东西的纯函数，只能是参数上的直白算术——
所以 20 个真实项目收成 **1 个 `_gettext_noop`（恒等函数）**。

把 27 个「只差调用」的函数按被调者拆开：

| 被调者类别 | 全候选集出现次数 | **只放开这一类的净新增 READY** |
|---|---|---|
| str 方法（`.lower/.replace/.strip/.upper/...`） | 239 | **3** |
| 纯 builtin（`len/abs/min/max/...`） | 463 | **1** |
| ↑ 两者合计 | 702 | **6** |
| + 用户函数（需要被调者纯度证明） | 2,623 | **13** |
| + 模块/对象方法（`re.sub`、`sys.*`、`struct.*`） | 2,133 | **27** |

str 方法 + 纯 builtin 只买到 **6**（1 → 7）。而且这 6 个需要的操作里，
`len` 在 13 门语言里根本不是同一个函数——Python 数码点、Java 数 UTF-16 单元、
Go/Rust 数字节；`.islower()` 要 Unicode `Cased` 属性，Java 没有对应物；
`.lstrip(chars)` 是字符集不是前缀，只有 Go 的 `TrimLeft` 语义相同。
**这条路又小又不便宜。**

真正能改变数量级的是 `user-function` 那 2,623 次——它要的是跨单元纯度证明，
是架构工作不是子集工作。第 8 节的组合搜索给出了排序。

## 5. 真正的大头在分析器**之前**

13,437 个 subject 连候选都不是。按**首个**阻塞码、去重到 subject：

| 首个阻塞码 | subject 数 | 占全体 |
|---|---|---|
| `TOP_LEVEL_EFFECT` | 7,784 | 48.51% |
| `NESTED_SYMBOL` | 4,539 | 28.29% |
| `CLASS_SYMBOL` | 1,114 | 6.94% |
| `FUNCTION_SIGNATURE` | 906 | 5.65% |
| `DECORATED_SYMBOL` | 219 | 1.36% |
| `ASYNC_FUNCTION` | 15 | 0.09% |

把 `NESTED_SYMBOL` 拆开（按同文件内的定义位置判定）：

```
4,596 个 NESTED_SYMBOL
  4,128  89.82%  类方法          <- 占全部 16,046 的 25.7%
    383   8.33%  内层函数/闭包
     57   1.24%  其它嵌套
     28   0.61%  同文件两种写法都有
```

**类方法 4,128 + 类符号 1,114 + 类定义副作用 878 ≈ 6,120，约占全体 38%。**
`typed-pure-function-v1` 是一个**自由函数** profile，而真实 Python 库是类组织的。

`TOP_LEVEL_EFFECT` 那 7,784 也不是噪音：模块体语句里
**模块级赋值 46.3% / import 36.7%**——常量表、预编译正则、查找表。
import 大概属于装配层不属于 IR，但赋值是真内容。

## 6. 所以，排序

1. **先认这个天花板**：不改 profile，准入率的物理上限是 **9.15%**，
   而且要走到那儿得把函数体面整个放开（108 个）+ 类型面整个放开（31 个）。
   **在这个 profile 里谈「提高准入率到可用」是没有出路的。**
2. **profile 内最便宜的真收益**：`call` 的**有界白名单**——str 方法 + 纯 builtin。
   **1 → 13**，形状照抄 SQL CHECK 那次（13 语言语义一致 + 执行证据 + 其余失败关闭）。
   代价小、方法已验证、能立刻验收。
3. **profile 内唯一的数量级变化**：用户函数调用（2,540 次），
   需要跨单元纯度证明。这是架构工作，做之前先用本文这把仪器量一遍净收益。
4. **真正的战略选择在 profile 外**：类方法（4,128 个 subject，25.7%）。
   这不是把子集放宽，是**新增一个 profile**（方法 / 结构体 / 接收者）。
   在此之前，任何「规范类型扩到 bytes/nullable」的工作**已被实测证明净收益为 0**，
   不应该排在前面。

## 7. 方法上的一条

这把仪器最重要的部分不是它算出的数，是它**跑不出数就 abort**：
脚本内的子集镜像与真实分析器的 READY 集合必须逐条相同。
第一次跑就抓到我漏掉了浮点取模那条规则。
**任何「假如支持了 X 会怎样」的测量都必须有这样一条自证**，
否则它量的是我对引擎的记忆，不是引擎。


---

## 8. 组合搜索：最便宜的**组合**是什么（穷举 1–4 元）

单个特性的净收益几乎全是 0，因为函数必须**整套**阻塞被清掉。所以真正的问题是组合的。
把 47 个阻塞族穷举到 4 元：

```
--- 1 元 ---            --- 2 元 ---
  +13  TYPE:CONTAINER_OF_CANONICAL      +44  CALL:user-function + TYPE:MISSING
  +11  TYPE:MISSING                     +24  TYPE:CONTAINER_OF_CANONICAL + TYPE:MISSING
  + 4  CALL:str-method                  +23  CALL:object-or-module-method + TYPE:MISSING
  + 4  CALL:object-or-module-method     +18  EXPR:other-binary-operator + TYPE:MISSING

--- 3 元 ---                            --- 4 元 ---
  +62  CALL:object-method + CALL:user-function + TYPE:MISSING
  +58  CALL:user-function + TYPE:MISSING + TYPE:OTHER      +83  ... + EXPR:Tuple + STMT:Assign
```

**`TYPE:MISSING` 出现在每一个头部组合里；`CALL:user-function` 出现在 3 元的 5/6 里。**
这两个是**基石**，其余都是配角。

- `TYPE:MISSING` ＝ 参数或返回**根本没有注解**。它不是「类型面太窄」，
  放开 `bytes`/nullable 一个也救不了（实测 0）。它要么靠**推断**
  （与 `ir_local_bindings` 那条设计决定正面冲突：类型必须来自源语言的类型系统，
  不能来自分析器的猜测），要么靠**让作者补上**。
- `CALL:user-function` ＝ 调用别的函数，需要被调者的**纯度证明**。

**结论与第 6 节的排序相反地更尖锐了：不要先做 str 方法白名单（+6）。**
真正的两件事是跨单元纯度证明与「缺注解」这条路，二者合计 +44。

### 一个几乎免费的副产品

`TYPE:MISSING` 单独 = **11 个函数只差注解**。引擎今天只说
`PYTHON_PARAMETER_TYPE_REQUIRED`——不说是哪个参数，也不说这是**最后一道**阻塞。
把「只差 N 个注解就能转」做成一份可执行清单，是纯报告工作、零语义风险，
而且把 11 从「统计数字」变成「11 条待办」。

---

## 9. 本轮修掉的三个前端缺陷（准入率不变，这是预期）

三个都是**缺陷**不是边界：拒绝没有理由，或者拒绝的是 IR **本来就能表示**的东西。

| | 之前 | 之后 |
|---|---|---|
| A | `a and b and c` 被拒，`(a and b) and c` 通过 | 左折叠，产出**逐字节相同**的 IR |
| B | `-1` **根本无法提升**（Python 里它是 `UnaryOp(USub, Constant(1))`） | 折进字面量 |
| C | `not x` 被拒 | 对规范 boolean 就是 `x == False` |

**B 是最能说明问题的一条**：`emitter.py` 一直为 `-9223372036854775808` 这个常量
带着 Kotlin(`Long.MIN_VALUE`)、PHP(`PHP_INT_MIN`)、C++(`INT64_MIN`)、
Objective-C(`LLONG_MIN`) 四套补偿——**目标侧一直在支持一个源侧永远产不出来的字面量**。
死代码本身就是缺口的证据。

仍然拒绝，但现在**带理由**：
- `-x`（表达式而非字面量）→ `PYTHON_UNARY_SIGN_ON_EXPRESSION_OUTSIDE_CERTIFIED_SUBSET`。
  降为 `0 - x` 对 `integer` 精确，对 `number` **不精确**：IEEE-754 里 `-(0.0)` 是负零，
  `0.0 - 0.0` 是正零，而返回值的零符号是可观测的。做对需要 IR 里真的加一个一元节点、
  canonical.py、z3 指称、13 个发射器——不便宜，就不偷偷塞进来。
- `not <非布尔>` → Python 真值性，仍在类型检查器失败关闭（`OPERAND_TYPE_MISMATCH:==`）。
- `a < b < c`、`%`、位运算 → 各自原因未变，都有测试钉住。

### 执行证据（`canonical.evaluate` 是参照，不是某个目标）

在 Mac 上跑满 13 个目标（云端只到 7 个——csharp / objc / swift / kotlin / flutter
在任何 Linux 容器里都没有工具链）：

```
full 套件（45 向量）
  java python csharp go rust cpp objc swift php kotlin flutter   AGREES 45/45  (11)
  typescript, react                    EMISSION_REFUSED:INTEGER_LITERAL_UNSAFE_*

safe_integer 套件（44 向量）
  上面 11 个 + typescript                                        AGREES 44/44  (12)
  react                                无可执行驱动，发射结果即其证据
```

TypeScript/React 在 `full` 上的**拒绝本身就是证据**：`-9223372036854775808` 超出
`Number.MAX_SAFE_INTEGER`，发射器拒绝给出一个错的常量而不是给个近似值。
**这条 R 规则以前永远走不到**——源侧根本产不出负字面量。它们在 `safe_integer`
上 44/44，证明拒绝是针对那一个值的，不是整套都不行。

### 证据分两级，不能混着报

| | 目标 | 说明 |
|---|---|---|
| **`PINNED:` 钉死工具链** | go 1.25.0、rust 1.89.0、php 8.4.12、kotlin 2.2.20 | 从 `~/.local/share/elmos/toolchains/<lang>/<版本>/` 解析出来的 |
| **`PATH:` Mac 运行时** | java(sdkman 21.0.11-tem)、python(引擎 venv)、csharp/flutter(Homebrew)、typescript(Homebrew node)、cpp/objc/swift(Xcode 自带) | **不等于**仓库钉的那份 |

`toolchains.py` 钉的 dart 是 Flutter 3.44.1 捆绑的 Dart 3.12.1、node 是 Homebrew
node 26.0.0——和 PATH 上那个大概率不是同一个。每行用的二进制路径与 `--version`
都记在证据 JSON 里，要升级成钉死证据用 `ELMOS_DIFF_<LANG>=<绝对路径>` 重跑即可。

### 两个 DIVERGES 都是差分器自己的 bug，不是引擎

说过 `DIVERGES` 当场查、不平均掉。查完两条都是我的驱动：

- **csharp**：csproj 写死 `net8.0`，在只装了 .NET 10 的机器上报
  `framework_version=8.0.0` 缺失。改成 `dotnet --version` 取主版本。
- **objc**：只有一个 `elmos_render(long long)`，把布尔打成 `0/1`，
  并在传参时把 `-2.5` 隐式截成 `-2`。45 − 27 = 18，正好是它报的 `18/45`——
  **算术对得上，诊断才站得住**。改成按函数**声明的返回类型**选
  `elmos_render_i/_d/_b`；遇到没有渲染器的返回类型直接 `NOT_RUN` 并写明
  「拒绝打印而不是错误地打印」。

Objective-C 那条还有一段来回：为了让 Linux 容器编过，我先把
`-framework Foundation` 拿掉了——而发射出的单元用 `[NSException raise:]` 做 R1
溢出保护，于是 Mac 上变成链接期失败。**修了错的那一头。**
在 Linux 上这个目标本来就是 NOT_RUN，根本不该为它改。

### 准入率：**1/16046 → 1/16046，没有变**

这是**预期**，headroom 测量提前说过净新增 = 0。真实效果在阻塞分布：

```
全部 1469 个候选：       -457 次 not、-434 次 -x  ，共 891 次假阻塞消失
过 A 墙的 109 个：       -11 not、-7 USub、-5 三元以上布尔 = 23 次
                        新露出：11 次 `not <非布尔>`（真truthiness）、
                                4 次 text.replace、3 次 codecs.lookup
```

**那 11 个 `not` 全部是对非布尔取反**——也就是 Python 真值性。
修之前它们叫「不支持 UnaryOp」，修之后叫「真值性不在子集内」。
假阻塞换成真阻塞，和 docstring 那次一模一样。

**零回归**：1190 条 FAILED 集合与基线逐条相同，passed 833 → 859（+26 ＝新测试文件）。

---

## 10. 更正二：镜像少记了两类函数体阻塞，Wall-B 相关的数全部偏高

第 9 节做完之后我去做「只差 N 个注解」的清单（第 11 节），
方法是**把补好注解的版本真的喂给分析器**。结果和镜像对不上：
镜像说 11 个只差注解，分析器只认 5 个。

去看那差的 6 个，暴露出镜像的**两处真漏**：

| 漏掉的规则 | 实例 | 分析器的拒绝码 |
|---|---|---|
| **自由变量**——函数体引用模块级全局 | `return z != mpc_zero` | `UNDECLARED_NAME:mpc_zero` |
| **字符串上的算术**——只有 `+` 在两个字符串上有定义 | `"(" * n` | `OPERAND_TYPE_MISMATCH:*:string:string` |

镜像把 `ast.Name` 一律当合法（从不检查它是否被参数或 `let` 绑定），
把 `* - / %` 一律当合法（从不看操作数类型）。两处都会**把不干净的函数体判成干净的**。

已修（并补上字符串排序：Java 按 UTF-16 码元、Python 按码点，分析器本来就拒）。
修完镜像与分析器验证结果**逐条一致：5 = 5，假阳 0，假阴 0**。

**受影响的已发布数字**：

| | 之前发布 | 修正后 |
|---|---|---|
| `body_clean`（过 B 墙） | 32 | **13** |
| **任何类型面放宽的上界** | 31 | **12** |
| `container_of_canonical_only` | 13 | **0** |
| `calls_only` | 27 | **18** |
| 「只差注解」 | 11 | **5** |

`max_gain_from_any_ir_widening = 108` 和 **9.15% 天花板不受影响**——它们建立在
`signature_clean` 上，而签名判定不碰函数体。

那 13 个 `def __dir__() -> list[str]` 现在**净收益是 0 而不是 13**：
它们 `return __all__`，`__all__` 是模块级全局，本来就过不了函数体闸门。
我当时说「真实收益 ≈ 1 个 idiom」，方向对，数字仍然偏高。

**这是同一把仪器的第二个缺陷。** 第一个（不递归调用接收者）让净收益偏高，
这一个让 Wall-B 判定偏松。两次都是**镜像比真分析器宽松**——
一个手写的近似永远会往「更宽松」的方向漂，因为漏掉一条规则＝少一个拒绝。
**结论：镜像只配当预筛，凡是要发布的数字必须由真分析器裁决。**

---

## 11. 「只差 N 个注解」清单：验证出来是 5 个，而且全部多解

工具：`engines/polyglot-route-engine/tools/near_miss_annotations.py`。
**不预测，验证**：枚举规范类型赋值 → 把补好注解的版本写出来 → 用真分析器重跑 →
只报告真的返回 READY 的那些。被报告的每一条都是**引擎接受过的证明**。

```
1,469 个候选
  108  在类型闸门之前就被挡住
  616  已标注但类型不在规范四类（类型面问题，不是缺注解）
  744  类型闸门 + 有未标注的槽位
         5  ONE_STEP_AWAY（已验证）
       577  补完注解仍被挡住
       162  槽位 > 3，没搜（4 槽 93 / 5 槽 31 / 6 槽 18 / 7 槽 16 / 更多 4）
    1  已经 READY
```

### 那 5 个是什么

| 函数 | 槽位 | 被接受的赋值数 |
|---|---|---|
| `sortedcontainers/sortedlist.py:1686 identity(value)` | 2 | **5** |
| `mpmath/libmp/libmpi.py:29 mpi_eq(s, t)` | 3 | **6** |
| `mpmath/libmp/libmpi.py:32 mpi_ne(s, t)` | 3 | **6** |
| `tabulate/__init__.py:209 _html_begin_table_without_header(colwidths_ignore, colaligns_ignore)` | 3 | **16** |
| `tabulate/__init__.py:1100 _padnone(ignore_width, s)` | 3 | **20** |

**没有一个有唯一解。** 看名字就知道为什么：`identity` 是恒等，
`colwidths_ignore` / `ignore_width` 连名字都写着这个参数没被用，
`_padnone` 直接返回 `s`。**参数要么没用、要么原样穿过，
所以代码根本不约束它的类型**——任何一个都行。

这有两个后果，都不利于我上一轮的建议：

1. **「补上注解」不是机械劳动。** 类型不是从代码推出来的，作者必须做决定，
   而这五个决定都不重要（转的是恒等函数和空壳）。
   **`TYPE:MISSING` 作为杠杆，实际价值接近 0。**
2. **它反过来给 `ir_local_bindings` 那条设计决定提供了新证据。**
   那条决定是「类型必须来自源语言的类型系统，不能来自分析器的猜测」。
   现在有了反例的正面版本：**在分析器最有可能推断成功的地方，答案不唯一**——
   真去推断就是在任意挑一个。

### 类型闸门后面真正的墙

577 个「补完注解仍被挡住」的下一道拒绝码：

```
234  PYTHON_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET
183  PYTHON_UNSUPPORTED_EXPRESSION
146  PYTHON_UNSUPPORTED_STATEMENT
  4  UNDECLARED_NAME        4  OPERAND_TYPE_MISMATCH
```

这是**第一次**看到类型墙后面的真实分布——之前的 58/25/21 只是那些
「第一个阻塞码不是类型」的函数。把注解全补上，577 个函数照样死，
而头号死因是未注解赋值和不支持的表达式，**不是类型面**。

### 结论没变，但更硬了

第 8 节的组合搜索说基石是 `CALL:user-function + TYPE:MISSING`(+44)。
现在知道 `TYPE:MISSING` 那半边**实际能兑现的只有 5 个平凡函数**，
所以真正的基石只剩一个：**跨单元调用的纯度证明**。
类型面那条路——不管是扩规范类型还是补注解——**实测都是接近 0**。
