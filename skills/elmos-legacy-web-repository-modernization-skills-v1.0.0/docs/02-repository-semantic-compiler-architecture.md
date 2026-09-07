# Repository Semantic Compiler 架构

## 一、分层

### 1. Source Frontends

输入适配器必须结构化解析：

- Git/ZIP/TAR、子模块、LFS；
- Maven、Gradle、Ant、Ivy、Shell/CI；
- Java AST、类型、字节码、反射字符串；
- XML、properties、YAML、容器 descriptor；
- JSP、JSTL、TLD、Tiles；
- Struts1/Struts2 配置；
- `web.xml`、`web-fragment.xml`、Servlet annotations；
- tests、logs、traces、traffic；
- DB schema、SQL、JPA/iBATIS/Hibernate mapping；
- deployment manifests、reverse proxy、JNDI。

Frontend 的输出不是 target code，而是 evidence。

### 2. Evidence Plane

```text
Evidence Store (immutable objects)
          +
Repository Evidence Graph (queryable)
```

证据对象保存原始片段、hash、locator、环境、提取器和时间；图只保存索引、关系和摘要。

禁止把大型源码、trace body、构建日志直接存入 PostgreSQL 行；数据库存 metadata/object URI/hash。

### 3. Semantic IR Plane

核心 IR：

- RepositoryTopologyIR
- EffectiveConfigurationIR
- EndpointContractIR
- RequestLifecycleIR
- BindingConversionIR
- NavigationDispatchIR
- StateScopeIR
- ViewSemanticsIR
- SecurityIR
- TransactionIR
- SideEffectIR
- DeploymentContainerIR
- ConcurrencyLifecycleIR
- UnknownSemanticsLedger

不同框架 adapter 只负责把 source-specific 事实投影到上述 IR。

### 4. Planning Plane

Planner 输出：

- target architecture；
- direct mappings；
- compatibility shims；
- dependency/Jakarta plan；
- packaging/view/container decision；
- transformation-unit DAG；
- allowed deltas；
- test/verification budget；
- Strangler/dual-run/cutover/rollback plan。

### 5. Transformation Plane

```text
Recipe Preconditions
  → AST / Symbol / Structured Config Rewrite
  → IR-driven Code Generation
  → Constrained Semantic Patch
  → Parse / Format / Compile
  → Change Set + Reverse Patch + Source Map
```

转换器不得绕过 IR 直接根据文件名批量生成。

### 6. Verification Plane

Legacy 和 target 同时置于隔离环境：

```text
Scenario Generator
       │
       ├──────────────┐
       ▼              ▼
  Legacy Runner   Target Runner
       │              │
       └──── Observation Bus ────┐
                                 ▼
                       Differential Oracles
```

Observation Bus 至少采集：

- request/response；
- dispatch/navigation；
- request/session/application state；
- DB transaction；
- messages/files/email/HTTP effects；
- logs/traces；
- resource/performance；
- security decisions。

### 7. Repair Plane

Repair Agent 的输入必须是：

```text
root-cause hypothesis
+ first divergence
+ evidence
+ IR
+ source map
+ affected tests
+ risk budget
```

输出是一个最小 change set 和可证伪测试，不能无目标地重写模块。

### 8. Certification Plane

认证器只聚合已经持久化的证据，不重新运行“看起来合理”的推理。认证结果包含：

- level；
- coverage numerator/denominator；
- allowed deltas；
- unknowns；
- risk exceptions；
- environment；
- artifact hashes；
- reproducibility commands；
- signer/policy。

## 二、控制面与数据面分离

### 控制面

- Job/Step 状态；
- DAG；
- lease/fencing；
- authority；
- retry/cancel/resume；
- cost/ETA；
- gate；
- artifact index。

### 数据面

- source snapshot；
- build cache；
- IR chunks；
- traces；
- test results；
- target repository；
- binaries/images；
- evidence bundle。

控制面记录 URI/hash，不复制数据面大对象。

## 三、执行单位

### Job

一个仓库到一个目标策略的完整迁移。

### Transformation Unit

可独立生成、构建、验证和回滚的最小仓库子图，通常由：

```text
module set + route cluster + shared state/effect boundary
```

定义。

### Step

一个 skill 在一个 transformation unit 上的幂等执行。

### Attempt

step 的一次 executor 尝试，携带 lease/fencing token。

## 四、关键 API 轮廓

```text
POST /modernization/jobs
GET  /modernization/jobs/{id}
POST /modernization/jobs/{id}:pause
POST /modernization/jobs/{id}:resume
POST /modernization/jobs/{id}:cancel
POST /modernization/jobs/{id}:approve-gate
GET  /modernization/jobs/{id}/artifacts
GET  /modernization/jobs/{id}/unknowns
GET  /modernization/jobs/{id}/certification
```

内部事件：

```text
job.created
step.scheduled
step.leased
artifact.produced
evidence.conflict
semantic.unknown
change_set.committed
verification.mismatch
repair.applied
gate.passed
certification.issued
cutover.rolled_back
```

## 五、缓存

缓存 key 必须包含：

```text
content hash
+ extractor/recipe/model version
+ target baseline
+ policy snapshot
+ relevant dependency subgraph hash
+ environment class
```

只对受影响子图失效。运行时 evidence 有 TTL；源码/构建 content-addressed artifact 可长期复用。

## 六、可扩展性

新增迁移路线时，优先新增：

```text
source adapter
target adapter
mapping policy
oracle plugins
fixtures/benchmarks
```

而不是复制 orchestration、evidence、IR、repair 和 certification。
