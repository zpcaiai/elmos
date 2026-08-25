# 合并 `perf/analyzer-build-cache-and-batching` → `main`：中间态与判断规则

这次合并没有做完。本文件记录**已经解掉的部分、每一处的理由、以及推导出的规则**，
让下一次接手的人不必重新推导，也不必反向猜测某个取舍是深思熟虑还是随手为之。

写在最前：**未解的 33 个文件里，引擎那 15 个是主体，而且必须先于
`apps/web-console/app/lib/server/translationRunner.ts` 的收尾**。原因见「未完成」一节。

## 状态

- 合并进行中，`git merge origin/main` 于 detached HEAD（`784a86f13`）上执行
- 54 个冲突文件，已解 21 个，剩 33 个仍带冲突标记
- 已解的部分**尚未提交**，只是 `git add`
- perf 领先 main 63 个提交，落后 47 个；`git cherry` 确认 63 个提交**没有一个**的等价补丁已在 main 上
  （前三个分支带进 main 的同类工作，在 perf 上是另一套实现，不是同一批提交）

## 推导出的规则

这些规则不是先验的，是从今天逐个文件的判断里长出来的，每条后面都有实例。

### 1. 两边都改了同一处 → 先问「这两个改动正交吗」，再问「取哪个」

大多数冲突其实是**正交改动被 diff 算法挤到了一起**，答案是取并集而不是二选一。

- `playwright.config.ts` 的就绪 URL：分叉点是 `${baseURL}/frontend`；
  main 只改了路径（换成 `/api/capabilities/generation` 能力端点），
  perf 只改了主机（引入 OIDC 代理后要指向上游 `nextServerBaseURL`）。
  答案是 `${nextServerBaseURL}/api/capabilities/generation`，各取一半。
- `contracts.ts`：perf 加了 `repository*` 五个字段，main 往 `status`/`stage`
  联合类型里加了 `PRECHECK`/`preflight`。两者都要。
- `package.json` 的 `check`：perf 挂了 5 条策略校验，main 挂了 4 条测试。9 条全跑。
- 13 个 `Makefile.batchNN`：**两边各自独立做了同一个 `$(UV)` 可移植性改造，文本完全相同
  所以自动合并了**，冲突只落在紧邻行上。不要被冲突块的位置误导。

### 2. 同一个守卫的两个版本 → 取更强的那个，不论它在哪一侧

方向不固定，必须逐个看，不能立一条「引擎文件取 perf、其余取 main」的偷懒规则。

- `OptionalSourcePackage.java` → **main**：校验路径穿越、区分「包缺失」（跳过）与
  「包残缺」（判失败）、用 `NOFOLLOW_LINKS`。
- `tooling/source_package_guard.py` → **perf**：有 `_confined_relative()` 拒绝 `../`
  逃逸并把 manifest 解析限制在 ROOT 内；main 那版是裸的路径拼接。
- `translationRunner.ts` 工件下载 → **main**：摘要格式、大小上下界、状态与
  `conversionSummary.codeArtifactReady` 联合判定、`verifiedOpenPipelineFile`。

### 3. 摘要 / 计数 / 联合类型这类「字段集合」必须逐字段核对

**这是今天最危险的一类，类型检查和测试都兜不住。**

实例：`translationInputDigest`。区 4 表面上是纯重构 —— perf 内联算摘要，main 抽成了函数。
但 main 的函数体只有 4 个字段，perf 内联版有 9 个。直接取 main 会**静默收窄输入摘要**，
让两个只在仓库证据上不同的任务算出同一个 digest。已在合并里把 5 个 `repository*`
字段补回函数体，并在函数上方写明原因。

同类还有：`Makefile.batch33`/`batch35` 的 `--with pyyaml`（main 有意移除，perf 只是保留原样，
取 main）；`schemas/test-suite` 的计数断言（上一个分支就栽过，9 → 11）。

### 4. 「被跳过」不等于「通过了」

`BatchOneToFiftyFiveSkillCatalogAssuranceTest` 与 `ProductBatch40To55SkillAssuranceTest`
两边解决的是同一件事：可选包缺失时，已跟踪文件的断言不该被埋没。
main 把断言提到假设之前，但**整个测试仍被标记为 skipped**，断言跑过了却不体现在报告里；
perf 拆成两个 `@Test`，已跟踪的那半独立报告为 PASSED。取 **perf**。
可验证：改前是 `Tests run: 2, Skipped: 2`，改后应有一个真通过。

### 5. 锁文件不手工解

`apps/web-console/pnpm-lock.yaml`（4 区）：取一侧后用
`pnpm --dir apps/web-console install --lockfile-only` 重新生成，让工具自己算。

### 6. 引擎必须先于 runner

`translationRunner.ts` 校验的是 polyglot 引擎产出的 `repository-pipeline-report.json`。
perf 的覆盖校验器不是独立的：

    function validateBehaviorCoverage(
      value: unknown,
      reportStatus: "COMPLETE" | "PARTIAL",
      closure: ReturnType<typeof validateBatchClosure>,   // 依赖 perf 的批次闭合校验
    ): TranslationBehaviorCoverage

引擎的 `batch.py` / `pipeline.py` / `discovery.py` 还没合，报告的最终字段结构未定。
在那之前把校验器接进去，等于对一个还没定型的契约写校验 —— 而结构对不上时
`tsc` 不会报（都是 `unknown` 进 `isRecord`），只会在运行时 `fail(409, ...)`。

## 已解的 21 个文件

| 文件 | 取舍 | 理由 |
|---|---|---|
| `Makefile.batch38`–`45`（8 个） | perf | perf 给 `.PHONY` 扩了 `gaps`/`score`/`manifest`/`request`；main 侧是分叉点原样 |
| `Makefile.batch33`、`batch35` | main | 有意移除 `--with pyyaml`；batch35 另有 `include Makefile.external-gates` |
| `Makefile.batch29` | 合并 | perf 的钉版依赖与 `b29-repository-contract-check` + main 的 `external-gate-intake-test` 前置 |
| `OptionalSourcePackage.java` | main | 规则 2 |
| `tooling/source_package_guard.py` | perf | 规则 2 |
| `docs/INDEPENDENT_VERIFICATION.md` | main | perf 侧为空，纯新增章节 |
| `BatchOneToFiftyFiveSkillCatalogAssuranceTest.java` | perf | 规则 4 |
| `ProductBatch40To55SkillAssuranceTest.java` | perf | 规则 4 |
| `apps/web-console/package.json` | 合并 | 规则 1 |
| `apps/web-console/e2e/global-teardown.ts` | main | 回调式替换无 `$1` 歧义；区 2 为纯新增清理 |
| `apps/web-console/e2e/generation-ui.spec.ts` | 合并 | 见下方「顺带修掉的缺陷」 |
| `apps/web-console/app/lib/contracts.ts` | 合并 | 规则 1 |
| `apps/web-console/playwright.config.ts` | 合并 | 规则 1；**就绪 URL 需 e2e 实跑验证**，指错会挂起而不是报错 |
| `apps/web-console/app/lib/server/translationRunner.ts` | 部分 | 见下 |

### `translationRunner.ts` 的部分解

- 区 1 导入取并集
- 区 2、3 两边的辅助函数与常量都保留，`atomicJson` 用 main 的 `(destination, serialized: string)` 签名
- 区 4 取 main 的函数调用，**函数体补回 perf 的 5 个字段**（规则 3）
- 区 5–8 取 main 骨架（工件校验更严）
- **未完成**：`semanticCoverage` / `behaviorCoverage` / `projectGraph` / `repositoryComplete`
  的校验与写入尚未接回。已确认的接法是保留 main 的骨架，在其末尾（`finalizedReportValidated = true` 之前）
  追加这四个字段的校验与赋值，其中 `projectGraph` 可直接用已保留的 `validProjectGraphSummary`，
  覆盖两项需要连 `validateBatchClosure` 一起接。**必须等引擎合完**（规则 6）。

## 顺带修掉的一个真实缺陷

main 上的 `generation-ui.spec.ts` 断言 `window.__generationAuthorization`，
而**全仓库没有任何产品代码给这个属性赋过值** —— `?? ""` 永远得到空字符串，
这条 `expect.poll(...).toBe("Bearer ...")` 在任何情况下都不可能通过。
`.github/workflows/ci.yml` 确认 `web-console-generation` job 会跨 5 个浏览器项目跑这个 spec，
**所以 main 现在的 CI 应该是红的，值得单独去 Actions 上确认**。

perf 那侧从来没有这个问题：它用 `route.request().headerValue("authorization")`
从真实请求上取头。本次合并取 perf 的结构（真实请求头捕获 + 无令牌时
`toBeDisabled()` 的凭据管辖断言 + `press("Enter")` 及其 WebKit 注释），
嫁接 main 的请求断言（method / `x-elmos-tenant` / `x-elmos-actor` / `postDataJSON` 形状）
与 CI 稳定性改进（READY 等待、30 秒超时）。

## 未完成的 33 个

**引擎（15 个，主体）** — `batch.py`(13 区)、`pipeline.py`(12)、`discovery.py`(11)、
`native.py`(4)、`toolchains.py`(4)、`engine.py`(4)、`validation.py`(4)、`assembly.py`(2)、
`cli.py`(2)、`clang_analyzer.py`(1)、`repository.py`(1)、四个测试文件、`README.md`。

规模是两条线各自重写了同一个引擎的核心模块，不是几行分歧：

    discovery.py 区 6:  perf 465 行 vs main  18 行
    discovery.py 区 9:  perf 233 行 vs main   4 行
    pipeline.py  区11:  perf  39 行 vs main 139 行
    pipeline.py  区10:  perf  24 行 vs main 119 行

`toolchains.py` 需要额外小心：2026-08-18 当天曾在其上还原过 Node topology pin
（`_EXPECTED_NODE_TOPOLOGY_SHA256` 回退到 `2a77ac1d…`），起因是 Homebrew sqlite
3.53.3 → 3.53.4 的漂移又漂了回去。合并时不要让任何一侧的 pin 值悄悄覆盖它。

**web-console（4 个）** — `TranslationStudio.tsx`(4)、`core-business-lines-ui.spec.ts`(2)、
`pnpm-lock.yaml`(4，走规则 5)，加 `translationRunner.ts` 的收尾。

**文档与脚本（14 个）** — `Makefile`(3)、`.github/workflows/ci.yml`(4)、`README.md`(4)、
`docs/BUSINESS_LINE_CLOSURE_MATRIX.md`(2)、`docs/test-suite/ELMOS_INTEGRATION_MANIFEST.json`(3)、
project-synthesis 的 `verification.py`/`workspace.py`/`test_project_documentation.py`/`README.md`、
`scripts/batch35/*`(4)、`scripts/precision_migration/trust.py`(1)、
`scripts/validate_mature_product_series.py`(2)、`tooling/validate_project_synthesis_integration.py`(5)。

## 合完之后要跑的门禁

    uv --directory engines/polyglot-route-engine run --locked --group dev pytest
    uv --directory engines/polyglot-route-engine run --locked --group dev ruff check src tests
    uv --directory engines/polyglot-route-engine run --locked --group dev mypy src
    mvn -pl apps/java-engine-worker test
    mvn -pl modules/architecture-tests test
    pnpm --dir apps/web-console check
    pnpm --dir apps/web-console exec playwright test --project=chromium e2e/generation-ui.spec.ts
    python3 scripts/operations/validate_makefile_portability.py
    make operations-scripts-test
    uv run --quiet --with pyyaml python -m unittest discover -s tests/production-readiness -p 'test_*.py'

playwright 那条要先 `pnpm --dir apps/web-console exec playwright install chromium`。
`playwright.config.ts` 的就绪 URL 就是靠这条验证的。

## 工作方式

合并在 `../elmos-merge`（`git worktree add`）里做，因为主工作区常年是脏的，
`git switch` 会失败——本会话早些时候正是这样误把 `origin/main` 合进了 perf 分支。
文件通过 `_merge_conflicts/` 中转（协作方读不到 worktree），解完拷回。
两个目录都是临时的，收尾时删掉。

---

## 第二轮追加：又解了 8 个（累计 29/54）

| 文件 | 取舍 | 理由 |
|---|---|---|
| `scripts/batch35/run_verification_gate.py` | main | 函数名集合是 perf 的严格超集（perf 独有 0 个、main 独有 5 个），且是今天 `batch35-test` 39 个测试跑绿的那版 |
| `scripts/precision_migration/trust.py` | 合并 | perf 拆出 `from_bytes`（让调用方传入已有界 no-follow 读过的字节，避免元数据检查与信任构建看到不同 JSON 版本）+ main 的符号链接/常规文件校验、`parse_constant` 拒绝 NaN/Infinity、`payload` 必须是 dict |
| `scripts/validate_mature_product_series.py` | perf **待确认** | 见下 |
| `engines/project-synthesis-engine/src/.../workspace.py` | main | `_COMPOSE_LIMITS` 纯新增（8 种语言的 CPU/内存限额，含 php/kotlin/rust） |
| `engines/project-synthesis-engine/tests/test_project_documentation.py` | perf | **由上下文定案**：合并后的测试体是 `workspace = tmp_path / "generated-task"`，归档前缀就是 `generated-task/`；取 main 的 `notes-docs-service/` 会直接红 |
| `engines/polyglot-route-engine/src/.../repository.py` | perf | 扩展名映射是超集，多 `.hh`/`.hpp`/`.hxx`/`.php` |
| `engines/polyglot-route-engine/src/.../clang_analyzer.py` | 合并 | perf 的 objc `-fobjc-arc -framework Foundation` 与沙箱化环境（临时 HOME/TMP + `sanitized_subprocess_env`）+ main 的 `TimeoutExpired` → `NATIVE_ANALYZER_TIMEOUT`。perf 本来就有 `timeout=120` 却没接异常，超时会以裸 `TimeoutExpired` 冒出去 |
| `engines/polyglot-route-engine/src/.../cli.py` | 各自保留 | 两个区各是一侧的纯新增（main 的 `repository-preflight`、perf 的 `module`） |

### 待确认：`validate_mature_product_series.py`

这是规则 3 那类仓库自计数，取 perf 只是因为它是新增 schema 的那一侧，**真实值必须跑出来**：

    perf:  batch 30 → 6 个 schema，总计 229
    main:  batch 30 → 4 个 schema，总计 124

合并后的树是两边 schema 的并集，所以正确数字未必是 229。校验器自己会报
`Expected N, found M`，按 `found` 修正：

    python3 scripts/validate_mature_product_series.py

## 停在这里的原因（第二轮）

`test_pipeline.py` 区 2 是个具体的反例，说明**测试文件不能一律「两边都留」**：

    perf 区2（4 行）：读回 previous_graph、改写 math.py —— 属于 perf 那个
                      「项目图有未闭合义务时流水线为 LIMITED」的测试
    main 区2（32 行）：一串针对 BLOCKED 报告的断言 —— 属于 main 那个
                      「可信分析事故会发布 BLOCKED 报告」的参数化测试

两侧都是**函数体片段**而不是完整函数，拼接会把 BLOCKED 的断言接到另一个测试的
中段。区 1 两侧倒确实是两个完整的测试函数（perf 216 行、main 13 行），那种可以两边都留。

所以测试文件的规则是：**整函数区（两侧都以 `def` 或 `@pytest.mark` 开头）两边都留；
函数体片段区必须先确定它属于哪个函数**。`test_toolchains.py` 同理 —— 区 1、3 是整函数
（perf 的 `_mock_go_closure` 与 Go 闭包测试、main 的平台元组测试与探针缓存测试），
区 2 是体内片段。

未解的 25 个：引擎 11 个（`batch.py` 13 区、`pipeline.py` 12、`discovery.py` 11、
`native.py` 4、`toolchains.py` 4、`engine.py` 4、`validation.py` 4、`assembly.py` 2、
四个测试文件、两个 README）、web-console 3 个（`TranslationStudio.tsx` 4、
`core-business-lines-ui.spec.ts` 2、`pnpm-lock.yaml` 4）、文档与构建 6 个
（`Makefile` 3、`ci.yml` 4、`README.md` 4、`BUSINESS_LINE_CLOSURE_MATRIX.md` 2、
`ELMOS_INTEGRATION_MANIFEST.json` 3、`tooling/validate_project_synthesis_integration.py` 5），
外加 `translationRunner.ts` 的覆盖字段收尾（须在引擎合完之后）。

---

## 第三轮追加：又解了 5 个（累计 34/54）

| 文件 | 取舍 | 理由 |
|---|---|---|
| `Makefile` | 并集 | 区1 `.PHONY` 以 perf 打底追加 main 独有（`operations-scripts-test`、`test-suite-certification-rehearsal`），`verify:` 与 `business-line-contracts:` 取 perf（超集）；区2 `production-readiness-check` 前置取并集；区3 守卫注释取 main（与保留的 `OptionalSourcePackage` 语义一致） |
| `.github/workflows/ci.yml` | main | 区1 两侧注释措辞等价；区2、3 main 给步骤加了 `- name:`；区4 认证路径演练为 main 纯新增 |
| `engines/polyglot-route-engine/README.md` | 两段都留 | perf 写项目图，main 写功能义务语义 —— 不同主题 |
| `engines/project-synthesis-engine/README.md` | 两段都留 | perf 写结构与等价视图，main 写 UV 缓存预热 |
| `docs/BUSINESS_LINE_CLOSURE_MATRIX.md` | perf **待确认** | 见下 |

## 规则 8：自动合并的文件也可能是错的

**冲突列表不等于风险列表。** 87 个双改文件里只有 54 个进了冲突列表；另外 33 个
两侧改在不同行，git 静默拼接，拼出来的结果可能既不符合 perf 的数据也不符合 main 的数据。

实例：`scripts/operations/validate_translation_route_matrix.py` 两侧内容不同
（perf `e52b4ecb…` / main `33bcd174…`）但**不在冲突列表里**。合并中途跑它得到

    {"reason": "ROUTE_POLICY_DRIFT", "status": "FAILED"}

脚本第 151 行硬编码期望 `"complete_route_set": "ten-language-complete-90"`（10 语言 / 90 条），
而它读的数据来自各侧、其中一部分还卡在未解冲突里。**合并未完成时这个失败没有信息量**，
但合并完成后它必须变绿 —— 它是 `make business-line-contracts` 的一环，而后者是 `make verify` 的前置。

收尾时要做的：把所有双改但未冲突的文件也过一遍，至少让每个门禁跑一次，不要假设
"没进冲突列表 = 合对了"。

### 待确认：路线条数

场上有三个数字，都不能靠挑一个解决：

- `validate_translation_route_matrix.py` 期望 **90**（10 语言）
- `BUSINESS_LINE_CLOSURE_MATRIX.md`：perf 侧 **72**（9 语言 × 8），main 侧 **30**（6 语言 × 5）
- perf 分支提交 `eed30b94a … pin the route denominator at 110`（11 语言 × 10）

php 是今天刚加的第 11 种语言，所以 110 很可能才是合并后的真实值，72 和 30 都是历史快照。
以 `validate_translation_route_matrix.py` 的输出为准，把矩阵文档里三处数字
（`72 个受治理 Route Pack`、`72 条显式有向语线路`、`9 种引擎语言`）一并修正。

---

## 第四、五轮追加（累计 40/54 完整解决，`discovery.py` 部分解）

| 文件 | 取舍 | 理由 |
|---|---|---|
| `apps/web-console/pnpm-lock.yaml` | 重生成 | `--lockfile-only` 122 个依赖全解析，无缺失 —— 同时验证了 `package.json` 并集是完整的 |
| `validation.py` | perf | 行为用例 harness 做位精确比较（`Object.is`、`isSafeInteger`、拒绝 `-0`、编码标签），正是今天刷新算术补偿证明 pin 的那一版；main 那侧是更早的 `!=` 版本 |
| `assembly.py` | 区1 perf / 区2 合并 | 区1 perf 在 `resolve` 之前检查未解析路径分量（注释写明：先 resolve 会丢掉"子路径曾是链接"的证据）；区2 两个 `_run` 合成一个 |
| `toolchains.py` | 区1 并集 / 区2-4 perf | perf 校验可执行文件 sha256、swift target 三元组与 driver 版本，main 只比版本串。**Node pin 确认仍是 `2a77ac1d…`** |
| `engine.py` | perf | main 侧把 `behavior_pass_rate` 硬编码成 `1.0`（指标永远宣称满分），perf 从实际 summary 计算 |
| `native.py` | perf 骨架 + 嫁接 | 见下 |
| `discovery.py` 区1-4 | 正则并集 | 见下 |

## 规则 9：拼接两侧函数块，必须检查是否产生同名定义

`assembly.py` 出现过两个 `_run`，`validation.py` 出现过两个 `validate_source`。
**Python 只认最后一个** —— perf 的沙箱化执行环境（临时 HOME/TMP/cache +
`sanitized_subprocess_env`）就这样被静默架空：代码在文件里、语法没问题、永远不被调用。

`grep -c '^def name('` 是最便宜的检查；ruff 的 F811/F841 是兜底。

## 规则 10：未使用导入不是清理项，是功能被摘掉的信号

删掉重复的 `validate_source` 时我选了 main 版（"不执行客户顶层代码"听起来更安全）。
ruff 随后报 `hashlib` 与 `javascript_esm_descriptor` 未使用 —— **这是那次损失的唯一可见症状**。
追查才发现 perf 版单独处理 JavaScript 的 ESM 描述符（含 sha256 校验），而合并后的
`_source_subject` 根本不覆盖 javascript。也就是说那次选择实际是"用一条安全性质
换掉一整条语言路线的源验证"，而做的时候并不知道。

已按决定恢复 perf 版。**看到未使用导入，先追查它原本服务于什么，再决定删不删。**

## `native.py`：perf 骨架 + 嫁接 main 的契约校验

两侧体量差极远（perf 7579 行 / main 149 行）：main 走 `frontend-client-engine` 的
`polyglot-cli.js`，perf 自建分析器并做构建缓存（本分支得名于此）。骨架取 perf。

但 `NATIVE_ANALYZER_CONTRACT_INVALID` 在 perf 版里出现 **0 次** —— main 的
`_external_semantic_ir` 校验分析器输出契约：`functions`/`diagnostics` 必须是列表；
`functions` 为空但有诊断时**把第一条诊断当作错误抛出**（分析器在报告真实源码问题，
直接暴露比让调用方几层之后看到无形状失败有用得多）。main 的 `test_pipeline.py`
正好参数化测试了 `NATIVE_ANALYZER_CONTRACT_INVALID:INVALID_FUNCTION_SIGNATURE`。

已把该函数移植进 perf 骨架，并把 `analyze` 尾部的 `return SemanticIR.from_mapping(value)`
换成 `return _external_semantic_ir(value)`，注释注明来源与理由。

## 规则 11：三个引擎文件的结构性区段必须与 runner 的决定保持一致

`translationRunner.ts` 已定为「以 main 为骨架」，而该骨架校验的是流水线报告里的
`functional_conversion` 字段块；该字段块由 `pipeline.py` 产出，其分母又来自
`discovery.py` 的 `_candidate_inventory` / `enumeration_complete` 契约。

**所以 `discovery.py` / `pipeline.py` / `batch.py` 的结构性区段取 main**，
否则报告里没有 `functional_conversion`，runner 会一路 fail closed。
perf 在这些文件里的**正则表达式**改动与结构无关，取并集。

### `discovery.py` 区1-4（正则，已解）

- 区1 → perf：javascript 的 `export function` 正则，main 侧为空
- 区2 → 并集：rust 补 main 的 `async\s+`、保留 perf 的 `extern "C"`；
  cpp 补 `int32_t`/`float`，保留 `long long`（必须排在 `long` 之前）与 `std::` 前缀
- 区3 → perf 结构 + main 的 `float`：perf 以 `\s+` 收尾更严，
  main 的 `\s*` 会让 `int` 直接粘上标识符（`intfoo` 也会匹配）
- 区4 → perf：swift 多 `final` 修饰符，且整段 php 正则（含非 ASCII 标识符字节、
  大小写不敏感的 `function`、by-reference 返回）只有 perf 有

### 未解：`discovery.py` 区5-11、`pipeline.py`(12)、`batch.py`(13)

按规则 11 结构取 main，但要逐区确认哪些是「两边不同函数」（可并存）而不是
「同一函数两版」。`discovery.py` 区6 就是可疑的一例：perf 465 行是
`_COMMON_SOURCE_REJECTION_CODES` 等新常量与辅助，main 18 行是
`_reportable_analysis_failure` —— 名字不同，很可能两个都该留。

其余未解：四个引擎测试、`TranslationStudio.tsx`(4)、`core-business-lines-ui.spec.ts`(2)、
`ELMOS_INTEGRATION_MANIFEST.json`(3)、`tooling/validate_project_synthesis_integration.py`(5)、
以及 `translationRunner.ts` 的覆盖字段收尾。

---

## 规则 11 的修订：先查引用，再谈取舍

规则 11 原文是「三个引擎文件的结构性区段取 main」。**在 `discovery.py` 上它不成立**，
已在第六轮被引用计数推翻：

    符号                          冲突区外  perf 区内  main 区内
    _analyzer_failure_verdict          1        2         0     ← perf 的
    _subject_blocker                   1       10         0     ← perf 的
    _candidate_inventory               3        0         1     ← main 的
    _preflight_inventory               2        0         1     ← main 的

**两侧的机器都被自动合并的代码引用着。** 取任何一侧都会留下未定义符号。

修订后的规则：**动手取舍之前，先统计每个候选符号在「冲突区外 / perf 区内 / main 区内」
的引用次数。** 冲突区外有引用 = 该侧不能丢。这个统计比任何关于"谁更新"的直觉都可靠，
而且几行 Python 就能做（把文件按冲突标记切成三份分别 count）。

原规则 11 关于 `functional_conversion` 链路的推理仍然成立（runner 取 main 骨架 →
报告需含 `functional_conversion` → 由 `pipeline.py` 产出 → 分母来自 `discovery.py`
的 `_candidate_inventory`/`enumeration_complete`）。它给出的是**下界**：main 那套必须在。
但它不构成上界 —— perf 那套同样必须在。

### 综合是否完整的检验

- **没有 F821**（未定义符号）→ 没有丢掉任何一侧被引用的东西
- **没有未使用的顶层定义**（F401/F811 及人工核对）→ 没有留下被架空的死代码

两个方向合起来才算证明。单看其中一个都可能自欺：只查 F821 会留下大片死代码，
只查未使用会把该留的删掉（规则 10 那次就是这么发生的）。

### `discovery.py` 现状

11 区已解 5 个：区1-4 正则（见上），区6 两套都留（顶层名完全不重叠，
且两侧符号都被区外引用）。**剩 6 个全是函数体片段**，需要逐个定位归属并综合。
`pipeline.py`(12 区)、`batch.py`(13 区) 里同类片段还有更多，合计约 31 个。

---

## 规则 12：自动合并可能把两套互不兼容的函数体交错拼在一起

到 `discovery.py` 的 `discover_unit` 才暴露出来，**这是本次合并里最重要的一条**。

区 2 与区 3 之间那段 git 认为无冲突、直接拼进来的代码：

    current = root                              # perf 的符号链接逐层检查
    for component in Path(relative).parts:
        ...
    try:
        path = candidate.resolve(strict=True)   # 需要 main 区2 定义的 candidate

而区 3 之后紧接着：

    path, content = source                      # 需要 perf 区3 定义的 source

**同一个函数体里，自动合并的部分同时依赖了两侧各自定义的变量。** `candidate` 只有取
main 的区 2 才有，`source` 只有取 perf 的区 3 才有，`path` 还会被赋值两次。
无论两个区怎么选，这个函数都是坏的。

区 5 同型：perf 那侧是 `_candidate_blocked` 闭包 + 批量 `analyze_many`，main 那侧是
逐候选 `analyze` 循环，而区 5 之后自动合并进来的注释与代码讲的是 perf 的 `analyze_many`。

### 后果：剩下的工作换了性质

`discovery.py` 的 `discover_unit` / `discover_repository` 需要**按一侧完整重建函数，
再把另一侧的增量嫁接进去**，不能逐区取舍。`pipeline.py`(12 区) 与 `batch.py`(13 区)
大概率同型 —— 它们是同一条仓库流水线的三段。

判断一个文件是否落入这一类的检验：**把某个冲突区两侧分别代入后，检查该函数体内
是否有未定义变量或重复赋值**。有，就说明自动合并已经交错，必须重建。

### 建议的重建顺序

1. 以 main 的 `discover_unit` 为骨架（其 `candidate_enumeration_*` 契约喂给
   `functional_conversion`，见规则 11 未被推翻的那半）
2. 嫁接 perf 的 `_python_subject_inventory` → `coverage_subjects` /
   `candidate_symbols` / `coverage_blockers` 三组结果键
3. 嫁接 perf 的 `analyze_many` 批量分析路径（它是本分支的性能主线之一）
4. `discover_repository` 同理：先 `_preflight_inventory`（main），
   再 perf 的 `file_results` 后处理循环
5. 每步之后跑引擎 pytest，并用规则 11 修订版的双向检验（无 F821 且无未使用顶层定义）
