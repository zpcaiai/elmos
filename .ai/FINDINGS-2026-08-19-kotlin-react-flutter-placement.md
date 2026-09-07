# Findings — 2026-08-19 · kotlin / react / flutter 在路由矩阵里的位置是错的

> 追加文件，不写入 `HANDOFF.md`。本文件不含任何认证声明。
> 产生于执行 `.ai/CODE_LEVEL_BACKLOG.md` #3（React 分析器）的**前置判断**。

## 实测事实

`inventory.json` 只标了这三种语言 `PENDING_ANALYZER`（不能作**源**）。实测发现它们**也不能作目标**：

```
可发射 (10/13): java python csharp typescript go rust cpp objc swift php
不可发射:
   kotlin     RouteError: IDENTIFIER_POLICY_UNSUPPORTED:kotlin
   react      RouteError: IDENTIFIER_POLICY_UNSUPPORTED:react
   flutter    RouteError: IDENTIFIER_POLICY_UNSUPPORTED:flutter
```

即：**三种语言在两个方向上都不通**。`identifier_hygiene._DIALECT` / `_RESERVED` / `_FORBIDDEN`
三张表里根本没有它们的条目。

## 路由账目（与 inventory 完全吻合）

| | 条数 |
|---|---:|
| 13 语言全矩阵 | 156 |
| 10 个真实语言 × 9 | **90** ← `limited_route_count` |
| 触及 kotlin/react/flutter 的 | **66** ← `research_route_count` |
| ├ 触及 react 或 flutter | 46 |
| └ 仅触及 kotlin | 20 |

数字对得上，说明仓库**已经诚实地**把这 66 条归为 `research`，不是隐瞒。
但「13 语言矩阵」这个说法在读者那里会被理解成 13 种都能跑，而实际只有 10 种。

## 判断：react 与 flutter 不属于这个 profile

`polyglot-route-engine` 的 IR 是：

```
SemanticIR { functions: [{ name, parameters, return_type, body: [return | if] }] }
CANONICAL_TYPES = {integer, number, boolean, string}
```

**React 组件在这套 IR 里根本无法表达**——没有 JSX、没有 props/state、没有节点树，
类型格里也没有任何能承载它们的东西。Flutter 同理。

而 React 的真实实现**已经存在于另一个引擎**：`engines/component-dialect-engine`

```
src/parsers/  : react.ts angular.ts svelte.ts vue2.ts vue3.ts miniprogram.ts expressions.ts
src/emitters/ : react.ts react-native.ts flutter.ts arkui.ts angular.ts svelte.ts vue2.ts vue3.ts miniprogram.ts
IR            : ComponentDef { name, props: PropDef[], state: StateDef[], root: Node }
```

10 个框架、54 条方向全部真转写、发射由目标框架**真编译器**回验、五端真 SSR 渲染比对、
`certified-component-v1` 子集内 `REPOSITORY_CLOSED`、对 `apps/web-console` 实测覆盖 8/33。

**结论：给 polyglot-route-engine 再写一个 React 前端是造第二套。**
两套 IR 服务两件不同的事，不该在同一个矩阵里并列成「语言」。

## 判断：kotlin 属于这个 profile

Kotlin 有普通的具名类型化函数（`fun clamp(v: Int, lo: Int, hi: Int): Int`），
在 `typed-pure-function-v1` 里可直接表达。它不是归属错误，是**单纯没实现**。

而且两侧的阻塞程度不同：

| 方向 | 需要什么 | 阻塞状态 |
|---|---|---|
| kotlin 作**目标**（发射） | `identifier_hygiene` 三张表加 kotlin 条目 + `emitter.py` 的 kotlin 分支 + `types.py` 类型映射 | **不阻塞**——纯 Python，不需要 kotlinc |
| kotlin 作**源**（提升） | `native/kotlin/` 分析器 + 精确工具链纳管 | 阻塞——Mac 上无 kotlinc，且 symlink-free 树契约拒绝 Homebrew 安装 |
| kotlin 行为验证 | `validation.py` 的 kotlin harness | 阻塞——同上 |

**所以「kotlin 作目标」是当前唯一可以立刻开工、且能真正减少 impossible 路由数的一项**，
做完可让 10 条 `X → kotlin` 从两端不通变成目标端可发射。

## 建议的处置

1. **react / flutter**：从 `COMPLETE_MATRIX_LANGUAGES` 移出，矩阵回到 11 语言 / 110 条路由。
   它们保留在 `component-dialect-engine` 里，那里才是真实现。
   若要保留对外「支持 React」的说法，应当指向 component-dialect-engine 而不是路由矩阵。
   —— **这是产品决定，不是纯技术决定，需要你拍板**，因为它会改变对外的语言数字。
2. **kotlin**：保留在矩阵里，先做目标侧（不阻塞），源侧等 kotlinc 纳管。
3. 无论 1 怎么定，`README` 的「13 语言」表述都应加一句：其中 10 种双向可用，
   3 种为 `research`（两端均未实现）。现在这句话只在 `inventory.json` 的字段里，README 读不到。

## 与 backlog 的关系

原 #3「React 分析器 `READY`」**定级错误**，已改为 `NEEDS-DECISION`。
原 #2 Kotlin 拆成 #2a（目标侧，`READY`）与 #2b（源侧，`BLOCKED`）。
原 #4 Flutter 与 #3 合并处置。
