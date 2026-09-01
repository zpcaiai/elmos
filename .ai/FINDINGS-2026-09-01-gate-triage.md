# FINDINGS 2026-09-01 — gate-triage 五项未闭合的处置：2 闭合 / 1 部分闭合 / 2 仍未闭合

承接 `.ai/FINDINGS-2026-08-26-gate-triage-mixed-tree.md` 的「仍未闭合」一节。

## 结论（先说）

1. **`gate-triage.sh` 在本机上找不到**：不在仓库树里，macOS 的 `/tmp` 下也没有
   `gate-triage` 目录。第 1、2 项直接依赖它和它的产物（`mvn-arch.log`、
   `base-pytest-engine.log`），**按原计划无法推进**。这不是「还没做」，是**取不到输入**。
2. **第 4 项（自计数漂移）闭合**：当场实测 `4319 / 4319`、`6442 / 6442`，
   `test_skill_inventory_ui_matches_callable_repository_directories` **1 passed**。
   1887 vs 1267 的口子已经被别人补上了。
3. **第 5 项的 `pytest-synthesis` 闭合，机制已证实**：不是测试挂了，是
   **命令行的 `-q` 和 pyproject 里 `addopts` 的 `-q` 叠成 `-qq`，`-qq` 会把计数行整行删掉**。
   退出码仍是 0，`FAILED`/`ERROR` 行仍在 —— 只有「N passed」那一行没了。
   任何靠计数行定性的分类器到这里只能给 UNKNOWN。
4. **顺带在 `verify-on-mac.sh` 上查出三个真缺陷并修掉**，其中两个是上一轮已经在
   `gate-triage.sh` 里修过、但**从来没人在 `verify-on-mac.sh` 上修**的同一类缺陷。
5. **第 1 项（mvn-arch）仍未闭合**，但根因候选已收敛到两个，且给出了可证伪的实测数据：
   任务书里当作「第一步」的那条命令 `grep -ac '^\[ERROR\] Tests run:'` **本身就是错的判据**。
6. **第 3 项部分闭合**：`--freeze` 已经实现在 `verify-on-mac.sh` 里（`git archive` 冻结树），
   但「两侧都从 archive 跑」需要基线侧配合，本轮跑不了。

---

## 零、环境事实（它决定了哪几项做不了，先摆出来）

| 事实 | 后果 |
|---|---|
| `device_bash` 是一台 **Linux VM**（`Linux 6.8.0 aarch64`），只挂载了仓库目录 | macOS 的 `/tmp`、`$HOME` 不可达 |
| 仓库树里**没有** `gate-triage.sh`（全树搜过，只有 08-26 那份 FINDINGS 提到它） | 第 1、2 项取不到输入；也无法按要求「改 gate-triage.sh」 |
| macOS `/tmp` 下**没有** `gate-triage` 目录 | 上一轮的 `/tmp/gate-triage/*` 产物已被清掉 |
| 无 `mvn`、无 `dotnet`；`java` 是 11，仓库 enforcer 要求 `[21,22)` | mvn 侧门禁在此完全跑不了 |
| 设备桥**不能 unlink**（实测 `failed to remove ... Operation not permitted`） | `uv` 无法就地重建仓库里的 `.venv`；必须 `UV_PROJECT_ENVIRONMENT` 指到 `${HOME}` |
| 仓库里的 `.venv` 指向 macOS 解释器 | 在 VM 里跑任何引擎套件都要另建 venv |

实测：

```
$ find . -name 'gate-triage*' -not -path './.git/*'
（无输出）

$ ls .agents/skills 2>/dev/null | wc -l     # 树是真的，只是脚本不在里面
4319
```

`/tmp`（macOS，只读列目录）里可见的 130+ 个 `elmos-*` 临时目录中没有 `gate-triage`。

---

## 一、mvn-arch 仍判 ENV —— **仍未闭合**，但判据被证伪了

### 做不了的部分

`mvn-arch.log` 已经不存在，`mvn` 在本环境里也不存在。**没有跑出任何 mvn 门禁。**

### 做到的部分：用仓库里归档的真 Maven 日志验证守卫的正则

仓库里有历史的 reactor 日志，可以当替身检验守卫的前提是否成立：

```
$ L=./artifacts/test-suite/local-qualification-20260722-r16-final-stable/logs/java-reactor.log
$ grep -ac 'Tests run:' "$L"
219
$ grep -acE '^\[(ERROR|INFO)\] Tests run:' "$L"
217
$ grep -ac '^\[ERROR\] Tests run:' "$L"
2
```

真实行形（`cat -A` 截断）：

```
[INFO] Tests run: 7, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 0.112 s -- in io.elmos.domain.MigrationRunTest
[WARNING] Tests run: 1, Failures: 0, Errors: 0, Skipped: 1, Time elapsed: 0.003 s -- in io.elmos.persistence.FlywayMigrationTest
[ERROR] Tests run: 20, Failures: 1, Errors: 0, Skipped: 0, Time elapsed: 1.430 s <<< FAILURE! -- in io.elmos.architecture.BatchOneToThirteenAssuranceTest
```

**三条结论：**

1. **任务书里当作「第一步」的 `grep -ac '^\[ERROR\] Tests run:'` 是错的判据。**
   在一份 219 行 `Tests run:` 的日志里它只命中 **2** 行 —— `[ERROR]` 前缀只在
   *某个模块真的有失败* 时出现。一次**测试全跑、全过**的构建，这条命令返回 **0**。
   如果 `gate-triage.sh` 的守卫用的是这个 `ERROR`-only 形式，那「测试跑了且全过」的
   mvn-arch 就会被判成「没有 `Tests run:`」⇒ **ENV**。这完全能解释症状。
2. `^\[(ERROR|INFO)\]` 形式命中 217/219，**但仍漏掉 `[WARNING] Tests run:`**（有 skip 的模块）。
   正确的形式应该不锁前缀：`^\[[A-Z]+\][[:space:]]*Tests run:`，或干脆 `Tests run:`。
3. **ENV 分支的「命中 JDK 文案」这一半根本不筛选**：enforcer 在**每个模块**都打印
   `[INFO] --- enforcer:3.6.1:enforce (baseline) @ ...` 和
   `Rule 0: ...RequireJavaVersion passed`。上面那份**全绿**的日志里这类文案出现 **73 次**。
   也就是说 ENV 判定实际上**全靠 `Tests run:` 那一半**扛着，另一半形同虚设。

```
$ grep -acE 'enforcer|requireJavaVersion|Detected JDK|Java version' "$L"
73
$ grep -aE 'enforcer|requireJavaVersion' "$L" | head -3
[INFO] --- enforcer:3.6.1:enforce (baseline) @ elmos-parent ---
[INFO] Rule 0: org.apache.maven.enforcer.rules.version.RequireJavaVersion passed
[INFO] Rule 1: org.apache.maven.enforcer.rules.version.RequireMavenVersion passed
```

### 两个根因候选（需要 `mvn-arch.log` 才能判）

- **候选 A（工具缺陷）**：守卫的 `Tests run:` 正则太窄（`ERROR`-only，或漏 `WARNING`），
  测试其实跑了，守卫没认出来 ⇒ 误判 ENV。
- **候选 B（判得对，只是没人核）**：enforcer 绑在 `validate` 阶段（`pom.xml:191-196`,
  `<requireJavaVersion>[21,22)</requireJavaVersion>`）。JDK 不对时构建停在 `validate`，
  surefire 根本没跑，**日志里一行 `Tests run:` 都不会有** —— 此时判 ENV 是**正确的**，
  守卫没「命中」正是因为它不该命中。

**区分办法（一条命令，需要 mvn-arch.log）：**

```bash
grep -acE '^\[[A-Z]+\][[:space:]]*Tests run:' mvn-arch.log
# > 0  ⇒ 候选 A：测试跑了，守卫正则太窄，改正则
# = 0  ⇒ 候选 B：构建停在 validate，ENV 是对的，去核 JAVA_21_HOME
```

**状态：仍未闭合。** 但下一个人不必再从零开始，也不该再用 `ERROR`-only 那条命令起手。

---

## 二、ERROR 侧差集无数据 —— **仍未闭合**（基线跑不了），但前提被证实成立

跑不了：基线要 `gate-triage.sh --baseline` 加一次两小时级的 Mac 全量跑，两个条件都不具备。

**但顺手证实了一件本来会咬人的事**：`-qq` 不会吃掉 `-rfE` 的短摘要行。

```
$ cd ~/qq-probe && cat pytest.ini
[pytest]
addopts = -q --strict-markers
testpaths = tests

$ pytest -rfE | tail -3          # 一个 -q（来自 addopts）
FAILED tests/test_probe.py::test_bad - assert False
1 failed, 1 passed in 0.01s

$ pytest -q -rfE | tail -3       # 两个 -q ⇒ -qq
=========================== short test summary info ============================
FAILED tests/test_probe.py::test_bad - assert False
                                 ← 计数行没了，FAILED 行还在
```

所以基线一旦重跑，`^(FAILED|ERROR)` 的抽取是可靠的，**不用担心 `-q` 把 ERROR 行一起吞掉**。
真正会丢的是计数行（见第五项）和 —— 更危险的 —— `grep` 的二进制模式（见第六节）。

---

## 三、两侧口径不对等 —— **部分闭合**

「两侧都从 `git archive` 解出来跑」需要基线侧配合，本轮做不到。
**能做的一半已经落盘**：`verify-on-mac.sh` 新增 `--freeze`，用
`GIT_OPTIONAL_LOCKS=0 git archive HEAD | tar -x` 把 HEAD 导出到临时目录、在里面跑、
产物留在冻结树里并打印取回命令。

脚本里把**代价写死在注释里**，因为这正是上一轮踩的坑：

> 导出的树**只有被跟踪的文件**。没有 `node_modules`、没有编译好的 analyzer 二进制、
> 没有 `.venv`、没有热的 `~/.cache` 构建缓存。凡是要 shell 出去调工具链的用例都会更慢，
> 有些会因为跟代码无关的原因失败。这种不对称 —— 基线来自 `git archive`、head 来自活工作树 ——
> 正是让 08-26「被合并修好 190 条」那一栏变成废数的原因。
> 所以：`--freeze` 用于 A/B 差分，两侧同付同一份代价；
> 「我这台 Mac 过不过」请用普通跑法。

无 git 时 `--freeze` **直接退出（exit 2）**，不会退化成在活树上跑：

```
$ bash .ai/measurement-2026-08-26/verify-on-mac.sh --freeze
--freeze needs git; cannot export a frozen tree. Aborting.
```

git 用法严格限制在**只读、无锁**：`GIT_OPTIONAL_LOCKS=0` 下的 `rev-parse` 与 `archive`，
且每一处都可失败（失败就在 provenance 里记 `unavailable`，跑动继续）。

**状态：部分闭合。** 冻结机制有了；两侧对齐还没有。

---

## 四、自计数漂移 —— **闭合**

校验器在 `tests/production-readiness/test_closure_skills_and_generation.py:157-174`，
数的是 **含 `SKILL.md` 的一级子目录**，比对 `apps/web-console/app/lib/catalog.ts` 里的
`codexSkillCount` / `runtimeSkillCount`（不是 `frtCatalog.generated.ts`）。

**当场再取一次**（方法论要求），`2026-09-01T03:41:54Z`：

```
codexSkillCount:   declared=4319  actual=4319  MATCH
runtimeSkillCount: declared=6442  actual=6442  MATCH
```

真跑一遍：

```
$ uv run --no-project --with pytest --with pyyaml python -m pytest \
    tests/production-readiness/test_closure_skills_and_generation.py \
    -k skill_inventory_ui -q
1 passed, 11 deselected in 1.69s
```

1887 vs 1267 的漂移不存在了（有人把 `catalog.ts` 重新生成过；现在的量级是 4319 / 6442）。

⚠️ **这个数只在 `2026-09-01T03:41:54Z` 那一刻成立。** 上一轮从 1847 涨到 1887，
这一轮已经是 4319 —— 引用前必须当场再取，不要从这份文档里抄数。

---

## 五、`pytest-synthesis` / `web-console-e2e`

### `pytest-synthesis` —— **闭合（机制已证实）**

不是测试挂了。跑给自己看：

```
$ cd engines/project-synthesis-engine
$ grep -A2 '\[tool.pytest' pyproject.toml
[tool.pytest.ini_options]
addopts = "-q --strict-markers"

$ uv run --locked --group dev pytest -q -rfE > synth2.log; echo "exit=$?"
exit=0
$ tail -2 synth2.log
.....................                                                    [100%]
                                    ← 没有计数行

$ uv run --locked --group dev pytest -rfE > synth3.log; echo "exit=$?"
exit=0
$ tail -2 synth3.log
.....................                                                    [100%]
165 passed in 3.34s                 ← 去掉命令行那个 -q，计数行就回来了
```

**机制：命令行 `-q` + `addopts` 里的 `-q` = `-qq`，`-qq` 删掉计数行。**
退出码照常，`FAILED`/`ERROR` 行照常 —— 只有「N passed」没了。
靠计数行定性的分类器到这里除了 UNKNOWN 无话可说。

**波及面（实测四个引擎的 addopts）：**

| 引擎 | `addopts` | 门禁再加 `-q` 会怎样 |
|---|---|---|
| `polyglot-route-engine` | `-q --strict-markers` | **会 `-qq`，丢计数行** |
| `sql-dialect-engine` | 无 | `-q` 是对的，保留 |
| `project-synthesis-engine` | `-q --strict-markers` | **会 `-qq`，丢计数行** |
| `database-data-engine/sql-transpiler` | `-q` | **会 `-qq`，丢计数行** |

`verify-on-mac.sh` 原来的第 1、3、4 步全都在重复加 `-q`。**已修。**

⚠️ 归因边界：`gate-triage.sh` 取不到，所以「`pytest-synthesis` 这个门禁**确实**是这么调的」
没有直接证据。证实的是**机制**，以及「本仓库三个引擎都具备触发条件」。
拿到脚本后一条命令就能收口：看它调 pytest 时有没有多给一个 `-q`。

### `web-console-e2e` —— **仍未闭合**

在本环境跑不了：要浏览器、要 Mac 上钉的 node 运行时。**没有跑，不猜结论。**
只留两条最该先查的线索（均为未验证的假设）：

- `Makefile:291` 的 e2e 步骤经 `$(PNPM)`，而 `PNPM ?= pnpm dlx pnpm@$(PNPM_VERSION)`
  （`Makefile:21`）**要联网**。网络不通时它失败得不像测试失败，很容易落到 UNKNOWN。
- `NODE_RUNTIME_BIN` 在 node 缺失时是 `/nonexistent/node-runtime-not-found/`
  （`Makefile:19`，注释说这是故意的，让它报 `node: command not found`）。
  先确认 `NODE_EXECUTABLE` 在门禁跑动的环境里解析成了什么。

---

## 六、本轮在 `verify-on-mac.sh` 上修掉的三个缺陷

改的文件只有一个：`.ai/measurement-2026-08-26/verify-on-mac.sh`
（写前核过 SHA-256 未被他人改动：`047b9539…2813b`，5627 字节；写后 `f57c5ee5…0b151`，13270 字节）。
**没有动任何引擎源码或测试。**

### A. `grep -E` 缺 `-a` —— 与上一轮 gate-triage.sh 的头号缺陷是同一个，**从没在这里修过**

原文：

```bash
grep -E '^(FAILED|ERROR)' "${ART}/mac-${STAMP}/polyglot-run.txt" | sort \
  > "${ART}/mac-${STAMP}/polyglot-failed.txt"
```

而 polyglot 套件里**篡改类测试会往输出写 NUL**。复现：

```
$ printf 'FAILED tests/test_a.py::test_one\n' > b.log
$ printf 'some tamper output \000 with NUL\n' >> b.log
$ printf 'FAILED tests/test_b.py::test_two\nERROR tests/test_c.py\n' >> b.log

$ grep -E '^(FAILED|ERROR)' b.log
grep: b.log: binary file matches
  exit=0  lines=0          ← 差集直接变空集，退出码还是 0

$ grep -aE '^(FAILED|ERROR)' b.log
FAILED tests/test_a.py::test_one
FAILED tests/test_b.py::test_two
ERROR tests/test_c.py
  exit=0  lines=3
```

**这就是 08-26 那份 FINDINGS 第 1 节写的坑，一字不差，只是换了个脚本。**
上一轮只修了 `gate-triage.sh`，`verify-on-mac.sh` 一直带着它。已改成 `grep -aE`。

### B. 重复 `-q`（见第五项）

第 1、3、4 步去掉命令行的 `-q`（`addopts` 已经给了），第 2 步保留（该项目没有 `addopts`）。
并且**加了断言**：第 1 步捕获完日志后检查计数行是否存在，不存在就打印
「多半是 `-qq`」并置 `FAILED=1` —— 免得以后有人再加回来、又是静默失效。
原来的 `tail -1` 在 `-qq` 下打印的是进度条，不是结果。

### C. 没有混合树保护（方法论第 3 条点名要补的）

新增：

- **步骤 0**：跑前记 `run_started_utc`、`head_at_start`、`tree`、`host`，
  落盘到 `${RUN}/run-provenance.txt`；同时在 `${TMPDIR}` 放一个 `mktemp` 标记文件
  （**不放进仓库**，免得自己触发自己）。
- **步骤 7**（编号故意是「7/6」，因为它不是一个门禁）：跑完比 `head_at_start` vs `head_at_end`，
  并 `find` 四个引擎的 `src`/`tests` 里比标记文件新的文件，
  排除 `__pycache__` / `.venv` / `.pytest_cache` / `.ruff_cache` / `.mypy_cache` /
  `node_modules` / `*.pyc`。
- **判混合就降级**：写 `${RUN}/.mixed-tree`（沿用 `gate-triage.sh` 的约定），
  打印「这些数字不描述任何一棵树」，**即使 `FAILED=0` 也 `exit 3`**，
  并指向 `--freeze`。

实测两条路径：

```
（干净跑）
== 7/6  mixed-tree check -- did the tree hold still? ==
  window        2026-09-01T03:40:51Z -> 2026-09-01T03:40:51Z  (0s)
  HEAD          unavailable -> unavailable
  source writes 0
all automated steps passed -- artefacts in .ai/measurement-2026-08-26/mac-2026-09-01/
EXIT=0

（跑动中间被写了一个源文件 + 一个 .pyc）
== 7/6  mixed-tree check -- did the tree hold still? ==
  window        2026-09-01T03:41:01Z -> 2026-09-01T03:41:07Z  (6s)
  source writes 1
    engines/polyglot-route-engine/src/assembly.py     ← .pyc 被正确忽略
MIXED TREE -- these numbers describe no single tree.
EXIT=3
```

「没有计数行」那条分支也验了：`EXIT=1`，并打印
`!! no pytest count line ... Almost always a doubled -q`。

`${VAR}` 检测（`macOS` 的 grep 无 `-P`，用 perl）：

```
$ perl -ne 'print if /\$[A-Za-z_]\w*[^\x00-\x7f]/' <脚本>
.ai/measurement-2026-08-26/verify-on-mac.sh    0 hit(s)
.ai/measurement-2026-08-21/verify-on-mac.sh    0 hit(s)
.ai/matrix-preflight.sh                        0 hit(s)
```

（新脚本全英文，本来也不会触发；顺手把另外两个也扫了，都干净。）

---

## 七、没做 / 做不了（不用推断填充）

- **没有跑任何 mvn 门禁**，`mvn-arch` 的两个候选没有分出胜负。
- **没有重跑基线**，第 2 项一行新数据都没有。
- **没有跑 `web-console-e2e`。**
- **没有改 `gate-triage.sh`** —— 它不在可达范围内。上一轮在它里面修的
  `grep -a` 和 `${VAR}` 两条，本轮也**无法复核是否还在**。
- **没有在这台 Mac 上跑过新的 `verify-on-mac.sh` 全程**：本环境是 Linux VM，
  没有 mvn / dotnet / swift / kotlin，第 5、6 步跑不了。
  新增逻辑是用**桩替身**端到端验的（干净 / 混合 / 无计数行 / 无 git 四条路径全过），
  引擎步骤本身没有在真环境里回归过。**第一次真跑请留意第 1 步的计数行断言。**

## 八、方法论补一条

上一轮的三条仍然成立。补第四条：

> **同一个缺陷会在第二个脚本里原样再活一次。**
> `grep` 的二进制静默归零，08-26 在 `gate-triage.sh` 里查清楚、修好、还写进了 FINDINGS；
> 六天后它在 `verify-on-mac.sh` 里一字不差地又被找到 —— 因为上一轮只修了「发现它的那个文件」。
> 修完一个门禁缺陷，**下一步不是收工，是拿判据去扫所有同类脚本**。
> 这一类的判据都很便宜，可以直接做成检查：
> `grep -n "grep -E\|grep '" *.sh`（缺 `-a`）、
> `perl -ne 'print if /\$[A-Za-z_]\w*[^\x00-\x7f]/'`（`${VAR}`）、
> 「命令行 `-q` 撞上 `addopts` 里的 `-q`」。
