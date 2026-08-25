# Findings — 2026-08-19 · Go emitter 对任何 if/else 都发射语法错误的代码

> 追加文件，不写入 `HANDOFF.md`（沿用 `.ai/` 约定）。本文件不含任何认证声明。
> 发现于实现 `.ai/CODE_LEVEL_BACKLOG.md` 的 #5b（Go/Rust 前端提升 `else if`）过程中。

## 缺陷

`emitter.py::_statements` 对 `go` 与 `rust` 走同一分支，闭合花括号与 `else` 分两行发射：

```
if (score >= 90) {
    return 4
}
else {
    return 1
}
```

**这不是合法的 Go。** Go 规范（Semicolons）在闭合花括号后的换行处自动插入分号，
`else` 因此悬空：

```
./main.go:7:5: syntax error: unexpected keyword else, expected }
```

已用真实 `go build` 复现，并用同行写法对照通过。

## 影响面

全部 **12 条 `X → go` 路由**，只要源函数带 else 分支，发射产物就根本无法编译。
Rust 走同一分支但**不受影响**——Rust 没有分号插入规则，两行写法本来就合法。

## 为什么一直没被发现

路由语料里没有任何一个函数在 Go 作为**目标**时带 else 分支。
`typed-pure-function-v1` 的典型夹具是 `clamp` 那种「若干个提前 return，最后兜底 return」，
写不出 else。前端此前又拒绝 `else if`，进一步压低了产生 else 的概率。

**这条缺陷是被「加宽子集」这个动作挤出来的**，不是被测试挤出来的。
这是一个有用的信号：子集越窄，未被覆盖的发射路径就越多，而它们的错误不会以失败的形式出现，
只会以「从未被走到」的形式潜伏。**每加宽一次子集，都应当预期挖出这一类既有缺陷。**

## 修复

只改 Go：

```python
if language == "go":
    lines.append(f"{prefix}}} else {{")
else:
    lines.append(f"{prefix}}}")
    lines.append(f"{prefix}else {{")
```

**刻意不改 Rust。** Rust 当前输出合法，改它会改动发射字节，
从而作废每一个带 else 分支的 Rust 发射的内容寻址证据，而换不到任何正确性。
（`rustfmt` 确实偏好 `} else {`，但那是风格不是正确性。）
这个不对称是有意的，已由 `test_rust_emission_keeps_its_existing_else_shape` 锁住，
免得后来者「顺手统一一下」。

## 验证

- `tests/test_else_chain.py::test_go_emission_keeps_the_closing_brace_and_else_on_one_line`
  断言 `} else {` 存在且不存在裸 `else {` 行——纯 Python，任何机器可跑
- 云端用真实 `go build` 编译发射产物：通过
- 源 Go 与发射 Go 的差分：12 个输入（含 69/70/71、79/80/81、89/90/91 全部边界）行为完全一致

## 待办

Mac 上应当补一条**发射产物真编译**的回归，而不是只断言字符串形状。
本次云端已用真 `go build` 验证，但云端 Go 1.24.7 不是钉死的 1.25.0，
所以这条证据不能作为路由证据采信。
