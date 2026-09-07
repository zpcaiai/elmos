# ELMOS 生成/跨库转换的准确度与完整度——实测评估

日期：2026-08-21
状态：`LOCAL_EXECUTED` / `NOT_CERTIFIED` / 独立验证 `NOT_RUN`
问题：「elmos 目前生成中小型项目、跨库转换的准确度和完整度究竟能达到多少，能不能准确评估出来」

---

## 0. 一句话结论

**能准确评估，而且今天已经测出来了。** 但测出来的东西和问题的措辞不太一样：

三条业务线的转换/生成核心都是**确定性**的（OpenRewrite 重写、模板发射、UIR 提升），
在各自的精确支持子集里「准确度」不是变量——要么进得去、要么被显式拒绝。
真正的变量是**完整度**，也就是**真实项目里有多大比例的东西能进入那个子集**。

这个数今天第一次在真实语料上测了出来：

| 业务线 | 完整度实测 | 准确度实测 |
| --- | --- | --- |
| 跨语言/跨库转换 | **0 / 16,046**（20 个真实 Python 项目的全部覆盖主体，无一进入子集） | 子集内 366 次行为比对全通过，但样本全是单函数夹具 |
| 多语言项目生成 | **24 / 48** 个 profile 组合可用；6/8 语言只能生成**单实体**；生产 profile 只支持 4 种关系里的 1 种；5 种项目形态只支持 1 种 | 16/16 生成→构建→启动→CRUD/RLS 全通过（2026-07-28 实跑） |
| Spring 现代化 | 4 个精确元组；参考工程是**一个** `OrderController.java` | 4/4 端到端通过，行为等价由**每条路线 3 个探针**建立 |

下面每个数字都附了产生它的命令和原始证据文件。

---

## 1. 跨语言/跨库转换

### 1.1 今天新跑的测量：真实仓库准入率

**语料**：从 PyPI 拉的 20 个真实中小型 Python 项目源码分发包（sdist），
按声明规则选取——高下载量纯 Python 库 + 5 个刻意挑的**对本引擎最有利**的
算法/数值型库（`mpmath`、`sortedcontainers`、`more-itertools`、`semver`、`cachetools`）。
sdist 的 SHA-256 全部记录在 `corpus-manifest.txt`。

**仪器**：引擎自己的两层，不是我重写的判断——
- `elmos_polyglot_route.project_graph.python_coverage_subjects`（覆盖清单，含 `candidate` 与结构阻断码）
- `elmos_polyglot_route.python_analyzer.analyze_python`（语义子集判定）

**结果**（排除测试文件；含测试的版本见第二份 JSON）：

```
583 个源文件 / 7,056,861 字节
      ↓
16,046 个 coverage subject     ← 引擎认定「完整转换必须覆盖」的全部主体
      ↓
 2,609 个 candidate（16.3%）    ← 顶层函数，其余全是类/嵌套/模块级效应
      ↓
 1,469 个进到语义检查（9.2%）   ← 无结构阻断（无装饰器/默认值/*args/**kwargs/async）
      ↓
   109 个通过类型闸门（0.68%）
      ↓
     0 个 READY（0.000%）
```

含测试文件时规模翻倍、结论不变：999 文件 / 12.6 MB / **31,952 个 subject → 0 READY**。

**阻断码分布**（结构层，按出现次数）：

| 阻断码 | 次数 |
| --- | --- |
| `PYTHON_TOP_LEVEL_EFFECT_CONVERSION_UNCOVERED` | 7,784 |
| `PYTHON_NESTED_SYMBOL_CONVERSION_UNCOVERED` | 4,596 |
| `PYTHON_FUNCTION_SIGNATURE_CONVERSION_UNCOVERED` | 1,995 |
| `PYTHON_CLASS_SYMBOL_CONVERSION_UNCOVERED` | 1,114 |
| `PYTHON_DECORATED_SYMBOL_CONVERSION_UNCOVERED` | 1,009 |
| `PYTHON_CLASS_DEFINITION_EFFECTS_UNCOVERED` | 878 |
| `PYTHON_ASYNC_FUNCTION_CONVERSION_UNCOVERED` | 44 |

**语义层**（1,469 个候选）：

| 拒绝码 | 次数 | 占比 |
| --- | --- | --- |
| `PYTHON_PARAMETER_TYPE_REQUIRED` | 1,175 | 80.0% |
| `PYTHON_RETURN_TYPE_REQUIRED` | 185 | 12.6% |
| `PYTHON_UNSUPPORTED_STATEMENT` | 94 | 6.4% |
| `PYTHON_UNSUPPORTED_EXPRESSION` | 14 | 1.0% |
| `PYTHON_UNANNOTATED_ASSIGNMENT_...` | 1 | 0.1% |

### 1.2 三个只有跑真实语料才能看见的事实

**（1）卡住的不是 IR 表达力，是类型面。**
92.6% 的候选在「参数/返回类型」这一关就死了，根本没走到语句/表达式覆盖判定。
把这一关拆开看（`annotation_breakdown.py`）：

- 参数注解：缺失 1,350 / 已注解但类型不在规范四类 683 / 规范 345
- 返回注解：缺失 739 / 已注解但不在规范四类 477 / 规范 253
- **签名完全规范的候选：109 个（占 1,469 的 7.4%）**

也就是说，「让用户补类型标注」这条路只能救一半——**另一半人已经标了，
标的是 `bytes`(61)、`Path`(47)、`str | None`(35)、`t.Any`(31)、`list[str]`(9)…**
规范类型只有 `int/float/bool/str` 四个，连 `None` 返回值（68 次）和 `bytes` 都不在内。

**（2）一个 docstring 就足以让函数出局。** 实测最小对：

```python
def calculate(quantity: int, price: int) -> int:
    """Return the line total."""      # ← 有这一行：PYTHON_UNSUPPORTED_STATEMENT:Expr
    return quantity * price           # ← 删掉这一行：READY
```

在 109 个签名完全规范的候选里，94 个死于 `UNSUPPORTED_STATEMENT`，其中绝大多数就是 docstring。

**（3）但把 docstring 全剥掉重测，收成仍然是 1 个。**
剥离后重跑 109 个候选：58 个 `UNSUPPORTED_EXPRESSION`（调用/属性访问）、
25 个 `UNANNOTATED_ASSIGNMENT`、21 个 `UNSUPPORTED_STATEMENT`（真语句：for/try/with/raise）、
3 个 `FLOORED_MODULO`、1 个 `UNSUPPORTED_LOCAL_TYPE`、**1 个 READY**：

```
humanize-4.16.0 | src/humanize/i18n.py | _gettext_noop
def _gettext_noop(message: str) -> str: return message
```

一个恒等函数。这就是 20 个真实项目、7 MB 源码、在最宽松的假设下的全部产出。

**这不是「测出来准确度低」，是「几乎没有东西能进入被测集合」。**
先前 `.ai/python-let-real-repository-measurement-2026-08-20.json` 在 langgraph 单仓
（447 文件 → 结构候选 2 → READY 0）得到的结论，在 20 倍规模上复现且更精确。

### 1.3 仓库里已有证据的实际规模

不靠文档，直接数 `routes/`：

- `routes/*/route.json`：**176 条**，`limited` 110 / `research` 66
- `routes/*/certification/evidence.json`：`execution_status` = `PASSED_LOCAL` **38** / `NOT_RUN` **72**
- `certification_status`：**296 个文件全部 `NOT_CERTIFIED`**，无一例外
- 全部路线证据里的行为比对总数：**366 次**
  （development 114 / holdout 130 / representative 122，38 条路线平均 9.6 次）
- 每条路线的开发语料就是一个文件：`Pricing.java` → `migrated.py`，`behavior_case_count = 3`

所以跨语言线目前的**全部**行为等价证据 = 366 次单函数比对。
`docs/batch29/ROUTE_MATRIX.md` 自己写着：没有任何 SMALL/MEDIUM 仓库战役把任何路线的
仓库执行状态抬到 `NOT_RUN` 之上。这一条与上面的实测互相印证。

### 1.4 这条线能不能「准确评估」

能，但要先换指标。**「跨库转换准确度 = ?%」这个问法在当前状态下没有可测对象**——
分母（进入转换的单元）在真实仓库上是 0。可测且已测的是：

- **准入率**（完整度）：0 / 16,046，且各拒绝码归因清楚 → 今天已给
- **子集内正确率**（准确度）：366/366 通过，但样本是单函数 → 已有
- 只有当准入率非零之后，「整仓准确度」才成为一个有分母的量

---

## 2. 多语言项目生成

### 2.1 今天新跑的测量：请求面准入扫描

**仪器**：引擎自己的 `intake.create_draft` / `approve_request` /
`workspace.generate_workspace`（生成是纯 Python，云端可跑；构建/启动验证需要钉死的
macOS 工具链，本次 **NOT_RUN**，没有当成通过记）。

**（1）profile 组合：48 格中 24 格可用**

| 组合 | 结果 |
| --- | --- |
| `in-memory` + `none` × 8 语言 | ACCEPTED |
| `postgresql` + `jwt` × 8 语言 | ACCEPTED |
| `postgresql` + `oidc` × 8 语言 | ACCEPTED |
| `in-memory` + `jwt` × 8 | `PROFILE_COMBINATION_UNSUPPORTED` |
| `in-memory` + `oidc` × 8 | `PROFILE_COMBINATION_UNSUPPORTED` |
| `postgresql` + `none` × 8 | `PROFILE_COMBINATION_UNSUPPORTED` |

即：要么全无（内存+无鉴权），要么全有（PG+鉴权），中间态一律拒绝。

**（2）实体数：6/8 语言硬上限 = 1 个实体**

生产 profile（postgresql + jwt）下按实体数递增实跑生成：

| 语言 | 1 | 2 | 5 | 20 | 21 |
| --- | --- | --- | --- | --- | --- |
| java | 57 文件 | 61 | 73 | 133 | `ENTITY_LIMIT_EXCEEDED` |
| python | 53 文件 | 53 | 53 | 53 | `ENTITY_LIMIT_EXCEEDED` |
| csharp / typescript / go / kotlin / php / rust | 49–56 文件 | **`*_PRODUCTION_PROFILE_SINGLE_ENTITY_ONLY`** | 同左 | 同左 | — |

python 的文件数不变但内容在长（134 KB → 379 KB @20 实体），java 是 148 KB → 470 KB，
两者都真实随实体数扩展；其余六个目标在第 2 个实体上直接拒绝。

**（3）关系种类：生产 profile 下 4 选 1**

| 关系 | postgresql+jwt | in-memory+none |
| --- | --- | --- |
| `many-to-one` | ACCEPTED | ACCEPTED |
| `one-to-one` | 被转成待答问题，无法批准 | ACCEPTED |
| `one-to-many` | 同上 | ACCEPTED |
| `many-to-many` | 同上 | ACCEPTED |

`many-to-many`（几乎每个真实业务系统都有的中间表）在带库的 profile 里不可用；
另外生产 profile 强制关系图**无环**（`PRODUCTION_RELATION_CYCLE`）。

**（4）项目形态：5 选 1**

`api` ACCEPTED；`fullstack` / `worker` / `cli` / `modular-monolith` 全部
`PROJECT_KIND_INVALID`（源码里标为 PLANNED，未进入契约）。

**（5）字段类型只有 5 种**：`string / integer / number / boolean / datetime`。
没有 decimal/money、enum、uuid、json、数组、二进制。对「中小型业务项目」而言，
金额字段只能用 `number`（浮点）表达。

### 2.2 已有的实跑证据（不是我跑的，是仓库里的）

`docs/project-synthesis/local-production-profile-matrix.json`（2026-07-28，
macOS-26.5.2-arm64，Python 3.12.9）：

- 16 个案例（8 语言 × jwt/oidc）**全部 PASSED**，`exact_toolchain_match` 全 true
- 每例包含生成 + 精确工具链构建 + 启动探针 + CRUD + RLS 跨租户隔离 + 清理
- 生成文件数 44–56；`entity_shape`：java/python 是 multi-entity（2 实体 1 关系），其余六个 single-entity
- `production_delivery_status` / `external_certification_status` / `independent_verification_status` 全 `NOT_RUN`，`certification_status` = `NOT_CERTIFIED`

### 2.3 生成的东西到底是什么

java、单实体、生产 profile，实跑生成 58 个文件（生成清单记 `file_count = 57`，
差的一个是清单文件自身），其中 **`.java` 文件只有 12 个**——10 个主源 + 2 个测试：

```
Application / api: Entity1, Entity1Controller, HealthController, UpsertEntity1Request
persistence: DataSourceConfiguration, Entity1Repository, TenantTemplate
security: SecurityConfiguration, TenantIdentity
test: ProductionIntegrationTest, TenantTemplateContractTest
```

其余 46 个是 docs（8）、requirements 契约（9）、operations（4）、database 迁移（4）、
security/observability 契约（4）、CI/Docker/deploy（7）、application.yml、openapi.yaml 等。

**结论**：这条线的准确度是可信的（16/16 实跑通过，确定性发射）；
完整度上它是一个**规范驱动的生产级 CRUD 脚手架生成器**，不是「中小型项目生成器」——
一个真实中小型项目通常有 5–20 个实体、多种关系、枚举与金额类型、后台任务或前端，
其中除 java/python 外的六个目标在第二个实体处就停了。

---

## 3. Spring 老项目现代化

`evidence/spring-routes/*.json`，4 个精确元组：

| 路线 | 源 | 目标 | 结果 |
| --- | --- | --- | --- |
| boot-1.5-java-8 | Boot 1.5.22.RELEASE / Java 8 | Boot 3.5.3 / Java 21 | `PASSED_LOCAL` |
| boot-2.0-2.6 | Boot 2.3.12.RELEASE / Java 11 | 同上 | `PASSED_LOCAL` |
| boot-2.7 | Boot 2.7.18 / Java 17 | 同上 | `PASSED_LOCAL` |
| boot-3.0-3.4 | Boot 3.4.1 / Java 17 | 同上 | `PASSED_LOCAL` |

四条都是真跑：源构建 PASSED → OpenRewrite（rewrite-maven-plugin 6.44.0 /
rewrite-spring 6.35.0）→ 目标构建 PASSED → 启动 + `/actuator/health` UP →
行为比对 `behavioral_parity = true`。

**完整度边界**：
- 参考工程是**一个** `OrderController.java`
- 行为等价由 **3 个探针**建立（`probe_ids = [42, 7, 1001]`，比对三个 JSON 响应体）
- `authorized_customer_repository` / `independent_verification` / `rootless_runner` /
  `external_evidence_status` 全 `NOT_RUN`；`certification_status` = `NOT_CERTIFIED`
- 每条路线绑定**一个精确版本元组**，不是版本区间；Gradle 精确元组仍 `NOT_RUN`

这条线是三条里**唯一**做到「源→改→目标→跑→比对」完整闭环的，
但深度是 1 个控制器 / 3 个响应体。它是「窄而深」的代表；
跨语言线是「宽而浅」——176 条路线、366 次单函数比对、真实仓库准入率 0。

---

## 4. 怎么才算「准确评估出来」——建议的指标口径

当前 README 与闭环矩阵用的是状态词（`PASSED_LOCAL` / `LIMITED` / `NOT_RUN`），
没有连续量，所以「能达到多少」无法回答。建议补三个有分母的指标：

1. **准入率 `ready / coverage_subjects`**——完整度。今天已对 Python 源测出 0/16,046。
   `tools/measure_repository_admission.py` 可把同一口径推到全部 13 门语言。
2. **子集内行为通过率 `passed_cases / total_cases`**——准确度。现有 366/366，
   但必须**同时报样本规模与形态**，否则 100% 会被误读。
3. **规范表达覆盖率**——生成线用：可接受的 profile 组合 / 实体数 / 关系种类 /
   字段类型 相对目标场景所需的比例。今天已测出 24/48、6/8 单实体、1/4 关系、1/5 形态。

三个指标合起来才能说「达到多少」。只报第 2 个会得到「100%」这种真实但误导的数字。

---

## 5. 交付物与复现命令

### 云端已跑（本次产出）

```
.ai/measurement-2026-08-21/
  measure_python_admission.py            # 真实仓库准入率（Python 源）
  annotation_breakdown.py                # 类型闸门拆解
  measure_generation_surface.py          # 生成契约请求面扫描
  admission-python-20-projects.json      # 主结果（排除测试文件）
  admission-python-20-projects-with-tests.json
  generation-spec-surface.json
  corpus-manifest.txt                    # 20 个 sdist 的 SHA-256
```

复现（任意 Python 3.12 环境，无需钉死工具链）：

```bash
pip download --no-deps --no-binary :all: --dest dl <上面 20 个包名>
# 逐个解包到 corpus/<name>/
PYTHONPATH=engines/polyglot-route-engine/src python measure_python_admission.py \
    --corpus-root corpus --output admission.json
```

### 需要在 Mac 上跑（覆盖其余 12 门语言）

`engines/polyglot-route-engine/tools/measure_repository_admission.py`
走的是**生产入口** `discovery.discover_unit`，因此带钉死工具链背书。
云端跑它会全部返回 `NOT_RUN`（`EXACT_TOOLCHAIN_PLATFORM_MISMATCH:python:expected=Darwin/arm64`）
——这正是它该有的行为，不是故障。

```bash
uv --directory engines/polyglot-route-engine run --locked python \
  tools/measure_repository_admission.py \
  --repository ~/DevProjects/AIProjects/langgraph \
  --language python \
  --output .ai/admission-langgraph-python.json
```

换 `--language java|go|rust|csharp|cpp|objc|swift|kotlin|php|typescript|javascript|dart`
与 `--repository <真实仓库>` 即可铺满矩阵。**不要**在仓库根目录用
`uv run --locked python tools/...`（`--locked` 只在引擎自己的 project 内生效，
uv 会回落到 PATH 上的 python 并报 `No such file or directory`）。

---

## 6. 本次评估自身的边界（不许被读掉）

- 本次全部是**准入/契约层**测量：没有跑任何一次实际转换、目标构建或行为比对。
  `READY` 只表示「进得去」，不表示「转对了」。
- Python 那一半用的是 `discover_unit` 底下两层（`python_coverage_subjects` +
  `analyze_python`）直调，因为生产入口在非 macOS/arm64 上拒绝执行。
  **分析器逻辑相同，工具链背书为 `NOT_RUN`。**
- 生成线只跑到「生成」为止；构建/启动/CRUD/RLS 在本次为 `NOT_RUN`，
  这些格子引用的是仓库里 2026-07-28 的既有证据，不是本次结果。
- 20 个项目的语料是按声明规则选的，但不是随机抽样，也不是「中小型项目」的统计代表。
  **0 READY 不能证明不存在正例的语料**——它证明的是在这 20 个真实项目上没有。
- 其余 12 门语言的准入率本次为 `NOT_PROBED`（缺工具链），**不是** `REJECTED`。
  这条区分参见 [[capability-probe]]。

参见 [[backlog-premise-discipline]]、[[capability-probe]]、[[cloud-session-tooling-limits]]。
