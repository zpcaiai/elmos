# 四线程产出交叉核对（主会话，2026-09-01 04:1x UTC）

四条并行线程（C2+C3 / gate-triage / A4+B4 / B3）返回后，主会话逐条复核。
本文件**只记我自己跑过的命令**，线程自己的证据在各自的 FINDINGS 里。

## 0. 结论

1. **两条线程给出的 5 语料合计覆盖率不一致，已定位并判明谁对。**
2. `gate-triage.sh` **不在仓库树里** —— 两处项目记忆需要更正。
3. **B1 的 `NEEDS-DECISION` 已过期**，两条线程独立实测确认。
4. **有第三个会话正在并行写入**（不是这四条线程），落点与线程 2 同目录。

---

## 1. 覆盖率数字冲突 —— `2644` 对，`2709` 错

| 来源 | schema 覆盖率 | 分母 |
| --- | --- | --- |
| `FINDINGS-2026-09-01-a4-b4.md` | 75.95% | 2644 |
| `FINDINGS-2026-09-01-b3.md` | 75.78% | 2709 |

同一天、同一棵树、相隔约 30 分钟，差 65 条。当场数：

```
$ ls engines/build-cache-engine/migrations/postgres/*.sql | wc -l
9
$ find engines/build-cache-engine/migrations -name '*.sql' | wc -l
16
$ ls -d engines/build-cache-engine/migrations/*
engines/build-cache-engine/migrations/postgres
engines/build-cache-engine/migrations/sqlite
```

**b3 把 `migrations/` 整个目录递归进来了，多带了 7 个 sqlite 文件**，而 2026-08-21 的
基线口径是 `migrations/postgres`。所以：

- **`75.95%` (2008/2644) 是与 08-21 基线可比的那个**；
- **`75.78%` (2053/2709) 口径错，不可引用** —— 它还把 sqlite DDL 当 postgres 方言扫了。

**但 b3 的 44 条不受影响**：该报告里 `sqlite` 出现 0 次，且它自己记的
`elmos-build-cache-migrations` PARSE_FAILED 是 `0 → 0`。污染只进了分母，没进分子。

⚠️ 两个数字**都不能当作 B 线成绩**：a4-b4 自己也写了，38.74%→75.95% 同时含
「语料长大」（persistence 67→81，当场数确认今天是 **81**）和「引擎被另一条线大改」
两个变量，没做四引擎零回归对比，也没跑真库。

## 2. `gate-triage.sh` 不存在 —— 项目记忆要更正

```
$ find .ai scripts tools .github -maxdepth 4 -name 'gate-triage*'
(无输出，rc=1)
$ ls *.sh          # 仓库根
(无输出)
```

项目记忆 `gate_triage_script_pitfalls.md` 记着「已修」的三处，**在这棵树上无从复核**。
它要么只存在于 Mac 本地、要么已被删。线程 2 因此转去扫同类脚本，
在 `verify-on-mac.sh` 里找到**同一个 `grep` 缺 `-a` 的缺陷原样活着**——
这条比原任务更有价值：**修完一个门禁缺陷，下一步是拿判据去扫所有同类脚本。**

`verify-on-mac.sh` 已改（`047b9539…` → `f57c5ee5…`，当场校验一致）。

## 3. B1 过期 —— 两条线程独立确认

`CERTIFIED_DDL_QUALIFIED_TABLE_NAME`（backlog 记的 160 条）**今天实测为 0**，
被 `NAMESPACE_MAPPING_REQUIRED` 取代（b3 数到 370 条）；a4-b4 实测 `--namespace-map`
可解并留 digest。两条线程用不同路径得到同一结论 —— 这是本轮唯一一处独立互证。

**B1 的 `NEEDS-DECISION`（"模式限定名在四方言含义有分歧，需先定失败关闭规则"）
在这个原因码上已经不成立**，应重新分诊后再定级。

## 4. 第三个会话正在并行写入

不是这四条线程写的（`>2026-09-01 03:00`）：

```
.ai/measurement-2026-08-26/method-profile.json          03:29
.ai/measurement-2026-08-26/method_profile_headroom.py   03:29
.ai/FINDINGS-2026-08-26-method-profile.md               03:29
.ai/measurement-2026-08-26/verify_generated_workspaces.py    03:51
.ai/measurement-2026-08-26/cloud-generation-evidence*.json   03:51
.ai/FINDINGS-2026-09-01-generated-workspace-verification.md  03:51
```

**落点与线程 2 同目录**（`measurement-2026-08-26/`，线程 2 在 03:41 改了
`verify-on-mac.sh`）。本次没撞上同一个文件，但这是靠运气不是靠机制。
另外 `method-profile` 正是 `admission_headroom` 里说的「剩下只有换 profile」那条路
（4,128 个类方法，占全体 25.7%），有人已经在走了。

## 5. 我复核过的其余事实

- 四份 FINDINGS + 一份 runbook 都真实落盘（`.ai/FINDINGS-2026-09-01-{c2-c3,gate-triage,a4-b4,b3}.md`、`.ai/DEMO-2026-09-01-runbook.md`）。
- project-intelligence-engine 新增 5 个模块 + 改 `cli.py` + 1 个测试文件，与线程 1 的自述一致；无其它引擎被写。
- 线程 4 对 `engines/sql-dialect-engine/` 的写入次数 **= 0**（它自己的 SHA-256 守卫没触发，我复核了该引擎无 09-01 的写入）。

## 6. 没做的

- **没有重跑任何覆盖率量测**去独立复算 2008/2644 —— 我只证伪了那个错口径，没有第三次独立读数。
- 没有在 Mac 上验证任何一项；C3 的「真 PowerPoint 能打开」仍是 `NOT_PROBED`。
- 没有复核线程 1 报的那个「有环 Spec 画到画布外」缺陷，采信它的负向对照（拆掉修复 4 条变红）。

---

## 7. 补：核对时漏掉的一条（2026-09-01 04:48 UTC 补记）

§5 我写了「四份 FINDINGS + 一份 runbook 都真实落盘」，**但没有核对报告里引用的产物路径**。
用户问「在哪里操作」时才发现：C2+C3 报告指向的 `_to_delete/c2c3-evidence/deck.pptx`
当时**不存在**，产物全在设备 VM 的 `$HOME/c2c3/`（`mnt/` 之外，用户不可见）。
已复制进仓库，详见 `FINDINGS-2026-09-01-c2-c3.md` 文末更正。

**这是本轮交叉核对自己的漏洞**：我验了「文件写没写」，没验「文件里指的路径存不存在」。
**报告里每一条要别人执行的路径，核对时都该 `ls` 一次** —— 成本一条命令。
