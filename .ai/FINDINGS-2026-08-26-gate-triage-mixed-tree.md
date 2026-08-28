# FINDINGS 2026-08-26 — 411 条「合并伤」是混合树产物，本轮合并无新增失败

## 结论

**perf→main 合并在 `polyglot-route-engine` 的 pytest 门禁上没有引入新失败。**

`gate-triage.sh --baseline` 曾报出「合并树 411 条 / 新增 411 条」，修掉工具缺陷后差集收敛到
**52 条**；把这 52 条整批重跑：**52 passed, 0 failed (6:29)**。
另用 `--collect-only` 校验过 `want ⊆ got`（`comm -23` 为空），没有条目被静默漏收集。

所以「新增」这一栏在本轮为 **0**。

⚠️ **复跑补记**：同一批 52 条第二次跑出 `1 failed / 51 passed (8:10)`，挂的是
`test_layered_equivalence.py::test_each_routed_target_relifts_exact_emitter_compensation[csharp]`，
错误是 `NATIVE_ANALYZER_FAILED:<dotnet>:process` —— `native.py` 里
`except (OSError, subprocess.TimeoutExpired)` 那条分支，**不是断言失败**。
同一棵树、同一条测试、两次不同结果，且第二次跑时机器上还在跑 `verify-on-mac.sh` 的全量套件
（同样 52 条 389s → 490s，+26%，`_run_native_process` 默认 `timeout=120`）。
判定为**跑动环境问题**，不改变「无合并伤」的结论，但准确的说法是
**51 条稳定通过 + 1 条在并发负载下超时，待单跑复验**，而不是「52/52」。

**复验**：`verify-on-mac.sh` 跑完后单独跑这一条，**1 passed in 97.90s**，
`grep` 不到 `TimeoutExpired` / `OSError` / `Errno`。确认为环境性，不是缺陷。

**机制（假设，未直接证实）**：不是泛泛的 CPU 争用，而是**共享的内容寻址构建缓存没有跨进程互斥**。
`native.py::_toolchain_build_cache()` 把 dotnet 的 NuGet restore 落在
`~/.cache/elmos-polyglot-route-engine/<schema>/dotnet/<key>/packages`，
**跨进程共享、只做可写探测、没有任何锁**（`_csharp_package_restore_cache` 的 docstring 明确说
「Only the restore is shared」）。两个并发跑动 key 相同 ⇒ 两个 restore 写同一个 packages 目录，
NuGet 自身的文件锁会让其中一个阻塞，`_run_native_process` 的 `timeout=120` 就被撑爆。

这条对本仓库尤其要紧：**本仓库的常态就是多会话并行**（见记忆 concurrent-sessions-in-elmos），
所以它会复发。证实办法很便宜 —— 两个终端同时跑同一条 csharp 测试，看是否复现同一个
`NATIVE_ANALYZER_FAILED:<dotnet>:process`。在此之前的止血办法是策略性的：
**同机不要并行跑两套引擎门禁**。

**教训：并发跑动不只污染树，也污染进程环境和磁盘上的共享缓存。**

## 走到错误结论的两个原因（叠加）

### 1. grep 的二进制模式把基线 559 条压成 1 条假行

差集提取用 `grep '^FAILED ' | awk '{print $2}'`。基线日志里混进了 NUL / 非法字节
（篡改类测试会写二进制），grep 判定为 binary 后**只打印一行 `Binary file … matches`，
一条匹配行都不打印，退出码仍是 0**。于是基线集合 = `{file}`（那行的第 2 个字段），
合并树的 411 条全部被算成「新增」。

判据（两个命令自相矛盾就是这个坑）：

```
grep -c '^FAILED ' base-pytest-engine.log   # 559
grep    '^FAILED ' base-pytest-engine.log   # 只有一行 Binary file … matches
```

### 2. 合并树侧的日志是混合树的产物

head 侧 pytest 跑了 **6:15:29**，窗口 **2026-08-25 15:27:35 → 21:43:04 UTC**
（本地 8/25 23:27 → 8/26 05:43）。窗口内另一会话重写了六个文件：

| 时间 (UTC) | 文件 |
|---|---|
| 17:01 | `src/assembly.py`, `src/project_graph.py` |
| 17:03 | `src/discovery.py` |
| 19:24 | `tests/test_repository_pipeline.py` |
| 19:46 | `tests/test_project_graph.py` |
| 19:51 | `tests/test_assembly_evidence_closure.py` |
| 20:00 | `tests/test_react_analyzer.py` |

52 条「新增」正好聚成两簇 + 1：`test_assembly_evidence_closure.py` 16 条、
csharp 作源侧的路由线、`test_project_graph.py` 1 条 —— 与被改文件一一对应。
同期 HEAD 从 `5b9e33ab7` 走到 `61cb1fc23`。

**推论：那一整张门禁表里没有任何两行说的是同一棵树。** ruff / mypy 在 15:27 附近就跑完
（早于 17:01 那批编辑）；pytest 横跨全部编辑；pytest 之后的门禁跑在 21:43 之后的更新树上。
「相对基线没有新增类型错误」这类结论只对 15:27 那棵树成立。

## 工具侧修复（`gate-triage.sh`，均已落盘）

1. 四个提取函数一律 `grep -a`；提取结果里出现 `^Binary file ` 就跳过该门禁不下结论。
2. `set -u` 崩溃：`WHY="…当前 $jdk，enforcer…"` —— 变量名后紧跟全角标点，bash 把多字节
   首字节当标识符字符 ⇒ `jdk?: unbound variable`，**炸在汇总循环里，整张定性表和退出码全丢**。
   中文串里插变量一律 `${var}`。查法：`perl -ne 'print if /\$[A-Za-z_]\w*[^\x00-\x7f]/'`
   （macOS grep 无 `-P`，别用 grep 查）。
3. enforcer 分支加守卫：命中 JDK 文案**且**日志里没有 `^\[(ERROR|INFO)\] Tests run:`
   才判 ENV，免得把真实测试失败盖成环境问题。⚠️ 加了之后 mvn-arch 仍判 ENV，**未查明，不算已修**。
4. 混合树检测：`.start` / `.head-sha` 只在真跑时记（`--reuse` 不再抹掉上一次的证据）；
   检测提到汇总**之前**；结果写进 `$OUT/.mixed-tree` 供 `--reuse` 继承；
   `classify()` 收尾把 MERGE 一律降级成 UNKNOWN 并附上原判据。
5. （另一会话所改）门禁与基线的 pytest 都改成 `-rfE`，差集同时认 `ERROR` ——
   collection / fixture error 不出现在 `-rf` 的短摘要里，只比 `FAILED` 会把它们当成两侧都没问题。
   注意**现有日志是 `-rf` 时代的产物**，这部分要等基线重跑才有数据。

## 顺带闭合的一个真缺陷（与合并无关）

`/api/v1/platform-admin`（P4 平台管理端）是 30 个 `@RequestMapping` 里唯一没在
`OperationsBusinessLineRegistry.ROUTES` 登记的路由组。而 `classify()` 没命中时
`.orElse("PRODUCT_OVERVIEW")` —— **不是报错，是静默归到「产品概览」**，
跨组织管理端的审计事件整条错归。已补 `ROUTES.put("/api/v1/platform-admin", "ADMIN_OPERATIONS")`。

核过：该文件自 8/8 起无人改动；`ADMIN_OPERATIONS` 在 control-plane / web-console /
resources 里没有对应枚举或约束，加值不触发别处校验；`ROUTES` 是 `LinkedHashMap` + `findFirst`，
长前缀须在前，这条与任何现有键都不构成前缀关系。
验证：`tests/production-readiness/test_operations_control.py` 5/5 通过，
整套 79 条只剩 1 条既有的自计数漂移。

**这是 silent-zero 模式的分类版**：分类函数的缺省桶必须是「未分类」这种一眼看得出不对的值，
不能是一条真实业务线。新增 Controller 必须同步登记 `ROUTES`。

## 仍未闭合

- **mvn-arch 仍判 ENV**：`Tests run:` 守卫没命中，原因未查（`grep -ac '^\[ERROR\] Tests run:' mvn-arch.log` 还没跑）。
- **ERROR 侧差集无数据**：要等基线用 `-rfE` 重跑。
- **两侧口径不对等**：基线是 `git archive` 解出的树（不含 analyzer 二进制、node_modules、构建缓存），
  合并树跑在活的工作树上。实测基线 559 failed / 1579 passed / 2:02:11，合并树 411 / 1721 / 6:15:29。
  因此**「被合并修好」那一栏（190 条，几乎全是 react/kotlin/swift/javascript）是环境差异，不是功劳，不可引用**。
  想让两个方向都可信，两侧都该从 `git archive` 解出来跑（顺带冻结树）；尚未实现。
- **自计数漂移**：`.agents/skills` 目录数 1887 vs UI 写死的 1267，且还在涨（门禁跑时是 1847）。
  这类校验器的数字只在跑的那一刻有意义，写回文档前必须当场再取一次。
- `pytest-synthesis`、`web-console-e2e` 仍是 UNKNOWN，本轮未查。

## 方法论（这轮最贵的三条）

1. **形状可信 ≠ 结论可信。** 52 条聚成两簇、边界干净，看着像真接缝，实际是写入窗口的投影。
2. **抽检单跑是最便宜的证伪。** 两条代表各跑一次（19s / 8s）就推翻了整份差集，
   比读 52 行测试名快得多。差集类工具的结论，落笔前先抽检一条。
3. **长跑必须冻结树，至少要记录起点。** 6 小时的跑动横跨他人写入，产出的是一份没有对应树的数字。
   `gate-triage.sh` 现在会自己检测并降级；`verify-on-mac.sh` 还没有这个保护（它也没有自我快照，
   跑动期间不能编辑）。

## 复现命令

```bash
# 差集（修好之后）
bash gate-triage.sh --reuse

# 逐条重跑「新增」
cd engines/polyglot-route-engine
sed 's/^FAILED //' /tmp/gate-triage/pytest-engine.new \
  | xargs uv run --locked --group dev pytest -o 'addopts=--strict-markers' -q

# 混合树检查（起点换成本次跑动的开始时间）
touch -t YYYYMMDDhhmm.ss /tmp/run-start
find engines/polyglot-route-engine/{src,tests} -type f -name '*.py' \
  -newer /tmp/run-start | grep -v __pycache__
GIT_OPTIONAL_LOCKS=0 git rev-parse --short HEAD
```
