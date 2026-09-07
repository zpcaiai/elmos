# elmos-repository-refactoring

`elmos-repository-refactoring-skills` v1.0.0 规范包的**生产实现**：23 个仓库级重构 Skill
的确定性运行时。零第三方依赖，Python ≥ 3.11，`ruff` + `mypy --strict` 全绿。

## 设计上的两层结构

```
                 ┌───────────────────────────────────────────────┐
   task payload  │  确定性纯核（本包）                            │
   ───────────►  │  解析 · 索引 · 计划 · 变换 · 裁决 · 证据        │
                 │  不碰 shell / 网络 / SCM / 时钟（业务判定）    │
                 └───────────────┬───────────────────────────────┘
                                 │ ExecutionRequest（带幂等键）
   trusted context ─────────────►│
   （policy / adapters /         ▼
     workspace root /   ┌──────────────────────┐
     executor）         │ SandboxExecutor 后端  │
                        │ Null / Recorded /    │
                        │ Subprocess           │
                        └──────────────────────┘
```

纯核永远可离线复现；真实编译、测试、扫描通过可插拔执行器完成。**没有执行器时，
门禁结果是 `not-run`（未决），绝不是 `pass`。**

## 三条贯穿全包的诚实性规则

1. **未读不等于空。** 无法解码的文件进入 `unscanned`，并拉低 coverage；它不会被
   当作「零符号、无风险」。
2. **未探测不等于不存在。** 适配器能力分 `declared` / `attested` / `proven` 三层，
   有效等级取 `min(proven, attested)`——签名不是实现，签名永远不能把一门语言抬到
   代码做不到的等级。
3. **未决不等于通过。** 表达式语言是三值的：缺失事实求值为 `UNKNOWN`，`UNKNOWN`
   的阻断门判为失败，未决的审批条件判为需要审批。

## 已落地

| Skill | 模块 | 实质能力 |
|---|---|---|
| `repository-refactor-orchestrator` | `orchestrator.py` | 事件溯源状态机、阶段 DAG 合成、审批门按策略推导、读写集冲突调度、p50/p80/p95 ETA、故障分类、可重放 |
| `repository-discovery` | `discovery.py` | 语言/构建/生成/vendor/测试/迁移清单、CODEOWNERS 真解析（last-match-wins）、9 类敏感区（路径+内容双证据）、覆盖率与未扫描区 |
| `build-graph-and-environment` | `buildgraph.py` | Maven/MSBuild(XML)、npm(JSON)、pyproject/Cargo(TOML)、go.mod 真解析；Gradle/CMake 显式标为启发式；工具链与 lockfile 固定；baseline 走执行器 |
| `semantic-index` | `index.py` + `extractors.py` | Python 走 `ast` 精确抽取（含动态引用按 `attribute`/`module` 分域标注）；13 门语言语法层抽取（注释/字符串剥离且保持行列几何）；OpenAPI/proto/GraphQL 契约实体；增量索引与全量一致 |
| `refactor-intent-compiler` | `intent.py` | 中英双语目标分类、目标 token 对索引求解、"不改变行为"拆成 source/binary/wire/data/behavior/operational 谓词、假设登记（低置信 + 不可逆 → 阻断）、**最小冲突集** |
| `change-impact-analysis` | `impact.py` | 沿 11 类边做闭包并保留 **原因链**、hub 符号、测试闭包与未覆盖路径、消费者矩阵（无可见消费者 = 风险更高）、波次/分片、未知惩罚**抬高**而非稀释风险 |
| `recipe-synthesis` | `synthesis.py` + `recipe.py` | 6 条内置 Recipe（真 schema 往返）、按语言与**实测适配器等级**筛选、参数绑定与类型/正则校验、组合冲突检测、dry-run 走与执行完全相同的代码路径、`recipes.lock` |
| `deterministic-transform-executor` | `executor.py` + `pyops.py` + `pyscope.py` + `patch.py` | Python 真作用域求解（LEGB + 类作用域不可见规则 + 推导式作用域 + global/nonlocal）；跨文件 rename 跟进 importer；签名变更保留未触参数原文；最小 unified diff + hunk→action→symbol 溯源；补丁可反演；分片仅允许不相交合并；**二次运行真跑一遍**证明幂等 |
| `api-compatibility` | `apicompat.py` | 语言面 + wire 面（proto 字段号/枚举序号按 message 分域）双抽取；差异按**最强被破坏的兼容性**分类；`strict` 连"新增"都拦；expand→annotate→observe→approve→contract 弃用生命周期；适配层提纲 |
| `test-and-verification` | `verification.py` + `anticheat.py` + `sarif.py` | 分层门禁 + **反作弊**（删测试/加 skip/加 noqa/降 severity/吞异常/扩 ignore 各有独立规则）；回滚证明是**反演补丁再应用后比对树 digest** 算出来的；flaky 隔离不计通过；baseline 不可信时所有失败都算新增；SARIF 2.1.0 + JUnit |
| `bounded-auto-repair` | `repair.py` | 失败签名归一化去重；**封闭候选词表**（加 import / 删无用 import），语法错与"新增必填参数"明确拒修；同签名复现即停；每个候选先过反作弊再决定是否采纳 |
| `human-approval-gate` | `approval.py` | 审批绑 request/plan/recipeLock/patch **四个 digest**，任一变化即失效；超时=拒绝；禁自批；四眼要两个不同 subject；`approve-with-conditions` 的条件是可求值谓词 |
| `canary-rollout` | `rollout.py` | 按构建目标与 owner 切 changeset；1→5→25→50→100 阶梯；**未验证回滚不开灰度**；R4 不许只凭技术指标全量；缺信号判 HOLD 不判通过 |
| `rollback-and-recovery` | `recovery.py` | 失败边界与**可复现**检查点定位；源码用反演补丁；外部副作用按逆序带幂等键补偿；数据可逆性未知时停写+切读**保留新增结构**而不是删列；恢复不删调查证据 |
| `evidence-and-audit` | `evidence.py` | 每个 artifact 带 digest、manifest digest 覆盖全集；hunk 溯源不全即判 `partial`；HMAC 签名可独立验证，无密钥时明说未签名；脱敏保留 digest 以维持不可抵赖 |
| `cross-language-contract-refactor` | `contractsmig.py` | 契约真源定位；波次顺序由**被破坏的是什么**推导（wire break → 消费者先行；source/binary break → 提供方先行；additive → 无约束）；无可见消费者 = 风险更高；生成客户端重新生成而非打补丁；清理波次门禁为 `old-path-usage-zero` |
| `data-schema-refactor` | `sqlops.py` | SQL 真词法（引号/注释/dollar-quoting）；expand→index→backfill→contract 四相；`NOT NULL` 不被类型正则吞掉；`require_sql_identifier` 拦截参数注入；可恢复+幂等回填带水位表；破坏性语句只允许出现在 contract 相 |
| `distributed-system-refactor` | `distributed.py` | 同步/异步/共享数据三类边；**共享表即耦合**（有无声明都算），未解决时禁止上分布式事务；调用策略审计窗口是**所在函数块**而不是固定行数；无 trace 时热点判定为 `UNKNOWN`；异步边强制 duplicate/reorder/replay 故障注入；branch-by-abstraction → strangler，清理步骤不可逆并单独门控 |
| `recipe-learning-registry` | `registry.py` | draft→quarantined→verified→certified 四级晋级规则（**跨仓次数/precision/recall/逃逸缺陷/幂等/对抗夹具/签名**逐条报全，不只报第一条）；digest 即身份，改内容=新版本；**一个逃逸缺陷否决一切成功率**；客户代码进共享语料需显式授权；撤销回溯到已执行的 run |
| `performance-preservation` | `performance.py` | 环境 digest 不同判 `not-comparable`；样本不足判 `undecided`（阻断）；**噪声带取自基线自身的四分位离散度**——同样 +12% 在安静指标上是回归、在噪声指标上不是；throughput 类指标方向自动反转；声明了却没测的 guardrail 判 `not-run` 并阻断；profile 差异区分「补丁改过」与「没改过」 |
| `security-preservation` | `security.py` | authn/authz/租户边界/校验/加密/日志/数据暴露七类控制的**消失**即发现；新增弱化模式（`verify=False`、`eval`、通配权限、吞异常、CORS `*`）只算**本次新增**的；密钥只报位置与 digest，**值不进证据**；suppression 无 owner 或无到期时间即阻断；依赖**降级**单独判定；无扫描器时 `not-run` 且不算通过；输出 SARIF 2.1.0 |
| `multi-repository-refactor-program` | `program.py` | 波次由计划生成后**再独立复核**依赖顺序并报出每一对违规；同一仓在多个波次里有**各自独立的状态**；暂停单仓不丢全局状态且可精确恢复；卡住的消费者（外部/超期/失败/暂停）单独列出并阻断清理波次；依赖成环时报出**具体环路** |
| `ui-and-client-refactor` | `client.py` | 组件/路由/状态/能力图；**平台能力矩阵**（小程序无 DOM、无 service worker、不能动态加载代码）逐项给出适配结论；埋点/实验/深链/权限/支付/原生桥被改动时单独列为必须验证项；无渲染器时视觉差异判 `not-run`（未决即阻断）；a11y 静态检查只报缺失的文本替代与标签，从不声称「页面无障碍」 |

**23 / 23 全部落地。** `dispatcher.PENDING_SKILLS` 现在是空集，
`test_runtime.test_every_catalog_skill_has_a_production_handler` 断言它保持为空——
任何新增的目录条目若没有生产 handler，构造 `RuntimeDispatcher` 时就会抛错，而不是
悄悄退化成一个返回成功的桩。

### 变换执行器拒绝做的事

- 无适用 Recipe 时产出空补丁并报"成功"——判为 `blocked`（"no recipe was applicable"）
- 只改定义不改 importer——`rename-imported-symbol` 是同一条 Recipe 的第二个 action，
  且 `dangling_references()` 能查出半成品重命名
- 用 `ast.unparse` 重排未触碰的参数（引号风格、空格）——改签名时按原文切片
- 选择器越出 Recipe 声明的文件集——报 scope expansion 并阻断，既不静默包含也不静默丢弃
- 名字捕获——重命名前先查冲突，冲突即拒绝而不是"带警告执行"

## TypeScript SDK 外壳

`packages/repository-refactoring-sdk` 是同一内核的类型化外壳：编译期 Skill 名、
门禁三态类型（`boolean | null`，`null` = 未判定）、退出码与信封状态互校、
子进程无 shell + 环境变量白名单。它**不做**重试、缓存或对结果的再解释。
`src/catalog.ts` 由 `config/skill-catalog.json` 生成，测试断言两侧不漂移。

## 用法

```bash
# 生成一个 workspace payload（离线、内联）
python -m elmos_repository_refactoring.cli snapshot ./repo \
    --revision 8a8f31c --repository-id billing > payload.json

# 运行一个 Skill
python -m elmos_repository_refactoring.cli run semantic-index --payload payload.json

# 运行时自述（哪些已实现、风险等级、依赖）
python -m elmos_repository_refactoring.cli describe
```

宿主集成：

```python
from elmos_repository_refactoring.runtime import dispatch

result = dispatch(
    "repository-discovery",
    {"workspace": {...}},
    trusted_context={
        "policy": {...},              # 缺省 = enterprise-default（拒网络、无自治）
        "adapter_capabilities": {...},
        "workspace_root": "/abs/approved/root",
        "recorded_executions": [...],  # 或由宿主直接注入 SubprocessExecutor
    },
)
```

CLI 退出码：`0` 成功 / `2` 拒绝 / `3` 阻塞 / `4` 失败 / `64` 命令行错误。

## 验证

```bash
make check      # lint + types + tests + certify，全部要绿
make certify    # 只跑生产认证套件
make golden     # 有意重录 Golden 基线（不要拿它把红的变绿）
```

### 生产认证套件

`tests/certification/` 分三层，各回答一个不同的问题：

| 层 | 问题 |
|---|---|
| 包不变量 | README 里的结构性声明，现在还对代码成立吗？ |
| Golden 语料 | 在固定仓库上，哪个 Skill 的行为变了？ |
| 变异测试 | 这套东西**真的**会在缺陷面前变红吗？ |

被强制的不变量（都是解析 AST 或真跑一遍验出来的，不是散文里的承诺）：

- **全包零第三方 import**——零依赖是安全属性（没有要 pin 的、没有要审的供应链），所以是**检查**出来的
- **只有 `sandbox.py` 能 import `subprocess`**，「没有执行器」才是内核能*如实报告*的状态，而不是可以绕过去的状态
- **任何地方都没有能联网的 import**
- **没有一个 handler 是桩**：按行数和是否走 pending 分支双重检查，23 个返回 `blocked` 的函数无法冒充目录覆盖
- **23 个 Skill 全部显式声明自己接受哪些字段**——结构性检查，因为「传个错 key 然后因为别的原因 blocked」正好能骗过纯行为探测
- **payload 无法给自己授予文件系统可达性**
- **handler 抛异常 → `failed` 信封**，不是 traceback，也不是半个成功
- **无执行器时阻断门未决且运行不通过**
- **无法解码的源文件拉低 coverage 并进 `unscanned`；声明为 binary 的资产两者都不**
- **声明的适配器等级永远不超过原生引擎等级**（Python 声明 L4 仍解析为 L2）

Golden 语料记录的是 **digest + 具名投影**，所以失败读起来是
`output.transformEvidence.changedPaths: was [4 files], now [1 file]`，
而不是两个不透明哈希。投影取不到值时记为字符串 `<missing>`，**绝不记 `null`**——
一个消失的字段不能冒充一个空字段。（这个哨兵在第一次运行时就抓出了本套件自己
投影路径写错的 bug。）

重录必须显式（`ELMOS_UPDATE_GOLDEN=1`）：一个见输出变了就自动重新定基线的语料，
只能**描述**回归，永远发现不了回归。

### 认证套件在被认证的包里找出的两个真缺陷

两个都是真的,而且 347 个功能测试**一个都没看见**。

**一个假的确定性声明。** `DispatchContext.now` 存在,但 `build_trusted_context`
根本不接受它,也没有任何 handler 把它往下传——于是 orchestrator / 审批门 / 回滚 /
证据四个 Skill 的时间戳直接来自墙上时钟。同样的输入,过一秒再跑,字节就不一样了。
进程内的确定性测试**一直是绿的**,因为两次 dispatch 读的是同一个时钟。是跨进程
测试把它暴露出来的。现在时钟从 trusted context 注入(不是 payload——能设定时间的
调用方可以把审批倒签),并且**双向断言**:同一时刻必须字节相同,不同时刻必须不同。
只断言前者的话,一个「解析了然后忽略」的 `now` 照样能过。

**反作弊在冤枉每一次诚实的重构。** 重命名改的是断言**内部**:旧行消失、同一个
hunk 里新行补上。原来的行级规则把这算作「删除断言」,于是那条样板证明——干净、
幂等、作用域正确的跨文件重命名——反作弊门是红的。同一个函数里的文件级计数器
同时报 `assertionsRemoved: 0`,正是这个自相矛盾坐实了 bug。一个在正常情况下就
乱叫的检查会被关掉,那比没有这个检查更糟。现在规则报**净损失**并精确定位,
文件级计数只作为整文件重写时的兜底。

### 真实工具链这一层

其余所有测试跑的都是确定性纯核——「没有执行器」在那里是诚实的缺省值,这恰恰把
**双层设计的另一半**留在了测试之外。`test_live_toolchain.py` 补上这一层:把快照
物化到临时目录,通过 `SubprocessExecutor` 跑**真的 pytest 和真的 ruff**,再看
实际发生了什么。

最吃重的一条是 `test_the_transform_output_survives_a_real_test_run`:纯核在不碰
shell、不碰文件系统的情况下算出一个跨文件重命名,结果写到磁盘,然后交给真的
pytest 判决。如果纯核的作用域分析错了——漏掉一个 importer、留下一个调用点——
它就在这里不再是理论。把跟进 importer 的那个 action 从 Recipe 里去掉,这条立刻变红。

它同时用真执行器核对沙箱声明的那些保证:非白名单二进制被拒、越界工作目录按名字
被拒(`path_escape` / `invalid_path` / `missing_working_directory`)、宿主环境变量
到不了子进程、超时**作为失败**是决定性的——但永远不是通过,因为 `succeeded` 要求
命令 COMPLETED 且退出码为 0。

工具链缺失时这些测试跳过,而 `test_the_live_suite_actually_ran_something` 会在
**全部**跳过时报错:否则从镜像里拿掉 pytest,这个文件就变成一排 skip,套件照样报绿。

物化本身也有诚实性规则:无法复现的文件(二进制资产、解码失败的源码)**被跳过并
报告,绝不写成空文件**——空占位会让编译器和测试运行器去评价一棵根本不存在的树。

### 这套套件被证明过会变红

`test_suite_detects_regressions.py` 把真实缺陷注入到包的**隔离副本**上再导入，
断言被守护的性质确实变了——而不是假设守护有效。已验证会被抓住的注入包括：
重命名不再跟进 importer、未决门禁读成通过、handler 不再拒绝未知字段、
无法解码的文件不再拉低 coverage、第三方 import 溜进来、固定时钟被解析后忽略、
反作弊退回去冤枉重命名。

Golden 语料覆盖**全部 23 个 Skill**(25 个 case),包含验证门的两条分支:
无执行器时(阻断门未决、运行不通过)和有真实录制证据时(机械门翻绿、无一未决)。

> 写这套件时它自己也出过两个同类 bug，都被记在代码注释里：一次是投影路径全部
> 写错（`<missing>` 哨兵抓到），一次是「声明必须有对应测试」的检查把**报告文件
> 自己**算进了搜索范围，于是每条声明都匹配到了写下它的那一行——一个自我满足的
> 断言，比没有断言更糟，因为它看起来像覆盖率。

## 与规范包的对应

`contracts/` 下的 9 份 JSON Schema 直接取自规范包；`request.py` / `plan.py` /
`policy.py` / `adapters.py` / `index.py` 的 `to_payload()` 均按对应 schema 输出。
`config/skill-catalog.json` 由 `runtime.skill_catalog_payload()` 生成，测试断言
文件与代码不漂移。
