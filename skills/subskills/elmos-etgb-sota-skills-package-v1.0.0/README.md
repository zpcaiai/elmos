# Elmos ETGB SOTA Skills Package v1.0.0

**ETGB — Elmos Enterprise Transformation & Generation Benchmark** 是 Elmos 四条核心业务线的统一测试与发布认证体系：

1. Spring 老项目现代化；
2. 全库跨语言转换；
3. 多语言项目生成；
4. SQL 方言与 SQL routine 转换。

本包不是只有测试计划文档，而是包含：

- 可展开为万级具体实例的能力矩阵；
- 已物化的 JSONL 全覆盖测试用例；
- 可运行的 `etgb` Python CLI；
- 多 Oracle、差分执行、状态副作用、变形、模糊、变异、故障注入规范；
- 四条业务线各一个完全离线可运行的 smoke fixture；
- 公共 GitHub 基准仓库 commit 锁定清单；
- CI、评分、SSER、发布门禁与证据包格式；
- 10 个可直接纳入 Elmos Agent/Skill 系统的 `SKILL.md`。

> “全覆盖”在本包中指：对 `matrices/coverage-requirements.yaml` 声明的 ETGB v1.0 能力模型达到 100% capability-cell 覆盖；它不宣称覆盖未来尚未纳入模型的所有语言、框架或数据库特性。

## 目录

```text
skills/       Agent/Skill 执行规范
matrices/     四条业务线与横切质量属性的能力矩阵
suites/       物化后的具体测试用例、索引和统计
schemas/      测试用例、结果、语料锁定、需求契约 JSON Schema
etgb/         可执行 CLI、Runner、Oracle、评分与报告
fixtures/     四个离线 smoke fixtures
docs/         SOTA 测试计划、门禁、治理、集成指南
corpora/      公共仓库锁定与许可证审查状态
.github/      CI 示例
scripts/      安装、自检、语料拉取和证据包脚本
```

## 立即运行

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]

etgb validate
etgb coverage
etgb run --profile smoke --output reports/smoke-results.jsonl
etgb score reports/smoke-results.jsonl --output reports/smoke-score.json
pytest -q
```

也可以直接：

```bash
make verify
```

## 核心判定原则

- **执行结果优先于文本相似度**：编译成功不是行为等价。
- **目标状态必须比较**：数据库行、消息、文件、缓存、事务和异常都属于输出。
- **P0 不允许静默语义错误**：P0 `SSER = 0`。
- **不能可靠转换时必须显式拒绝或升级人工审查**，不可伪装成功。
- **公共语料固定 commit**，不允许发布门禁跟随上游 `main` 漂移。
- **模型与 Skill 评测使用时间切分和 hidden tests**，降低训练污染与提示过拟合。

## 运行档位

| Profile | 用途 | 典型频率 |
|---|---|---|
| smoke | Runner 与基础 Oracle 自检 | 每次提交 |
| pr | P0 micro/fixture + 受影响矩阵 | 每个 PR |
| nightly | P0/P1 + 属性/变形/故障注入 | 每夜 |
| weekly | 公共仓库、大矩阵、多随机种子 | 每周 |
| release | 全量门禁、许可证、证据包 | 发布前 |
| golden | 客户/大型仓库 Golden Route | 按候选版本 |
| exhaustive | 全矩阵、模糊、变异、长稳测试 | 专项 |

## 发布硬门

- P0 关键行为、事务、数据、安全 Oracle：100% 通过；
- P0 Silent Semantic Error Rate：0；
- 数据损坏、越权、安全策略退化：0；
- P0 flaky：0；
- 语料 commit 全部固定，许可证审查无阻断项；
- P1 加权通过率至少 98.5%，P2 至少 95%；
- 所有声称成功的转换必须产生可追溯 evidence bundle。

详见 `docs/SOTA_TEST_PLAN.md` 与 `docs/RELEASE_GATES.md`。
