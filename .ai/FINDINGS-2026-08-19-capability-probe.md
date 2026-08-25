# Findings — 2026-08-19 · 可执行能力探针：把「什么能跑」变成一条命令

> 追加文件，不写入 `HANDOFF.md`。本文件不含任何认证声明。

## 为什么做这个，而不是继续做 backlog 下一条

一天之内出现的问题，根因是同一个：

| 现象 | 根因 |
|---|---|
| backlog 9 条里 3 条前提错（#3、#5a、#5b） | 靠读代码推断能力 |
| Kotlin 发射侧被两个会话各实现一遍 | 没有权威的「已实现」清单 |
| `#10 CAS` 标 DONE 但零调用者 | 「写完了」被当成「生效了」 |
| 64-Skill 包被评估两次，第一次口径还错了 | 同上 |

仓库对路由有铁律：`filePresenceIsEvidence: false`。
**但它对自己的能力清单没有这条铁律。** 每个「支不支持 X」都靠读代码回答，
而读代码有一个特定的失效模式，一下午产出了三个错误答案：

> **中间层的拒绝码不是系统的边界。**

`discover_unit()` 对多函数文件返回 `MULTIPLE_ELIGIBLE_FUNCTIONS_REQUIRE_EXPLICIT_PARTITION`，
读起来就是「不支持」。`discover_repository()` 紧接着把同一个结果拆成每函数一个 READY 单元。
两句都是真的，只有第二句是边界。不跑一遍，无法知道自己在看哪一层。

## 探针做什么

`tools/capability_probe.py` —— **从不推断**，每一项都调真实入口并记录返回。

```bash
make capability-probe          # 表格
make capability-probe-json     # 机器可读
```

在仓库根目录写 `uv run --locked python tools/...` 会**静默失败**：
`--locked` 只在引擎自己的 project 内生效，`uv` 于是回落到 PATH 上的 python，
而那个 python 找不到这个文件。已加 `make` 目标，不必再记路径。

四组探测：**发射**（每语言能否作目标）、**模块枚举**（文件闭包所依赖的）、
**提升**（每语言能否作源）、**子集边界**（IR 对哪些构造没有表示）。

## 最要紧的一条设计：工具链缺失 ≠ 能力缺失

`analyze()` 在分派前先验精确工具链，所以没有 Apple clang 21 或 Swift 6.3.3 的机器
拿到的是 `EXACT_TOOLCHAIN_UNAVAILABLE`——**这跟能力存不存在毫无关系**。
把「这里测不了」塌缩成「不支持」，和把中间层拒绝码塌缩成边界是同一类错误。
所以裁决词表把它们分开，且是封闭的：

```
SUPPORTED      跑了，成功
REJECTED:code  跑了，拒绝 —— 真实边界
BY_DESIGN:code 跑了，拒绝，但那是路由决定（如 Python 走 CPython ast 另一条枚举路径）
NOT_PROBED     这台机器跑不了 —— 不是能力结论
ERROR:code     意外 —— 视为探针缺陷直到解释清楚
```

**`NOT_PROBED` 是「去有工具链的机器上重跑」的指令，永远不是答案。**

## 首跑结果（云端；Mac 上会填满 NOT_PROBED 那两列）

发射侧 13 语言里 **11 个 SUPPORTED**（含 Kotlin，确认另一会话的实现有效），
`react` / `flutter` 为 `REJECTED:IDENTIFIER_POLICY_UNSUPPORTED`。

IR 子集边界，逐项实测而非读 `models.py` 推断：

| 构造 | 结果 |
|---|---|
| `call` / `attribute_access` / `subscript` | `REJECTED:PYTHON_UNSUPPORTED_EXPRESSION` |
| `assignment` / `exception` / `loop` | `REJECTED:PYTHON_UNSUPPORTED_STATEMENT` |
| `async` | `REJECTED:ASYNC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET` |
| `class_declared_beside_function` | `SUPPORTED`（文件闭包的事，不是提升器的事） |

**backlog 里每一条「加宽子集」都压在这张表上**，现在它有执行证据了。

## 探针第一次跑就抓到自己的两个缺陷

写出来的东西第一次运行就找出自己两处不准，值得记下来：

1. 原来有个构造叫 `class`，报 `SUPPORTED`——**读起来像「对象可用」**。
   实际夹具把类放在模块层，测的不是标签说的东西。已拆成
   `class_declared_beside_function`（确为 SUPPORTED）与 `attribute_access`（REJECTED）。
2. Python 的模块枚举报 `REJECTED`，但那是**有意的路由决定**。
   已加 `BY_DESIGN` 一档——否则探针会亲手复制它要消灭的那种混淆。

## 测试

`tests/test_capability_probe.py` 15 条，**纯 Python 任何机器可跑**。锁住的是让输出可信的那部分：

- 词表封闭
- **任何 `ERROR:` 行都是探针缺陷，不是发现，不许出厂**
- 发射列在任何机器上都必须有结论（纯 Python，出现 `NOT_PROBED` 就是探针 bug）
- 工具链缺失必须归到 `NOT_PROBED`，域拒绝必须归到 `REJECTED`——直接对分类函数断言

## 建议怎么用

1. **动手前先跑一遍。** 这一下午三次「实现了才发现早就有」都能被它挡掉。
2. **两个会话共用它。** 事实层面撞不了车；分歧只会出现在该分歧的地方。
3. **Mac 上跑一次并把 JSON 存进 `.ai/`**，那才是完整矩阵——云端只能填发射列和子集边界列。
4. backlog 新增条目时附上探针输出作为依据，而不是只写结论。

## 局限

- `kotlin` / `react` / `flutter` 的提升列是 `NOT_PROBED:NO_FIXTURE`——**没有分析器，不是没测**。
  等 kotlinc 纳管后补 Kotlin 夹具即可。
- 子集边界用 Python 作代表源。边界本身是 IR 层的（白名单对所有语言相同），
  但个别语言的**额外**限制（如 `GO_IF_INIT_OUTSIDE_CERTIFIED_SUBSET`）不在这张表里。
- 探针只覆盖 `polyglot-route-engine`。`modules/`、其余 engine 需要各自的探针——
  `#10 CAS 未接调用链` 正是一个没有探针就看不见的例子。
