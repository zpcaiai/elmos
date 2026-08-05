# uir-java-python — 一条真正打穿的迁移路线

这不是规范包。这里的每一条语义规则都有可执行实现、有对照 `javac`/`java` 的差分证据、并且被变异实验证明"删掉它测试一定变红"。

```
Java 源码
  → 全程序声明扫描（先建类型表）
  → tree-sitter 解析
  → Unified Semantic IR（带类型、带 Origin、内容寻址）
  → Python 代码生成（算术走 Java 语义运行时）
  → 差分执行：真编译真跑 Java，真跑 Python，逐字节比对
```

## 现在的真实数字

| 指标 | 数值 | 怎么来的 |
|---|---:|---|
| 单元 + 端到端测试 | **255** | `make uir-j2p-test` |
| 差分比较（Java vs Python 实跑） | **584** | 13 个单文件语料 + 1 个跨文件程序 × 边界输入向量 |
| 变异实验 | **98** | `make uir-j2p-mutation` |
| elmos 仓库 884 个 Java 文件**能降级到 UIR** | **94.9%**（839 个） | `make uir-j2p-survey` |
| 其中**能真正生成 Python** | **9.0%**（80 个） | 同上 |
| 已实现路线 | **1 / 90** | `java → python` |

**最后三行要一起读，尤其是中间那道鸿沟。** 前端能看懂 95% 的文件，生成器只能翻译 9%。

这不是矛盾，是两件不同的事：把 `Foo.class` 如实记进 IR 很容易（它就是一个类字面量节点），把它*翻译*成等价的 Python 不可能（反射语义复现不了）。所以前端理解它、生成器拒绝它。降级率衡量的是"读懂了多少"，生成率衡量的是"能保证行为一致地搬过去多少"。**后者才是迁移真正的进度。**

## 全程序符号解析：做完了，也没达到投影

上一轮测量得出的结论是：787 个生成失败的文件里 **742 个（94%）撞的是同一件事——引擎一次只解析一个文件**。一个调用如果指向别的文件里定义的类，它就没有类型，于是被拒。基于当时的障碍集，投影是"跨文件符号解析 + 构造器重载做完之后，137 个文件障碍清零，生成率 5.9% → 约 21%"。

两件事都做完了。真实结果：

| | 之前 | 之后 |
|---|---:|---:|
| 能生成 Python | 52（5.9%） | **80（9.0%）** |
| 只差 1 个能力 | 73 | 61 |
| 差 ≤2 个 | 143 | 128 |

**投影错了，而且错得有系统性原因。** 生成器在 survey 模式下遇到障碍会放占位符继续走，但**类声明层面**的拒绝（重载构造器、带 default 方法的接口、字段与方法重名）会在走进任何方法体之前就中止这个类——于是这些文件报出来的障碍数是个**下限，不是总数**。原来那 12 个"只差重载构造器"的文件，把重载构造器做完之后，露出来的是每个文件几十条别的障碍。

这个偏差现在被测出来并被排除了：survey 输出多了 `blockers_truncated`（本次 **50** 个文件），这些文件不再进入 `one_blocker_away` 和 `greedy_build_order`。上面"只差 1 个"从 104 降到 61，就是把这 50 个的虚假乐观扣掉的结果。

> README 上一版已经写了"投影不是测量"这句警告。警告是对的，但没有量化。现在量化了。

## 现在真正的瓶颈换了

跨文件解析做完之后，剩下的"unresolved receiver type"几乎全部指向 **JDK 类型**（`Map`、`Stream`、`Optional`、`Path`），不再是项目自己的类。按文件数排前面的是：

| 障碍 | 挡住的文件数 |
|---|---:|
| `Map.of` / `Set.of`（迭代顺序每次 JVM 运行都不同） | 222 / 132 |
| `Foo.class`（反射，复现不了） | 178 |
| JUnit 断言（`assertEquals`/`assertTrue`/…） | 173 / 130 |
| Stream（`stream`/`map`/`filter`/`toList`/`anyMatch`） | 149 / 106 / 96 / 128 / 109 |
| `String.getBytes` | 106 |

这是一份**库的清单**，不再是架构问题。其中 `Map.of` 一项就占了 `one_blocker_away` 的 38 个文件——它是下一个单点杠杆，但它不能简单地翻译成 dict：Java 的 `Map.of` 迭代顺序是每次运行随机化的，所以正确的做法是支持它、同时**拒绝对它的任何迭代**，而不是假装顺序一致。

## 跨文件是怎么做的

两遍。第一遍只扫声明、不进方法体、**不会失败**——一个方法体里有前端看不懂的构造，它的签名照样要进类型表，因为别的文件依赖它。第二遍拿着类型表逐文件降级和生成。

```
corpus/program/    Ledger.java  Rates.java  Money.java  Op.java  Adjust.java
```

这 5 个文件是跨文件差分语料：`Ledger` 里几乎每一行有意义的代码都跨文件——静态调用、静态字段、构造别的文件的类、record 工厂与访问器、enum 常量、别的文件声明的函数式接口上的 lambda、调用点按对方签名打包的 varargs、紧凑构造器抛出的异常。一次 `javac` 编译全部 5 个文件，一份索引翻译全部 5 个文件，两边跑同一个入口，逐字节比对。

同一个文件在**没有索引**时是 `TRANSLATION_REFUSED`，这条也有测试守着——否则"跨文件能力"就没有对照组。

生成的模块之间用 `import Other as _m_Other` 再取 `_m_Other.Other`，不是 `from Other import Other`。Java 里两个类互相调用是家常便饭，而 `from X import Y` 在这种环形依赖下会炸：后开始导入的那个模块，看到的对方还没执行到 class 语句。模块对象本身则是先进 `sys.modules` 的，属性到调用时才取，所以环没有问题。

## 顺手挖出来的四个真问题

这几条都不是设计出来的，是差分和变异逼出来的：

1. **字段和方法重名**。Java 里 `int factor;` 和 `int factor()` 分属两个命名空间，Python 只有一个——`self.factor = factor` 会把方法覆盖掉，调用时报一个离声明很远的 `TypeError`。跨文件差分第一次跑就撞上了。现在**拒绝**，全仓库里有 13 个文件命中。
2. **enum 常量原来生成成了序数**。`Op.ADD` 变成 `0`，于是 `System.out.println(Op.ADD)` 打印 `0`，Java 打印 `ADD`。这条规则此前**一条差分证据都没有**（语料里声明过 enum 但从没用过）。现在生成 `rt.JEnum('Op', 'ADD', 0)`：`name()`/`ordinal()`/`toString()` 各归各的，`==` 走单例身份比较——这正是 Java 的语义。
3. **`int[][]` 被降级成了 `int[]`**。tree-sitter 把两对方括号都放在同一个 `array_type` 的 `dimensions` 子节点里，顺着 `element` 递归就丢掉了一维。类型错了比拒绝更糟——它下面每一次下标都会被算成元素类型。现在前端直接拒绝。
4. **重载构造器**现在支持了，但只支持**参数个数互不相同**的那种。Java 按参数静态类型选构造器，Python 只有一个 `__init__`；参数个数运行时是有的，静态类型不是。所以按个数分派是精确的，个数相同的重载继续拒绝。字段初始化器在分派**之前**执行一次，因为 Java 就是在选中的构造器体之前跑它们。

## 为什么代码长这样

生成的 Python 不好看：

```python
# Java:  return a / b;
return rt.idiv('int', a, b)
```

因为 Python 的 `//` 向下取整（Java 向零截断），`%` 取除数符号（Java 取被除数符号），`+` 不会溢出（Java 的 int 会在 32 位回绕），`repr(1e7)` 是 `'10000000.0'`（Java 是 `1.0E7`）。每一条差异都会静默改变程序行为，而且都发生在迁移最不可能测到的输入上。

所以算术全部走 `runtime/j2p_runtime.py`。噪音就是重点。

## Lambda 的捕获是按值的

Java 只允许捕获 effectively final 的局部变量；Python 闭包按引用捕获，调用时才读值。普通情况两者一致，但在循环里每轮重新绑定的变量上不一致——不做处理的话，循环里造出来的每个 lambda 都会看到最后一个值：

```java
for (int v : vals) { made[i] = () -> v * 10; i++; }
```

Java 打印 `cap0=30 cap1=40 cap2=50`；朴素翻译成 Python 闭包打印 `cap0=50 cap1=50 cap2=50`。所以捕获一律编译成默认参数：

```python
lambda v=v: rt.jint(v * 10)
```

默认参数在 lambda 创建时求值一次，正好等于 Java 的捕获时机。这条规则由 M33 变异实验守住——删掉它，差分立刻报出上面那组数字。

## Fail closed

前端和生成器都**拒绝**它们看不懂的东西，带源码位置报错，绝不静默跳过：

```
Foo.java:41:18: unsupported Java construct: class_literal (as expression)
```

一个悄悄跳过 lambda 的前端会产出"看起来完整"的翻译。那正是这套工程要防的事。

索引让更多调用可解析，因此也让**拒绝**更重要了：一个能解析但翻错的调用，比一个被拒绝的调用糟糕得多。所以跨文件的每一条路径都对着扫描到的声明做检查——方法不存在、重载多于一个、静态/实例用反了、构造器参数个数对不上、静态字段其实不是静态的，全部拒绝并给出位置。

## 已支持 / 已拒绝

**支持**：跨文件类型解析（静态调用、静态字段、enum 常量、构造、实例方法、继承来的方法、record 访问器、别的文件声明的函数式接口、按对方签名打包的 varargs）、参数个数互不相同的重载构造器、try-with-resources（含 suppressed 语义）、泛型方法与泛型类（按 Java 的方式擦除）、varargs、record 紧凑构造器与显式规范构造器、switch 表达式（箭头式与 `yield` 式）、箭头式 switch 语句、lambda（表达式体与块体、三种参数写法）、方法引用（`this::m`、`obj::m`、`Type::m`、`Type::new`）、JDK 函数式接口与项目自己声明的单抽象方法接口、class、record、static 嵌套类、enum（常量为带名字的单例，`name`/`ordinal`/`toString`/`compareTo`，`==` 走身份比较）、字段/方法/构造器、int/long/short/byte/char/boolean/double、一维数组、if/while/do/for/foreach/switch(不含 fall-through)/try-catch-finally/throw、String 与 StringBuilder 常用方法、Integer/Long/Double/Math、`java.time`、文本块（含行连接符）、转义、字符串拼接、复合赋值、自增自减（语句位置）。

**运行时库**（每一条都有对照 `javac`/`java` 的差分证据）：`String` 的 `isBlank`/`strip`/`startsWith`/`endsWith`/`contains`/`replace`/`repeat`/`concat`/`equalsIgnoreCase`/`compareTo`/`hashCode`/`split`/`lastIndexOf`，`Objects` 的 `requireNonNull`/`equals`/`hash`/`toString`/`isNull`/`nonNull`，`Math` 的 `round`/`floorDiv`/`floorMod`/`signum`/`hypot`/`addExact`/`subtractExact`/`multiplyExact`/`toIntExact`，`Integer` 的 `toHexString`/`toBinaryString`/`bitCount`/`sum`/`max`/`min`，`List.of`（不可变）/`List.copyOf`/`ArrayList`，`JEnum`。

**明确拒绝**（每一条都有测试）：`Foo.class`、`Map.of`/`Set.of`/`HashMap` 等迭代顺序不确定的集合、Stream、JUnit 断言、字段与方法重名的类、参数个数相同的重载构造器、重载的 varargs 构造器、多维数组类型、跨文件的多重载方法、`this(...)`/`super(args)` 构造器委托、运行时没有对应实现的外部方法引用、无 default 的 switch 表达式、case 体不是单一表达式的 switch 表达式、会被重复求值的位置上需要提升语句的表达式、`==` 比较两个非 enum 引用类型、函数式接口的 default 方法（`andThen`/`negate`）、带 default/static 方法的接口、非静态内部类、`float`、带标签的 break/continue、switch fall-through、表达式位置的赋值与 `++`、未声明 `toString`/`hashCode` 的类调用它们、会被二次求值的复合赋值目标。

## 用法

```bash
pip install -r requirements.txt          # tree_sitter, tree_sitter_java

python3 -m j2p.cli parse   Foo.java                                # 降级到 UIR，打印 digest
python3 -m j2p.cli emit    Foo.java --index-root src --out Foo.py  # 带全程序索引生成
python3 -m j2p.cli emit    Foo.java --no-index                     # 单文件模式（对照组）
python3 -m j2p.cli diff    Foo.java --arity 2                      # 真差分执行
python3 -m j2p.cli survey  /path/to/java/tree                      # 覆盖率、拒绝统计、每文件障碍集
python3 -m j2p.cli survey  /path/to/java/tree --no-index           # 不带索引的对照测量
```

退出码：`0` 正常，`2` 差分不一致，`3` 拒绝翻译（这是正常结果，不是错误）。

## 接入 Batch 1–38 平台

`tools/record_batch_evidence.py` 是这套平台**第一个真实的 Evidence 生产者**。此前 batch1-38 运行时能存证据、验证据、判 Gate，但没有任何东西产生证据。

```bash
make uir-j2p-evidence WORKSPACE=/tmp/ws SOURCE=$(pwd)/engines/uir-java-python
```

记录的三条：

| Batch | Claim | Outcome |
|---|---|---|
| B02 | `required_outputs[0]` Differential execution runtime | **PASS** |
| B03 | `required_outputs[1]` Unified Semantic IR | **PASS** |
| B19 | `required_outputs[0]` 90 executable packs | **FAIL** |

B19 记成 FAIL 是刻意的。把 1 条路线记成 90 条的 PASS 很容易，Gate 也会给出一份很好看的结论。1 不是 90，所以证据写 FAIL，Gate 阻断——正是这个行为让另外两条记录有意义。

跑完之后 `gate --mode local` 三个 Batch 全部 `BLOCKED`，原因运行时自己列得很清楚：

- B01 没有任何证据（依赖不满足）
- B02 的 4 条 required_outputs 只有 1 条有生产者
- 没有任何**独立 Verifier** 复核过——按平台的角色隔离规则，Builder 产出的证据不能由 Builder 自己确认

这三条都是真的。

## 这份工作没有声称什么

- **89 条路线没有实现**。`route-pack-inventory` 里逐条列出。
- **另外九种语言没有前端**。B03 的 observation 里显式记为 `NOT_RUN`。
- **降级率 94.9% 里有很大一部分是"读懂但翻不动"**。别把它当成迁移进度，**9.0%** 才是。
- **上一轮的投影（21%）没有兑现，实测是 9.0%**。原因在上面写清楚了，偏差来源也已经被测量并从后续投影里排除。
- **`one_blocker_away` 和 `greedy_build_order` 仍然是投影**。表达式翻不动时会被占位符替换，消费这个值的构造可能就没被走到。类声明层面被截断的 50 个文件已经排除在外，但表达式层面的同类偏差还在。
- **索引不做重载决议**。同名多重载的跨文件调用一律拒绝，因为选哪一个需要前端并不总是有的实参类型。
- **差分只比对 stdout 和抛出的异常类型/消息**。时间、内存、线程交错没有比对。
- **语料是为这个引擎写的**，不是从客户仓库采样的。真实项目的差分需要真实项目。
- **JVM 侧 884 个 Java 文件本次未编译、未测试**——跨文件差分跑的是 `corpus/program/` 那 5 个文件。

## 目录

```
j2p/program.py              全程序声明扫描与符号索引（第一遍）
j2p/uir.py                  IR 定义、规范序列化、内容寻址、Java 类型提升规则
j2p/frontend/java.py        tree-sitter → UIR，fail-closed，带索引
j2p/emit/python.py          UIR → Python，fail-closed，带 source map 与跨模块导入
j2p/diff/harness.py         差分执行（单文件 run / 多文件 run_program）
j2p/cli.py                  parse / emit / diff / survey
runtime/j2p_errors.py       Java throwable 层级（运行时与 java.time 共用）
runtime/j2p_runtime.py      Java 语义的 Python 实现（生成代码依赖它）
runtime/j2p_time.py         java.time，按 Java 自己的 (秒, 纳秒) 模型实现
corpus/                     语义陷阱语料（溢出、负除、MIN_VALUE、Double.toString…）
corpus/program/             跨文件语料：5 个文件，一次编译一次翻译一起比对
tests/                      255 个测试
tools/mutation_check.py     98 个变异实验
tools/record_batch_evidence.py  接入 batch1-38 的证据生产者
```
