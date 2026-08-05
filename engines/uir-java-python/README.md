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
| 单元 + 端到端测试 | **323** | `make uir-j2p-test` |
| 差分比较（Java vs Python 实跑） | **636** | 17 个单文件语料 + 1 个跨文件程序 × 边界输入向量 |
| 变异实验 | **137** | `make uir-j2p-mutation` |
| elmos 仓库 884 个 Java 文件**能降级到 UIR** | **94.9%**（839 个） | `make uir-j2p-survey` |
| 其中**能真正生成 Python** | **20.5%**（181 个） | 同上 |
| 已实现路线 | **1 / 90** | `java → python` |

**最后三行要一起读，尤其是中间那道鸿沟。** 前端能看懂 95% 的文件，生成器只能翻译 20%。

这不是矛盾，是两件不同的事：把 `Foo.class` 如实记进 IR 很容易（它就是一个类字面量节点），把它*翻译*成等价的 Python 不可能（反射语义复现不了）。所以前端理解它、生成器拒绝它。降级率衡量的是"读懂了多少"，生成率衡量的是"能保证行为一致地搬过去多少"。**后者才是迁移真正的进度。**

## 全程序符号解析：做完了，也没达到投影

上一轮测量得出的结论是：787 个生成失败的文件里 **742 个（94%）撞的是同一件事——引擎一次只解析一个文件**。一个调用如果指向别的文件里定义的类，它就没有类型，于是被拒。基于当时的障碍集，投影是"跨文件符号解析 + 构造器重载做完之后，137 个文件障碍清零，生成率 5.9% → 约 21%"。

两件事都做完了。真实结果：

| | 单文件 | + 全程序解析 | + 集合与 Stream | + 正则与嵌套静态 | + var/作用域/charset |
|---|---:|---:|---:|---:|---:|
| 能生成 Python | 52（5.9%） | 80（9.0%） | 144（16.3%） | 166（18.8%） | **181（20.5%）** |
| 只差 1 个能力 | 73 | 61 | 48 | 44 | 46 |
| 差 ≤2 个 | 143 | 128 | 120 | 115 | 116 |

同一份代码关掉全程序索引（`--no-index`，`make uir-j2p-survey-noindex`）现在是 **87** 个文件。这是对照组：库的工作对单文件模式同样有用，两者相差的 94 个文件是跨文件解析自己挣来的。

**投影错了，而且错得有系统性原因。** 生成器在 survey 模式下遇到障碍会放占位符继续走，但**类声明层面**的拒绝（重载构造器、带 default 方法的接口、字段与方法重名）会在走进任何方法体之前就中止这个类——于是这些文件报出来的障碍数是个**下限，不是总数**。原来那 12 个"只差重载构造器"的文件，把重载构造器做完之后，露出来的是每个文件几十条别的障碍。

这个偏差现在被测出来并被排除了：survey 输出多了 `blockers_truncated`（本次 **50** 个文件），这些文件不再进入 `one_blocker_away` 和 `greedy_build_order`。上面"只差 1 个"从 104 降到 61，就是把这 50 个的虚假乐观扣掉的结果。

> README 上一版已经写了"投影不是测量"这句警告。警告是对的，但没有量化。现在量化了。

## 集合与 Stream：整件事只关于"迭代顺序"

跨文件解析做完之后瓶颈换成了库，排第一的是 `Map.of`（222 个文件）和 Stream（`stream` 149、`toList` 128、`anyMatch` 109、`map` 106、`filter` 96）。这些原来是**整类拒绝**的，理由写在拒绝信息里：Java 不指定 `Map.of`/`Set.of`/`HashMap` 的迭代顺序，而且 `of` 工厂**每次 JVM 运行都重新随机化**——同一个 Java 程序两次运行打印出来的顺序都可能不一样。

整类拒绝是对的，但太粗。真正的分界不在"集合"，而在"这次观测能不能看见顺序"：

| 观测 | 能看见顺序吗 | 处理 |
|---|---|---|
| `get` `containsKey` `size` `isEmpty` `equals` | 不能 | **翻译**，精确 |
| `keySet` `entrySet` `values` `toString`、for-each、`println(map)` | 能 | **拒绝**（除非声明类型是 LinkedHashMap/TreeMap/LinkedHashSet/TreeSet） |
| `stream().anyMatch/allMatch/count/map/filter/distinct` | 不能 | **翻译**，任何来源都行 |
| `stream().toList/findFirst/forEach/reduce/limit/skip` | 能 | 只有来源有序时才翻译；`sorted()` 会**建立**顺序，所以它之后就允许了 |

这正好对应 Java 自己的 ordered / unordered stream 概念。`set.stream().anyMatch(p)` 无论顺序答案都一样，`set.stream().toList()` 不是——所以前者放行，后者拒绝，拒绝信息会告诉你 `sorted()` 或者换个 List 来源。

判定用的是**声明类型**，这是保守的：一个 `LinkedHashMap` 存在声明为 `Map` 的变量里也会被拒绝，因为生成器看不穿声明。

`Collectors.toSet`/`toMap` 也拒绝——它们产出 HashSet/HashMap，顺序 Java 同样不指定，实现它就等于替 Java 编造一个顺序。

顺带修掉的一个真陷阱：**Map 的键相等性是 Java 的，不是 Python 的**。Python 里 `True == 1`、`1.0 == 1` 且哈希相同；Java 里 `Boolean` 键和 `Integer` 键永远不相等，`Integer` 和 `Double` 也不。直接用 Python dict 会把三个条目合成一个。所以键统一包一层 `_JKey`，把 Java 的类型敏感相等性带进哈希里。语料 `corpus/Maps.java` 最后三行就是这个，差分实跑证明的。

## JUnit 断言没有做，理由

`assertEquals`/`assertTrue`/`assertFalse`/`assertThrows` 按 `files_blocked_by_capability` 排在 173/130/109/87，看起来是大头。**没做，因为这个容器里拿不到 JUnit 5 的 API jar**（Maven Central 被挡，本地只有 junit-4 和 platform-launcher，没有 jupiter-api）。没有它，那些测试文件 `javac` 编译不了，也就没有独立的对照物。

自己写一个 `Assertions` 桩来跑差分是**循环论证**：比对的两边都是我定义的语义，证不出任何东西。这套工程的规矩是每条规则都要有对照 `javac`/`java` 的证据，所以这一块记为未做，而不是做成没有证据的功能。

## 正则：只做两边确实一致的那个子集

`String.matches` 原来整条拒绝，理由是"Java 的正则方言不是 Python 的"。这话对，但仓库里实际出现的模式几乎全在两边一致的范围内——`[0-9a-f]{64}`、`^[A-Za-z0-9._:-]{1,64}$`、`\d{6}`、`(?:refs/(?:heads|tags)/)?[A-Za-z0-9._/-]+` 这些。

所以改成：**在生成时**翻译并校验模式，超出已验证子集的构造按名字拒绝，带源码位置。有三处差异是静默的，全部处理了：

| 差异 | Java | Python | 处理 |
|---|---|---|---|
| `.` | 排除 5 个行终止符（`\n \r \u0085 \u2028 \u2029`） | 只排除 `\n` | 重写成显式否定字符类 |
| `\d` `\w` `\s` `\b` | 默认只认 ASCII | 默认 Unicode 感知 | 编译时加 `re.ASCII` |
| `matches()` | 隐式两端锚定 | `re.match` 只匹配前缀 | 用 `re.fullmatch` |

第二条最阴：`"٣٤٥".matches("\\d{3}")` 在 Java 是 `false`，不加 `re.ASCII` 的 Python 是 `true`。`corpus/Regex.java` 的输入向量里就有这串阿拉伯-印度数字，还有带尾随换行的字符串——22 组向量逐字节对上。

拒绝的：`\p{...}`（两边类目名不同）、占有量词（Python 没有对应形式）、`(?<name>)` 命名组（Python 拼作 `(?P<name>)`）、`[a&&b]` 类交集、`\Q...\E`、`\h \R \z` 这些 Java 专有转义、内联标志 `(?i)`（Java 默认只折 ASCII 大小写）、反向引用、非字面量模式（校验必须在生成时做，模式就得那时候知道）。

## 嵌套类调用外层静态方法

这是当时 `one_blocker_away` 里最大的一项（15 个文件）。Java 允许嵌套类型不加限定就调用外层类的静态方法：

```java
public record EstateProfile(String estateId, ...) {
    public EstateProfile { require(estateId, "estateId"); }   // require 在外层类上
}
```

生成器把嵌套类型摊平成各自独立的 Python 类，所以 Java 省略掉的那个限定得补回来（`R.require(...)`）。两个候选就拒绝——Java 靠词法嵌套决定选哪个，摊平后的 IR 已经不带这个信息了，猜就是掷硬币。

## var、文件作用域、charset

这三条都是"类型解析"的收尾，加起来把 166 推到 181：

**`var` 不是类型。** 它原来被降级成一个名叫 `var` 的类，于是变量的每一次使用都是"无法解析的接收者"——survey 里到处是 `ClassType(name='var')`。现在 `var x = expr` 取初始化器的类型，`for (var w : items)` 取被迭代对象的元素类型，`List.of("a")` 这类工厂也带上从实参推出来的元素类型（实参类型不一致时不硬认，Java 那里是 `List<Object>`）。

**一个文件自己的声明优先于全局表。** 原来 `_lookup` 直接查全局符号表，于是 `Status`、`Decision`、`Result` 这些重名的嵌套类型因为"全局不唯一"而解析不出来——**恰恰是在声明它们的那个文件里**。现在先查本文件，再查全局。这一条改动单独就多了 11 个文件，而且它是正确性修复不是功能。

**`String.getBytes`。** 带 `StandardCharsets` 常量的版本可以精确复现，不带参数的用平台默认字符集（同一个程序在不同机器上产出不同字节），拒绝。差分立刻抓出一条我没想到的：**Java 的 `getBytes(Charset)` 从不抛异常**——编码器设成 REPLACE，字符表示不了就变成 `?`；Python 的 `encode()` 直接抛。`"héllo"` 转 ASCII 就是这个。另外 Java 的 byte 是**有符号**的，UTF-8 续字节 `0xC3` 要报成 `-61`。

**跨文件重载现在按参数个数选**，和构造器同一条规则：个数运行时有，静态类型没有。个数相同的重载继续拒绝。

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

**运行时库**（每一条都有对照 `javac`/`java` 的差分证据）：`String` 的 `isBlank`/`strip`/`startsWith`/`endsWith`/`contains`/`replace`/`repeat`/`concat`/`equalsIgnoreCase`/`compareTo`/`hashCode`/`split`/`lastIndexOf`，`Objects` 的 `requireNonNull`/`equals`/`hash`/`toString`/`isNull`/`nonNull`，`Math` 的 `round`/`floorDiv`/`floorMod`/`signum`/`hypot`/`addExact`/`subtractExact`/`multiplyExact`/`toIntExact`，`Integer` 的 `toHexString`/`toBinaryString`/`bitCount`/`sum`/`max`/`min`，`List.of`（不可变）/`List.copyOf`/`ArrayList`，`JEnum`，`Map`/`Set`（`Map.of`/`Set.of`/`copyOf`/`entry`/`ofEntries`、`HashMap`/`LinkedHashMap`/`TreeMap`/`HashSet`/`LinkedHashSet`/`TreeSet`，键相等性按 Java 的类型敏感规则），`Stream`（`map`/`filter`/`flatMap`/`distinct`/`sorted`/`limit`/`skip`/`anyMatch`/`allMatch`/`noneMatch`/`count`/`sum`/`reduce`/`toList`/`findFirst`/`forEach`/`max`/`min`），`Optional`，`Collectors` 的 `toList`/`toUnmodifiableList`/`joining`/`counting`，`Boolean.TRUE`/`FALSE`。

**明确拒绝**（每一条都有测试）：`Foo.class`、**对顺序不确定的集合的任何顺序观测**（`keySet`/`entrySet`/`values`/`toString`/for-each/`println`，以及 `toList`/`findFirst`/`forEach`/`reduce` 这类顺序敏感的 Stream 终结操作）、`Collectors.toSet`/`toMap`、手写 `Collector`、JUnit 断言（没有独立对照物，见上）、字段与方法重名的类、参数个数相同的重载构造器、重载的 varargs 构造器、多维数组类型、跨文件的多重载方法、`this(...)`/`super(args)` 构造器委托、运行时没有对应实现的外部方法引用、无 default 的 switch 表达式、case 体不是单一表达式的 switch 表达式、会被重复求值的位置上需要提升语句的表达式、`==` 比较两个非 enum 引用类型、函数式接口的 default 方法（`andThen`/`negate`）、带 default/static 方法的接口、非静态内部类、`float`、带标签的 break/continue、switch fall-through、表达式位置的赋值与 `++`、未声明 `toString`/`hashCode` 的类调用它们、会被二次求值的复合赋值目标。

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
- **降级率 94.9% 里有很大一部分是"读懂但翻不动"**。别把它当成迁移进度，**20.5%** 才是。
- **上一轮的投影（21%）在只做跨文件解析时没有兑现，实测 9.0%**；把集合、Stream、正则子集、嵌套静态调用、var 与文件作用域都做掉之后是 20.5%。偏差来源已经被测量并从后续投影里排除。
- **JUnit 断言没有做**，理由是拿不到独立对照物，不是难度问题。见上一节。
- **顺序判定用声明类型，是保守的**。声明为 `Map` 的 `LinkedHashMap` 会被拒绝迭代，虽然它其实有序。
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
corpus/                     语义陷阱语料（溢出、负除、MIN_VALUE、Double.toString、集合键相等性、Stream 顺序…）
corpus/program/             跨文件语料：5 个文件，一次编译一次翻译一起比对
j2p/emit/regex.py           Java 正则 → Python 正则，已验证子集，其余按名字拒绝
tests/                      323 个测试
tools/mutation_check.py     137 个变异实验
tools/record_batch_evidence.py  接入 batch1-38 的证据生产者
```
