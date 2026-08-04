# uir-java-python — 一条真正打穿的迁移路线

这不是规范包。这里的每一条语义规则都有可执行实现、有对照 `javac`/`java` 的差分证据、并且被变异实验证明"删掉它测试一定变红"。

```
Java 源码
  → tree-sitter 解析
  → Unified Semantic IR（带类型、带 Origin、内容寻址）
  → Python 代码生成（算术走 Java 语义运行时）
  → 差分执行：真编译真跑 Java，真跑 Python，逐字节比对
```

## 现在的真实数字

| 指标 | 数值 | 怎么来的 |
|---|---:|---|
| 单元 + 端到端测试 | **140** | `make uir-j2p-test` |
| 差分比较（Java vs Python 实跑） | **500** | 8 个语料程序 × 边界输入向量 |
| 变异实验 | **39/39 全部杀死** | `make uir-j2p-mutation` |
| elmos 仓库 884 个 Java 文件的降级率 | **39.7%**（351 个） | `make uir-j2p-survey` |
| 其中能生成 Python 的 | **4.8%**（42 个） | 同上 |
| 已实现路线 | **1 / 90** | `java → python` |

后两行是这个包最重要的两个数字。它们很难看，而且是真的。

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

一个悄悄跳过 lambda 的前端会产出"看起来完整"的翻译。那正是这套工程要防的事。`make uir-j2p-survey` 输出的 refusal 统计就是下一步该做什么的依据——不是凭感觉挑的。

## 已支持 / 已拒绝

**支持**：lambda（表达式体与块体、三种参数写法）、方法引用（`this::m`、`obj::m`、`Type::m`、`Type::new`）、JDK 函数式接口与项目自己声明的单抽象方法接口、class、record、static 嵌套类、enum 常量、字段/方法/构造器、int/long/short/byte/char/boolean/double、数组、if/while/do/for/foreach/switch(不含 fall-through)/try-catch-finally/throw、String 与 StringBuilder 常用方法、Integer/Long/Double/Math、文本块、转义、字符串拼接、复合赋值、自增自减（语句位置）。

**明确拒绝**（每一条都有测试）：`Foo.class`、record 紧凑构造器、指向本编译单元外类型的方法引用、try-with-resources、`==` 比较两个引用类型、函数式接口的 default 方法（`andThen`/`negate`）、带 default/static 方法的接口、varargs、泛型方法/泛型类声明、非静态内部类、`float`、带标签的 break/continue、switch fall-through、多维数组、表达式位置的赋值与 `++`、未声明 `toString`/`hashCode` 的类调用它们、会被二次求值的复合赋值目标。

## 用法

```bash
pip install -r requirements.txt          # tree_sitter, tree_sitter_java

python3 -m j2p.cli parse   Foo.java                    # 降级到 UIR，打印 digest
python3 -m j2p.cli emit    Foo.java --out Foo.py --source-map Foo.map.json
python3 -m j2p.cli diff    Foo.java --arity 2          # 真差分执行
python3 -m j2p.cli survey  /path/to/java/tree          # 覆盖率与拒绝统计
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
- **lambda 已经做了**（原本 178 个文件），降级率从 30.7% 提到 39.7%。没到我先前估的 50%——lambda 让路之后暴露出下一层瓶颈，实测排序是：`Foo.class` **158** 个文件、record 紧凑构造器 **129** 个、本单元外的方法引用 **85** 个。
- **差分只比对 stdout 和抛出的异常类型/消息**。时间、内存、线程交错没有比对。
- **语料是为这个引擎写的**，不是从客户仓库采样的。真实项目的差分需要真实项目。
- **JVM 侧 843 个 Java 文件本次未编译、未测试**。

## 目录

```
j2p/uir.py                  IR 定义、规范序列化、内容寻址、Java 类型提升规则
j2p/frontend/java.py        tree-sitter → UIR，fail-closed
j2p/emit/python.py          UIR → Python，fail-closed，带 source map
j2p/diff/harness.py         差分执行
j2p/cli.py                  parse / emit / diff / survey
runtime/j2p_runtime.py      Java 语义的 Python 实现（生成代码依赖它）
corpus/                     语义陷阱语料（溢出、负除、MIN_VALUE、Double.toString…）
tests/                      140 个测试
tools/mutation_check.py     39 个变异实验
tools/record_batch_evidence.py  接入 batch1-38 的证据生产者
```
