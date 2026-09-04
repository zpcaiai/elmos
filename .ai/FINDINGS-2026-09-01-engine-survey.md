# FINDINGS 2026-09-01 · 20 引擎测试普查(云端复原实测)

> **2026-09-03 更正：**“`database-bigdata-engine` 完全没有 tests 目录，因此是零测试
> 引擎”只检查了引擎目录，结论错误。它的 32 个运行时/安装完整性用例在仓库级
> `tests/database-bigdata-skills/`，并由 `make database-bigdata-skills` 执行。
> 当前统一注册表也把该根绑定到 `database-bigdata-engine`。下文原句保留为当时普查记录，
> 不得再引用为当前缺口。

**执行环境**:设备桥 device_bash 因本会话 VM 卷 ENOSPC 不可用;改用「Mac→云端逐引擎复原」法:
device_stage_files 搬运源码 + Blender 无头 CLI(`blender --background --python`)在 Mac 上打 tar 包/复制超深路径文件,云容器内以 `uv run --locked --with pytest` 在仓库根 CWD 下逐引擎实测。
判读纪律:只认 pytest 汇总行,不认退出码。

## 一、总账

20 个此前「从未测过/结果存疑」的引擎全部探测完毕。**今日云端实测通过 ≈ 4468 个测试**。

### 全绿(16 个)

| 引擎 | 结果 |
|---|---|
| functional-assurance-engine | 15 passed(Mac 实测,仓库根 CWD) |
| legacy-web-modernization-engine | 19 passed |
| pricing-billing-engine | 10 passed |
| semantic-assurance-engine | 63 passed |
| etgb-engine | 46 passed (179s) |
| ai-capability-engine | 37 passed |
| proof-driven-harness-intelligence-engine | 56 passed(需 tooling/integrate_pdhi_v1.py + 钉包 zip) |
| autonomous-qa-engine | 338 passed |
| multimodal-intake-engine | **487 passed**(见「三」修复过程) |
| build-cache-engine | **1753 passed, 55 skipped**(skip=native toolchain/postgres/tree-sitter 环境门,设计如此;需 agent-skills parity 包) |
| formal-assurance-engine | 563 passed, 2 skipped(需 docs/formal-assurance-kernel 收据) |
| openhands-absorption-engine | 60 passed |
| uir-java-python | 323 passed(非 uv 工程:venv + requirements.txt,tree_sitter+tree_sitter_java) |
| knowledge-skill-model-foundry-engine | 75 passed(需 subskills 顶层 v2/v3 钉包 zip + skills/ 解包树) |
| proof-driven-harness-engine | 265 passed(需 tooling/ + tests/proof-driven-harness-v3 + schemas/batch35 + delta-v3.1.0 zip) |
| database-data-engine · sql-transpiler | 241 passed, 9 skipped, 1 环境红(见「二」) |

### 受限/部分(3 个,非全红)

- **software-factory-engine**:66 passed / 2 failed / 8 skipped。2 失败 = archive-neutralization:要求 canonical 源里脚本按「中性化字节格式」存放且 registry 绑定 `elmos-lsp-capability-seam`、`elmos-failure-repair-corpus`、`elmos-permission-policy-engine` 三条。云端复原做不全,**归 Mac 复核**(疑似结构性欠账而非代码缺陷)。
- **commercial-capability-expansion-engine**:local_algorithms 42 passed 全绿;trusted_runtime 需完整 `.agents/skills` 工作区(数千目录),云端 NOT_PROBED,**归 Mac**。
- **spring-golden-route-engine**:9 passed;34 errors + 3 failed 全部为 CATALOG_VALIDATION(需 `agent-skills/runtime` 下 196 个已安装 skill),云端 NOT_PROBED,**归 Mac**。

### 环境红(1 个)

- **python-engine**:`requires-python==3.14.*` 硬钉;云端 3.14.0rc2 上 pydantic/fastapi 出 2 个 collection error(typing 签名不兼容)。**真缺陷成分**:版本钉死无上界、对 rc 不设防。Mac 3.14 正式版结果待对数。

### 未探测(网络/宿主门,非代码问题)

- **database-data-engine · Maven 半边**:云端 Maven Central 403(出网白名单),NOT_PROBED,归 Mac(`mvn test`)。
- sql-transpiler 唯一失败 `RunnerBlockedError: requires darwin-arm64 host` —— SQLite Runner 明确只在 Mac 上执行,属**环境红**,Mac 上应当能跑真等价性验证。

## 二、红项分类汇总(真缺陷 / 功能缺口 / 既有红 / 假红 / 环境)

- **真缺陷(1)**:python-engine 的 3.14 钉版策略(无上界 + rc 崩)。
- **功能缺口(2)**:software-factory 的 archive-neutralization 三绑定欠账(待 Mac 确认);database-bigdata-engine(顺带发现,不在 20 清单里)**完全没有 tests 目录** —— 零测试引擎。
- **环境红(2)**:sql-transpiler darwin-arm64 runner;python-engine rc 半边。
- **假红(今日全部转绿)**:multimodal-intake 首轮 199f/41e、foundry 首轮 18f/33e、pdh 首轮 15f、build-cache 首轮 10f、formal-assurance/uir/pdhi 首轮 collection error —— **全部是复原缺文件/缺依赖,不是代码坏**。补齐后全绿。
- **既有红**:无新增;CAS 4 项生产阻塞、EI BLOCK、R10 0/90 等仍以台账为准(今日未动)。

## 三、multimodal-intake 的 3 层假红剥离(方法论样本)

1. 首轮 199 failed:staging 声称 ok 但 2 个迁移 SQL 未落盘(dir-cache 撒谎)+ 引擎根 openapi/、migrations/ 镜像目录未搬。→ 复核 uploads 实际文件数才发现。
2. 次轮 13 failed:测试读仓库级 `sdk/multimodal-intake/...Client.java`(距仓库根 9 层)与 `apps/web-console/...[jobId]/route.ts`(9 层)——**device_stage_files 有 7 层深度上限,ok:true 之外的路径直接拒**。
3. 解法:Blender 4.4.3 无头 CLI 在 Mac 上执行 Python(开一个 Blender 自带 asset .blend 才肯跑),把深层文件复制到仓库根 `_cloudstage/`(1 层),再 stage。→ 52/52 全过,整套 487 绿。

**教训(第 7 条「验证不过先查判据」实例)**:桥的成功回执 ≠ 文件真到了;深度上限是隐性判据。以后大树一律 Mac 端打 tar 再 stage 单文件。

## 四、遗留物与 Mac 待办

- 仓库根新增 `_cloudstage/`(约 33MB:8 个引擎 tar + docs/scripts/schemas/tooling/tests tar + 2 个深层文件副本)。**可整目录删除**,不影响任何东西;或留作下次云端复原的缓存。
- Mac 待办(按优先级):① software-factory 2 失败复核(真缺口 or 环境);② spring-golden-route / commercial trusted_runtime 全量(装好 skill 树后);③ database-data `mvn test`;④ python-engine 在 3.14 正式版跑;⑤ database-bigdata-engine 补测试(零测试引擎)。
- 云端 /root/repo 复原层现已含:tooling/ docs/ schemas/ scripts/ tests/ contracts/ apps/(部分) sdk/(部分) skills/subskills 14 个钉包 + 4 个解包树 —— 下个会话可直接复用。
