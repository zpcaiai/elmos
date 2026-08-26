# 剩下六条：两个真缺陷、一个功能缺口、一条测试写错了

2026-08-26 第二轮。承接 `FINDINGS-2026-08-26-generation-line-outage.md`
（那一轮把 project-synthesis 从 40 条失败降到 6 条）。这六条全部处理完。

## 摘要

| # | 症状 | 判定 | 归属 |
|---|---|---|---|
| 1-2 | 两条 probe 状态断言对不上 | **真缺陷：管道死锁** | `_probe` |
| 3-4 | `ELMOS_PROJECT_SYNTHESIS_COMMAND_TIMEOUT_SECONDS` 不生效 | 功能缺口 | `_run` |
| 5 | 依赖同步瞬时失败不重试 | 功能缺口 | `_run` |
| 6 | 归档根前缀 | **测试写错了，代码是对的** | 测试 |

**同一棵树前后：18 → 12 条失败，修好 6 条，新增 0 条；新增 17 条测试（136 → 153 passed）。**
云端剩的 12 条在 Mac 上本来就是绿的（Mac 那轮只有这 6 条），所以**你那边跑应该是 0**。

---

## 1-2. `_probe` 会把它探测的进程卡死（这条最重）

我原以为这两条只是"行为对不上"。真去看，是**管道缓冲区死锁**。

`_probe` 用 `stdout=subprocess.PIPE` 起子进程，然后**直到 `finally` 才读**——
也就是启动超时窗口跑完之后。而一个 OS 管道只有约 **64 KiB**。
启动阶段日志超过这个量的服务，会**永远阻塞在自己的 `write` 里**，
根本走不到 `serve_forever()`，于是 `/health` 一直没人应答，
探针在超时后报 **FAILED**。

**服务是好的，是探针把它卡死了，然后报告说它坏了。**

测试夹具正是照这个形状写的：

```python
sys.stdout.write("startup-log:" + "x" * 200000)   # 200 KB，远超 64 KiB
sys.stdout.flush()                                 # ← 卡在这里，永不返回
```

生产影响不是测试问题：**任何在启动期打日志超过 64 KiB 的生成服务
都会被误判为启动失败**，而且子进程被挂住。Gradle、dotnet restore、
npm install 这种启动噪音大的目标最容易撞上。

**修法**：开一个读取线程，在整个探测期间持续排空管道，只保留尾部
（`_PROBE_OUTPUT_TAIL_CHARACTERS = 6_000`，与原来 `[-6_000:]` 完全一致）。
`finally` 里有界 `join(timeout=5)`——卡住的读取线程不能反过来卡住探针。

**负向对照**（这条测试必须能红，否则它什么也没钉住）：把排空线程拆掉重跑，

```
2 failed, 15 passed in 60.46s
```

60 秒 = 两次 20 秒启动超时跑满，正是"卡死"的形状；装回去后 **0.9 秒全绿**。

## 3-4. 命令超时读不到环境变量

`verification.py` 里别的旋钮全都可以用环境变量配（`_LOCK_CACHE`、
`_GRADLE_PROXY`、`_TOOLCHAIN_ROOT`、`_GRADLE_USER_HOME`、`_GRADLE_REPOSITORY`），
唯独**决定"慢但健康的原生构建会不会被报成失败"的那个超时**是写死的形参默认值。

修法：环境变量只提供**默认值**——显式传 `timeout_seconds=` 的调用方
（已有若干处传 30）不受影响。范围校验仍然是**唯一一道闸门**，
所以配 901 和传 901 一样，在**执行任何命令之前**就
`COMMAND_TIMEOUT_OUT_OF_RANGE` 失败关闭。非数字另给
`COMMAND_TIMEOUT_NOT_AN_INTEGER`。

## 5. 锁定依赖同步的一次重试

一次网络抖动会让整个验证失败。重试**刻意收得很窄**：

- 只对 `uv sync --locked`——`--locked` 的含义是"要么严格按已提交的锁文件解析，
  要么失败"，所以**重跑一次不可能装出不一样的东西**。这正是这里能安全重试、
  而别处不能的原因。
- 只在失败文本是**取包失败**时（`failed to fetch` / `failed to download` /
  `error sending request` / `connection reset` / DNS 临时失败）。
- **最多一次**——网络断了就是断了，无限重试是把失败变成挂起。
- **`TimeoutExpired` 之后绝不重试**：硬超时是预算决定不是抖动，
  哪怕工具自己的消息里写着 "timed out"。
- 编译失败是确定性的，永不重试。

绿了也要看得出来：输出里留 `TRANSIENT_DEPENDENCY_FETCH_RETRY:1/1` 和第一次的失败文本，
**一次靠重试才通过的结果，不能和一次就过的长得一模一样**。

## 6. 归档根前缀：测试错了，代码对

`test_markdown_document_pack_is_in_the_download_archive` 断言归档条目前缀是
**输出目录名**（`generated-task/`）。实际是**项目名**（`notes-docs-service/`）。

代码是对的，而且是刻意设计的：

- `cli._archive_workspace` 从 blueprint 读 `project.name`，
  并用身份正则校验，配专属错误码 `ARCHIVE_PROJECT_IDENTITY_INVALID`；
- 同一套件里**已经通过**的 `test_archive_includes_verified_lockfiles`
  钉的正是这条规则：工作目录叫 `workspace`，断言却是
  `commerce-service/python/uv.lock`；
- 语义上也该如此：解压出来的交付物应该以项目命名，
  而不是以生成它的那个临时目录命名。

所以改测试，并把理由写进断言旁边——否则下一个人会以为是代码错了又改回去。

## 方法上的两条

- **"行为对不上"不等于"实现有小 bug"。** 这两条 probe 我差点归成参数问题，
  真去读 `_probe` 的进程生命周期才看到死锁。**看到状态不符先问：
  被测对象到底跑起来没有。**
- **回归测试必须做负向对照。** 那两条死锁测试如果不拆掉修复验一遍，
  我无法知道它们是不是恒绿。拆掉一验：60 秒、两条红——它们是有牙齿的。
