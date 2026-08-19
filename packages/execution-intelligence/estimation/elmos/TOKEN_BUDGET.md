# TOKEN_BUDGET — elmos

- 模式：`verification`
- 完成定义：`production_verified`
- Monte Carlo：5000 次，seed=42
- 置信度：0.6

## 1. 整体 Token 区间

| 类别 | P50 | P80 | P90 | Worst Case |
|---|---|---|---|---|
| input（未命中缓存的输入） | 192,295,061 | 209,789,023 | 219,997,925 | 246,969,965 |
| cached_input（缓存命中读取） | 504,446,552 | 550,427,763 | 577,503,707 | 649,788,616 |
| cache_write（写入缓存） | 55,880,481 | 60,766,012 | 63,729,022 | 71,362,418 |
| output（可见输出） | 26,644,186 | 28,903,855 | 30,247,803 | 33,844,966 |
| reasoning_output（推理输出） | 16,502,593 | 17,910,244 | 18,784,843 | 20,955,009 |
| **total（分类之和）** | 795,559,011 | 867,847,847 | 909,753,569 | 1,021,266,536 |

> 五个分类互不重叠，`total` 是它们的和；任何时候都不得把 `total` 再加回某个分类。

## 2. 按任务追溯（P50 降序）

| Task | 名称 | P50 | P80 | P90 | Worst |
|---|---|---|---|---|---|
| independent-client-repos | 独立客户仓库验证（当前 0/156） | 119,201,242 | 174,945,510 | 216,032,068 | 296,656,338 |
| route-packs-66 | kotlin/react/flutter 相关 66 条路由包生成与登记 | 84,529,768 | 108,068,459 | 126,259,940 | 178,790,326 |
| matrix-medium | 全矩阵 MEDIUM 规模跑通（156 路线） | 72,396,360 | 94,543,112 | 111,743,053 | 153,569,983 |
| semantic-divergence | 13 语言两两语义分歧表与 IR 归一 | 67,788,216 | 88,480,887 | 104,786,292 | 144,638,158 |
| kotlin-analyzer | Kotlin 原生 analyzer 补齐（PENDING_ANALYZER） | 55,419,356 | 75,821,454 | 94,407,830 | 131,213,161 |
| flutter-analyzer | Flutter/Dart analyzer 补齐（PENDING_ANALYZER） | 52,994,081 | 72,174,463 | 90,612,495 | 127,983,155 |
| react-analyzer | React 方言 analyzer 补齐（PENDING_ANALYZER） | 50,539,359 | 68,053,246 | 84,219,716 | 120,740,013 |
| java-swift-regression | Java 源路线与 Swift 环境回归定向修复 | 39,730,512 | 51,743,434 | 61,438,708 | 83,068,534 |
| matrix-small | 全矩阵 SMALL 规模跑通（156 路线） | 38,569,480 | 49,238,901 | 58,366,823 | 82,897,918 |
| repo-parallel-singlepass | 仓库级并行与单遍 AST 遍历 | 29,446,503 | 37,532,268 | 44,917,569 | 62,892,417 |
| frozen-rerun-evidence | 冻结全矩阵重跑与证据收集 | 29,433,754 | 36,990,878 | 41,865,481 | 61,509,006 |
| analyzer-cache-batch | Analyzer 缓存与批量化（保住可提升/不可提升拒绝区分） | 26,051,102 | 32,771,997 | 37,953,821 | 55,455,373 |
| certification-package | 认证材料与交付包 | 21,851,589 | 27,007,363 | 29,838,388 | 45,119,559 |
| perf-baseline | 性能基线与回归门禁 | 19,501,463 | 24,562,859 | 27,847,371 | 40,691,498 |
| security-license | 安全扫描与依赖许可证核查 | 16,419,138 | 20,450,876 | 23,031,530 | 34,787,238 |
| matrix-authority-audit | 路由矩阵权威源审计与口径对齐 | 10,734,421 | 13,153,039 | 14,603,087 | 21,484,690 |

> 任务分位数之和不等于项目分位数：分位数不可相加。项目区间来自整体 Monte Carlo 抽样。

## 3. 静态语料扫描（一次性读取成本）

- 扫描根：`/sessions/rcw-01selignehxwntgsnfurjwmx/mnt/elmos`
- 计数方式：`cjk-aware-heuristic`（exact=False）
- 文件数：45,790，字符数：366,736,507
- 一次性全量读取估算：**95,021,753 tokens**
- Skill 目录常驻（name+description）：556,211 tokens，Skill 正文合计：13,804,476 tokens

| 目录 | 文件数 | 估算 tokens |
|---|---|---|
| verification-packs | 6,283 | 26,560,165 |
| client-packs | 4,793 | 20,276,057 |
| routes | 4,638 | 8,734,313 |
| agent-skills | 8,374 | 7,345,257 |
| skills | 7,739 | 6,144,810 |
| test-suites | 1,991 | 4,248,621 |
| docs | 528 | 3,477,424 |
| engines | 1,051 | 3,382,441 |
| .agents | 2,595 | 2,360,720 |
| apps | 1,801 | 2,265,097 |
| framework-packs | 125 | 1,978,912 |
| elmos-codex-skills-batch66-80-complete | 440 | 1,380,863 |
| scripts | 298 | 1,144,802 |
| modules | 618 | 1,099,861 |
| elmos-language-packs-batch81-95-complete | 250 | 699,307 |

> 静态扫描回答的是「把磁盘上的材料喂给模型一次要多少 token」，它是预测的输入，不是预测本身。

### 上下文压力告警

| 级别 | 类型 | 路径 | tokens | 说明 |
|---|---|---|---|---|
| warning | oversized-skill | `test-suites/batch1-65-slightly-strict/source-package/agent-skills/runtime/elmos-modernization-synthesis-interoperability-tests/SKILL.md` | 5,721 | SKILL.md body exceeds 5000 tokens; split references out so activation stays cheap. |
| warning | oversized-skill | `test-suites/batch1-65-slightly-strict/source-package/agent-skills/runtime/elmos-legacy-modernization-end-to-end-tests/SKILL.md` | 5,706 | SKILL.md body exceeds 5000 tokens; split references out so activation stays cheap. |
| warning | oversized-skill | `test-suites/batch1-65-slightly-strict/source-package/agent-skills/runtime/elmos-complete-package-release-certification-tests/SKILL.md` | 5,645 | SKILL.md body exceeds 5000 tokens; split references out so activation stays cheap. |
| warning | oversized-skill | `test-suites/batch1-65-slightly-strict/source-package/agent-skills/runtime/elmos-checkpoint-resume-failure-recovery-tests/SKILL.md` | 5,642 | SKILL.md body exceeds 5000 tokens; split references out so activation stays cheap. |
| warning | oversized-skill | `test-suites/batch1-65-slightly-strict/source-package/agent-skills/runtime/elmos-secret-privacy-redaction-tests/SKILL.md` | 5,638 | SKILL.md body exceeds 5000 tokens; split references out so activation stays cheap. |
| warning | oversized-skill | `test-suites/batch1-65-slightly-strict/source-package/agent-skills/runtime/elmos-lifecycle-state-machine-cancellation-tests/SKILL.md` | 5,636 | SKILL.md body exceeds 5000 tokens; split references out so activation stays cheap. |
| warning | oversized-skill | `test-suites/batch1-65-slightly-strict/source-package/agent-skills/runtime/elmos-supply-chain-provenance-sbom-tests/SKILL.md` | 5,634 | SKILL.md body exceeds 5000 tokens; split references out so activation stays cheap. |
| warning | oversized-skill | `skills/batch_01_to_44_complete_skill_system/batch_05_target_language_lowering_complete_skill_pack/SKILL.md` | 5,630 | SKILL.md body exceeds 5000 tokens; split references out so activation stays cheap. |
| warning | oversized-skill | `skills/modernization-skills-batch-01-44/batch_05_target_language_lowering_complete_skill_pack/SKILL.md` | 5,630 | SKILL.md body exceeds 5000 tokens; split references out so activation stays cheap. |
| warning | oversized-skill | `test-suites/batch1-65-slightly-strict/source-package/agent-skills/runtime/elmos-scale-performance-cost-budget-tests/SKILL.md` | 5,625 | SKILL.md body exceeds 5000 tokens; split references out so activation stays cheap. |
| warning | oversized-skill | `test-suites/batch1-65-slightly-strict/source-package/agent-skills/runtime/elmos-deployment-rollout-rollback-dr-tests/SKILL.md` | 5,623 | SKILL.md body exceeds 5000 tokens; split references out so activation stays cheap. |
| warning | oversized-skill | `test-suites/batch1-65-slightly-strict/source-package/agent-skills/runtime/elmos-project-synthesis-end-to-end-tests/SKILL.md` | 5,620 | SKILL.md body exceeds 5000 tokens; split references out so activation stays cheap. |
| warning | oversized-skill | `test-suites/batch1-65-slightly-strict/source-package/agent-skills/runtime/elmos-build-test-repair-anti-cheating-tests/SKILL.md` | 5,618 | SKILL.md body exceeds 5000 tokens; split references out so activation stays cheap. |
| warning | oversized-skill | `test-suites/batch1-65-slightly-strict/source-package/agent-skills/runtime/elmos-artifact-graph-traceability-tests/SKILL.md` | 5,616 | SKILL.md body exceeds 5000 tokens; split references out so activation stays cheap. |
| warning | oversized-skill | `test-suites/batch1-65-slightly-strict/source-package/agent-skills/runtime/elmos-policy-capability-least-privilege-tests/SKILL.md` | 5,615 | SKILL.md body exceeds 5000 tokens; split references out so activation stays cheap. |

## 假设与排除项

- 假设：Seeded by the scope auditor from measured repository facts plus configured defaults.
- 假设：Durations and token profiles are seeds, not measurements; calibrate after the first milestone.
- 排除：Human approval and acceptance time (carried in human_assisted).
- 排除：Vendor pricing (supply a verified rate card).

> 执行后必须用真实 usage 回填 `calibrate`，再重新出预测。未校准的预测不构成任何承诺。
