# Findings — 2026-08-19 · backlog 前提复核：三条定级错误，且错法一致

> 追加文件，不写入 `HANDOFF.md`。本文件不含任何认证声明。

## 起因

推进 `#5a 单文件多函数` 时，按惯例先审计再动手，结果发现**这条早就实现了**。
这是 9 条 backlog 里第三条前提出错的。三条错法完全一致，值得单独记下来。

## 三条错在哪

| 条目 | 我写的前提 | 实际 |
|---|---|---|
| `#3 React 分析器 READY` | 缺 React 前端，照着 TS 那份写即可 | React 组件在 `typed-pure-function-v1` 的 IR 里**无法表达**；真实现在 `component-dialect-engine`。再写一个是造第二套 |
| `#5b Go 控制流补全` | `else if` 与 `if init` 是一件事 | `else if` 是纯脱糖零改动；`if init` 要新增 IR 语句种类 + 13 个 emitter，是完全不同量级的两件事 |
| `#5a 单文件多函数` | 枚举支持了，卡在 assembly/equivalence 只处理单单元 | `discover_repository()` 1087–1109 行**已经**拆成 `WU-#####-F###` 独立单元 |

## 共同错法

**都是「只读了一层就下断言」。**

`#5a` 最典型：我读的是**单文件层** `discover_unit()`，它对多函数返回
`MULTIPLE_ELIGIBLE_FUNCTIONS_REQUIRE_EXPLICIT_PARTITION`，看起来就是「不支持」。
但**仓库层** `discover_repository()` 紧接着把这个中间结果拆开，每个 eligible 函数
生成一个独立 READY 单元。中间层的拒绝码不是系统的能力边界。

`#3` 同理：我读了 `emit()` 的报错和 `inventory.json` 的 `PENDING_ANALYZER`，
没读另一个引擎；`#5b` 同理：我读了两个相邻的拒绝码，没分辨它们背后的改动量级差了两个数量级。

## 哪些前提是可靠的

复核后，**基于「代码量/代码不存在」的前提全部成立**：

| 条目 | 复核结果 |
|---|---|
| `#5c` 跨文件调用 / `#5d` 异常 / `#5e` async / `#5f` 类 | ✅ 成立。`models.py` 白名单只有 `name / literal / binary / return / if`——**IR 里没有 `call`、没有赋值/声明、没有 try/throw、没有 await**。这些是结构性缺失，不是某层的拒绝码 |
| `#6` 执行平面 | ✅ 成立。`secure-execution-plane` 127 行 / `security` 36 / `network-policy` 84 / `secret` 186，全是决策器 |
| `#7` 六个骨架引擎 | ✅ 成立。`composite-engine` **0 行**，`ai-platform` / `operations-sre-itsm` 各 65 行 |
| `#8` 独立验证 | ✅ 成立。`certified_route_count: 0`，independent 与 local 均 `NOT_RUN` |

## 该记住的判据

- **「某处报了拒绝码」≠「系统不支持」**。拒绝码可能只是中间层在把决定交给上一层。
  下断言前要找到**最外层的消费者**，看它拿这个结果做了什么。
- **「代码不存在」是可靠前提**，「行为不支持」不是。前者可以数行数证伪，
  后者必须跑一遍或读完整条调用链。
- 顺带一个正面收获：`-F###` 拆分在语义上是**可证明**的而非权宜——
  IR 没有 `call` kind，所以同文件函数结构上不可能互相调用。

## 对 backlog 的处置

`#5a` 标为「已实现，前提有误」并写明原因；`#3`、`#5b` 此前已更正。
剩余条目（`#5c–#5g`、`#6`、`#7`、`#8`、`#9`）前提已逐条复核，成立。

**下一条真正该做的是 `#5d 异常/错误通道` 或 `#7 骨架引擎合并决策`** ——
前者是 IR 扩展（大件，需设计），后者需要先回答「这六个引擎是否该独立存在」。
