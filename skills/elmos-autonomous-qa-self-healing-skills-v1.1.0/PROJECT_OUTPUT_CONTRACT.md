# Elmos 项目产出与测试文件集契约

## 1. 目标

本契约定义 Elmos 在项目生成、语言/框架转换、老项目翻新、功能迭代和自动修复后，必须向用户交付的文件集合。测试源文件不是内部中间状态，而是与业务代码同级的正式项目资产。

## 2. 交付根目录

默认不可变交付目录：

```text
deliverables/{project_id}/{revision_id}/
├── project/                         # 最终项目源码；测试位于技术栈原生目录
├── qa/
│   ├── plans/                       # 测试计划、风险与覆盖策略
│   ├── traceability/                # 需求—代码—测试—证据矩阵/图
│   ├── results/                     # 结构化执行结果、JUnit XML 等
│   ├── reports/                     # 管理报告、工程报告、HTML/JSON
│   ├── evidence/                    # 日志、Trace、截图、视频、HAR、快照
│   ├── coverage/                    # 代码/需求/变异覆盖率
│   ├── performance/                 # 性能、压力、容量、耐久结果与基线
│   ├── security/                    # 安全发现、扫描结果、例外审批
│   ├── defects/                     # 缺陷、最小复现与根因分析
│   ├── repairs/                     # 修复计划、补丁、回滚与验证证据
│   └── certificates/                # 门禁结果与发布证书
├── replay/                          # 一键重放脚本、容器/环境说明
├── manifests/
│   ├── project-output-manifest.json # 全部产出文件、哈希、来源与状态
│   ├── test-artifact-set.json       # 测试文件集索引
│   ├── evidence-manifest.json       # QA 证据索引
│   ├── provenance.jsonl             # 生成/修改谱系事件
│   └── checksums.sha256             # 文件完整性校验
├── bundles/
│   ├── {project}-{revision}-project-with-tests.zip
│   ├── {project}-{revision}-tests-only.zip
│   ├── {project}-{revision}-qa-evidence.zip
│   └── {project}-{revision}-repair-patches.zip  # repair/certify 可选
└── DELIVERY_SUMMARY.md
```

交付目录不得包含依赖缓存、`.git`、本地密钥、生产凭据、无关构建缓存或未经批准的生产数据。

## 3. 项目中的原生测试目录

测试必须进入目标生态可直接运行的原生位置，而不是统一塞入一个无法被构建工具识别的目录。适配器按 `mappings/native-test-layouts.yaml` 选择路径。例如：

| 生态 | 原生输出位置 |
|---|---|
| Java/Kotlin Maven | `src/test/java`、`src/test/resources`，集成测试可使用 `src/it` 或独立测试模块 |
| Gradle | `src/test/*`、`src/integrationTest/*` 与对应 sourceSet |
| Python | `tests/unit`、`tests/integration`、`tests/api`、`tests/e2e` |
| C#/.NET | 独立 `*.Tests`、`*.IntegrationTests` 项目并加入解决方案 |
| Go | 包内 `*_test.go`；跨包/E2E 可置于 `tests/` 或专用测试模块 |
| Rust | 模块内 `#[cfg(test)]`、`tests/`、`benches/`、`fuzz/` |
| C/C++ | `tests/` 与 CMake/Meson 测试目标 |
| PHP | `tests/Unit`、`tests/Feature`、`tests/Integration` |
| JS/TS/React/Vue | `tests/`、`__tests__/`、`e2e/`、`performance/`，并更新 package scripts |
| Swift/Objective-C | XCTest Target、`Tests/`、UI Test Target |
| Flutter | `test/`、`integration_test/`、`test_driver/`（旧项目兼容） |

视觉基线、Mock、Fixture、测试数据、性能脚本和安全配置也必须进入构建工具或测试运行器可发现的位置，并在 Manifest 中分类。

## 4. Test Artifact Set 的组成

`tests-only` Bundle 至少包含：

- 测试源代码：unit、component、functional、integration、contract、API、DB、message、workflow、UI、E2E、visual、accessibility、compatibility、performance、load、stress、spike、soak、capacity、security、resilience、chaos、recovery、property、fuzz、mutation；
- 框架配置：测试 runner、覆盖率、并行度、超时、浏览器/设备矩阵、性能阈值；
- Fixture、Factory、Seed、Mock、Stub、虚拟服务、Schema 和脱敏数据；
- 视觉基线、性能基线和批准元数据；
- 本地运行、容器运行和 CI 运行入口；
- `GENERATED_TESTS_README.md`、需求追踪矩阵和测试文件 Manifest；
- 复现失败所需的最小输入与重放命令。

不得把第三方依赖二进制、包管理器缓存或容器镜像直接塞进 tests-only Bundle；只提供锁文件、镜像摘要和重建说明。

## 5. 文件级元数据

每个产出文件至少记录：

- `artifact_id`、`category`、`role`、相对路径、内容类型、字节数、SHA-256；
- `project_id`、`revision_id`、`run_id`、输入 `snapshot_id`；
- 生成/修改该文件的 Skill、Adapter、模型/工具版本和时间；
- 对应的 `requirement_refs`、`test_case_refs`、`defect_refs`、`patch_refs`；
- 语言、框架、测试类型和原生测试 Target；
- 验证状态：`generated`、`syntax_valid`、`buildable`、`discovered`、`executed`、`certified`、`blocked`；
- 保留等级、敏感信息扫描状态和签名/校验信息。

同一内容使用内容寻址去重，但 Manifest 中仍保留每个逻辑路径和谱系。

## 6. 生成与物化顺序

1. 统一 Test DSL 生成测试语义。
2. 选择目标语言、框架、构建系统和原生目录。
3. 生成测试源代码、配置、Fixture、Mock、数据、基线和运行器。
4. 在隔离工作树中原子写入；禁止写到根目录外。
5. 执行格式化、语法、静态检查和测试发现。
6. 构建测试 Target，并运行最小冒烟用例。
7. 将文件逐个登记到 `project-output-manifest.json` 和 `test-artifact-set.json`。
8. 执行完整测试；生成结果和证据。
9. 自动修复后重新计算受影响文件哈希，保留前后谱系。
10. 生成三套 Bundle、校验和和交付摘要；最后原子发布。

## 7. 输出模式

### 7.1 embedded

- 在项目 Worktree 中生成测试文件；
- 以 Git Patch、分支或完整源码包交付；
- 适合用户希望测试直接进入仓库的场景。

### 7.2 sidecar

- 输入仓库只读；
- 在 `deliverables/.../project/` 中创建完整项目副本并加入测试；
- 适合只读仓库、评估任务或不允许 Agent 直接改仓库的场景。

### 7.3 both（默认）

- 生成可审查 Patch/Worktree；
- 同时发布不可变完整项目包和 tests-only Bundle；
- 用户可以选择应用补丁或直接下载完整项目。

## 8. 质量门禁

项目产出通过门禁必须满足：

- 非 `plan-only` 运行存在 `project-output-manifest.json`；
- 每个 Required 测试用例至少对应一个物化产物；
- 每个测试源文件均有 SHA-256、生成谱系、需求引用和测试用例引用；
- 生成测试能被目标框架发现；P0/P1 测试 Target 可构建；
- 不存在空测试、禁用测试、静默 skip、无解释快照更新或无界重试；
- tests-only Bundle 和 project-with-tests Bundle 均可解压、校验和一致、路径安全；
- 重放入口存在，并使用固定依赖版本/锁文件；
- Secrets/凭据扫描为零；
- 运行失败时仍发布 `partial`/`failed` Bundle，且不得声称已认证。

## 9. 版本与生命周期

- `revision_id` 由项目版本、输入快照和产出策略共同确定；同一输入与同一生成器版本应生成可比较的稳定结果。
- 需求、代码、测试策略或 Adapter 变化时，标记受影响测试为 `stale`，重新生成并验证。
- 新产出发布后，旧产出标记 `superseded`，按保留策略保存；发布认证与安全事件可进入长期保留或 legal hold。
- 删除采用引用计数和两阶段回收；任何 Manifest、证书或审计记录仍引用的对象不得被回收。

## 10. 用户可操作性

最终交付摘要必须明确给出：

- 如何安装依赖；
- 如何运行全部测试、单类测试、指定用例和失败重放；
- 如何更新视觉/性能基线以及需要的审批；
- 哪些测试已执行、哪些被阻塞及原因；
- 测试文件所在路径、对应需求和最近一次验证状态；
- 系统自主生成/执行的 wall-clock 时间、实际耗时和人工等效时间。
