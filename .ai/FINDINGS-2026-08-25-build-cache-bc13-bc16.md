# BC-13 / BC-14 / BC-15 / BC-16 —— 一轮闭合，外加一次对抗验证

> 2026-08-25 · cowork-claude-20260825 · 云端容器（CPython 3.11.15 / aarch64-linux）
> 认领记录见 `.ai/BUILD_CACHE_PROGRESS.md` 的 “Active claims (2026-08-25)”。
>
> **本文全部是云端工程证据。** 不是 Mac、不是 provider、不是生产、不是独立验证者、
> 不是认证证据。BC-18 仍 `NOT_RUN`，BC-19 仍 `NOT_CERTIFIED`。

## 一、口径与执行边界

| 项 | 值 |
|---|---|
| 环境 | 云端容器，CPython **3.11.15**，aarch64-linux，`pip install -e .` |
| 未装 | `psycopg`（dev group，容器内不可达）→ 全部 26 个 postgres 参数化 **skip** |
| 会话起始基线 | `pytest tests/` → **4 failed** |
| 本轮结束 | `pytest tests/` → **1600 passed, 52 skipped, 0 failed**（116.40s） |
| ruff | 仅 1 条既有错误 `tests/test_e2e.py` `I001`（不在本轮范围，未动） |
| mypy --strict | 仅 1 条既有错误 `db/store.py:1956` psycopg `import-not-found`（72 源文件） |

**`pytest -q` 在本仓会静默吞掉计数行**：`pyproject` 的 `addopts` 已含 `-q`，
再传一次就是双 quiet，摘要整行不打印。本轮所有计数都用
`-o addopts="--strict-markers"` 覆盖后取得。这条值得写进后续会话的默认姿势。

## 二、起始的 4 条失败：3 条是 BC-13 自己造的，1 条是测试写错了

BC-13 追加了 `migrations/sqlite/0007_slo_control.sql` 与
`migrations/postgres/0009_slo_control.sql`，但没同步迁移契约测试——那三条仍断言
最后一个迁移是 `0006` / `0008`。它们不是回归，是 BC-13 `IMPLEMENTED_NOT_VERIFIED`
状态的直接体现：代码进了仓库，没人跑过。

第 4 条 `test_sota_16_a_policy_cannot_make_an_invalid_entry_reusable` 是**测试错了**：
`0001_init.sql:12` 把 `projects.project_id` 声明为**全局 PRIMARY KEY**，`0006` 在其上
再建 `(tenant_id, project_id)` 复合唯一索引作为 FK 目标，**并没有撤掉全局 PK**。
所以两个租户共用同一个 `project_id` 在 schema 层就不成立，
`ensure_project` 抛 `ConflictError` 是对的，同一套件里的
`test_project_identity_cannot_be_claimed_by_another_tenant` 早就这么断言。
改测试不改 store，并**补强**了「跨租户认领被拒且归属不变」的断言。

## 三、三条 backlog 的落地

### BC-13 —— `slo_service.py` 有一个让整个状态机不可达的真 bug

新增 `tests/test_slo_service.py`（1924 行 / **52 条**），真 SQLite + 真 CAS + 真
Ed25519，全部走公开入口。

**真 bug**：`_persist_document` 把依赖引用边写在了与 proposal 语义身份**同一个 key** 下。
`MetadataStore.artifact_targets`（`db/store.py:651`）只按 `(tenant_id, source_kind, source_id)`
选择，**忽略 `ref_kind`**，于是身份 key 解析出 **3 个** digest，而
`_proposal()` 要求恰好 1 个，否则 `NotFound`。后果是
`install()` / `advance()` / 活跃候选的 `rollback()` **全部是死代码**，公开 API 走不到；
字节相同的重复 `propose()` 也会误报 `IdempotencyConflict`。
修法：依赖边改走派生命名空间 `f"{source_kind}-dependency"`。
`gc.py` 的 `reachable()` 走固定 kind 列表、从不含 SLO kind，GC 行为不受影响。
**回滚这一行修复，52 条新测试里有 29 条失败。**

迁移契约测试从 `[-1]` 索引改为**钉住完整有序元组**并逐个字节比对**每一个**打包镜像
（旧写法只比最后一个，一个旧文件的陈旧镜像会发出与仓库声明不同的 schema）。
另补 `test_postgres_slo_control_migration_carries_the_same_composite_scope_contract`：
新的 project-scoped 表必须自带 `(tenant_id, project_id)` FK 与 `RESTRICT/RESTRICT`，
之前没有任何东西在检查这件事。

### BC-14 —— 五层 composition 的测试与接线

`tests/test_parity_composition.py`（1967 行 / **230 条**）。核心不变式被穷举钉死：
**只有精确 Action 命中才能跳过执行**——四个非 Action 层的 15 个非空子集全部覆盖，
外加 14 种 Action 层缺陷（冷未命中、端口旁路、未验证材料、不兼容、外来 trust namespace、
restore 失败…）**在其余四层全热的情况下**逐一验证仍然执行。
在 1365 行里没找到真 bug——用行级 tracer 量过，未执行的只剩 Protocol 的 `...` 与
两处构造上不可达的防御分支。

接线新增 `src/elmos_build_cache/parity_composition_wiring.py`（578 行）与
`tests/test_api_composition_wiring.py`（1275 行 / **42 条**）。接线期抓到的真问题：
`ActionCacheLayerProbe` 会把 Action Cache 查两遍（composition 判一次、组装 404/200 正文再查一次），
已改为记忆化。

**交接说明里有 6 处与代码不符**，最重要的一处：`_serving_call` **不能**驱动会 restore 的端口。
`operation()` 本身就是该层的工作，若同层 restore 了，`FallbackExecutionResult`
必须声明 `set(LayerWork) - {restored}`，而 `operation()` 照样做了那份工作——
要么声明说谎，要么 composition 抛 `ContractViolation`，而这条路由今天是返回 200 的。
因此 serving 路由上五个端口全部 `BYPASS/LAYER_OUT_OF_REQUEST_SCOPE`。

### BC-15 —— provider 生产链

`PromptCacheController` 以 `serving_authorizer` 那一支的约定注入
（**缺失即缺失，绝不造默认值**）：没有 controller 的控制面在两条新路由上
以本包自己的 `RemoteUnavailable` fail closed，不会 `None` 解引用。

两个新 OpenAPI operation：`prepareProviderPrompt`（`POST /cache/provider-prompts/prepare`）、
`recordProviderCacheUsage`（`POST /cache/provider-prompts/usage`）。

**project ownership 前置于全局幂等**，并且是**实测**而非论证的：把 preflight 移到
幂等 claim 之后再跑，恰好两条测试失败——一条看「被拒请求必须零 `idempotency_records` 行」，
一条看「同一个不属于自己的 project，已用 key 与未用 key 的应答必须无法区分」
（顺序颠倒后分别是 `409 IDEMPOTENCY_CONFLICT` 与 `404 NOT_FOUND`，这个差值本身就能枚举 key）。

## 四、对抗验证：一次独立的证伪回合

三条 backlog 报完成后，跑了一轮**以证伪为目标**的独立验证（只读源码，需要变异就复制到 `/tmp`）。
它推翻了其中一条核心声明，并挖出四个此前无人提及的问题。这一步的产出比三条 backlog 本身更值。

### 4.1 被推翻：「接线不可能扩大跳过执行的集合」

**声明是错的，而且能构造出来。** `CompositionRunner.__init__` 里

```python
override = wiring.layer_ports.get(layer)
self._ports[layer] = override if override is not None else ScopedCacheLayerPort(...)
```

一个 `layer_ports[ACTION]` 条目会**整体替换端口**，把 `lookup_action` 传进来的
per-request `ActionCacheLayerProbe` 静默丢掉，于是 `exact_action_reused` 与真实
Action Cache 之间**再无因果联系**。实测：缓存全冷、从未 commit 过任何东西，
带 ACTION 端口覆盖的已接线控制面返回

```
200 {"hit": true, "result_manifest_digest": null, "result": null}
```

——一个「不要执行」的应答，却没有任何结果附在上面；未接线的同一请求返回
`404 {"hit": false, "miss_reasons": ["NO_ENTRY"]}`。

问题的根不在覆盖，在于子集性质是**被推断的**而不是**被强制的**：

```python
served = result.hit if reused is None else reused      # api.py:533，旧
```

已改为在缝上强制，并且额外在 wiring 构造期就拒绝 ACTION 端口覆盖：

```python
served = result.hit and (reused is None or reused)     # 新
```

`reused` 现在只能做减法，永远不能做加法。

**教训**：「A 是 B 的合取加强」这种子集论证，只要它依赖的那个合取项在别处可被绕开，
论证就不是结构性的而是偶然性的。子集性质必须写在决定点上，不能写在注释里。

### 4.2 4xx 会把调用者的原文持久化——BC-15 的 prompt-safety 声明有洞

`_enum` 回显 `value=value`，`_strict_object` 回显 `unknown=[...]`，两者都无界无脱敏；
而 `handle()` 会把**任何 < 500 的应答**原样写进 `idempotency_records.response`。于是：

```
POST /cache/provider-prompts/prepare  {"request_class": "<整段 prompt>"}
  → 422，details.value 就是那段 prompt → 逐字进入持久化幂等记录
```

`segments[0]` 里放一个意料之外的 key 名同理。**canary 测试从来没跑过 4xx**，
它只发一个 200 然后扫这一个 200 写出的行。

修法：两个校验器改为只报**形状**——`allowed` 是服务端自有的封闭 key 集，
`unknown_count` 是有界整数，`missing` 是服务端 `required` 的子集，`permitted` 是封闭词表。
三者都不是回显。诊断性没丢：调用者手里有自己的请求，用 `allowed` 一减就知道是哪个 key。
canary 测试已扩到覆盖 200 + 两条 422 写出的**全部**行。
**回滚脱敏，该测试立刻失败并打印出泄漏的原文。**

### 4.3 canary 扫描对 NFC 归一化是瞎的

`canonical_json_bytes` 在落盘前做 NFC 归一化（`canonical.py:75-85`），
而测试按写入时的字面量扫。以 NFD 写入的泄漏会以 NFC 落盘，直接漏过。
已对 haystack 与 needle 双向归一化，并补一条专门的 NFD 用例，
用**写入端自己的编码器**（`canonical_json_text`，`ensure_ascii=False`）做正控——
`json.dumps` 会把非 ASCII 转义成 `́`，拿它做正控会让检查变成空转。

### 4.4 两个安全护栏零覆盖：删掉整套测试照样绿

变异实测：

| 变异 | 修复前 | 修复后 |
|---|---|---|
| 删掉 `_composed_serving_call` 的 `exact_action_reused` 拒绝（api.py） | **93 passed**（无感） | 1 failed |
| 把 `ActionCacheLayerProbe.__call__` 的 `not result.hit` 放宽（wiring:304） | **293 passed**（无感） | 1 failed |

第二个正是 4.1 那条不变式所依赖的判断，而下游**没有任何东西再复查它**。
它今天不可证伪，只因为 `ActionCache.lookup` 恰好只在命中路径上设 `result_digest`
（`action_cache.py:341-347`）；将来任何一个「保留 digest 的未命中原因」
（比如 restore 成本超过重算）都会直接变成一次被服务的命中。
两条测试都已补上并用变异证明会咬。

### 4.5 `api.py` 里一段论证是假的

原注释称 serving 路由传 `probes={}`，所以 Action 层「不在请求作用域内」，
`exact_action_reused` 因而结构上不可达。**不对**：`CompositionRunner` 会把
`wiring.layer_probes` 合并在 per-call probes **下面**，部署级的 ACTION probe
在 serving 路由上照样在作用域内。行为仍然 fail closed，但**靠的是 4.4 里那个当时零覆盖的护栏**，
不是注释说的理由。注释已改为陈述真实机制，护栏已有测试。

**规律**：一段解释「为什么这里不可能出事」的注释，如果它给的理由是假的，
那它同时也解释了为什么没人给真正兜底的那个护栏写测试。假论证比没有论证更贵。

## 五、不在本轮范围、需要你拍板的三个既有缺陷

以下三条**已复现**，但都属于已关闭的 BC-10 行或 `parity_store` 的既有语义，
改动会牵动别处钉死的错误优先级。**本轮刻意没改**，请你定。

### 缺陷 1（最严重）：`compile_prompt_prefix` 是跨租户的 project 存在性预言机，并且能抢注全局命名空间

`POST /cache/prompt-prefixes/compile` 不在 `_authorize_resource_preflight`（api.py:425-476）里，
直达 `ParityMetadataRepository._ensure_scope`，后者**未命中即创建**（parity_store.py:729）、
外来则抛 `TenantMismatch`（parity_store.py:731-736）。实测：

```
foreign project : 404 TENANT_MISMATCH（并回显 tenant_id / project_id）
absent  project : 200 + projects 表新增一行，归属调用方
```

叠加 `projects.project_id` 的**全局 PRIMARY KEY**，攻击者可以按应答码枚举整个全局
project 命名空间，然后把所有空闲名字抢注掉——被抢的租户此后
`ensure_project` 永远 `ConflictError`。实测 `tenant-attacker` 成功占住 `acme-production`。

### 缺陷 2：BC-10 的四条变更路由都泄漏幂等 key 存在性，并为被拒请求写下持久状态

`compile_prompt_prefix` / `appendContextLedgerEvent` / `decideCacheAffinity` /
`startCacheParityRun` 都不在 preflight 名单里，`handle()` 先拿持久幂等 claim 再走租户检查：

| 路由 | 已用 key | 未用 key |
|---|---|---|
| `compile_prompt_prefix` | 409 `IDEMPOTENCY_CONFLICT` | 404 `TENANT_MISMATCH` |
| `appendContextLedgerEvent` | 409 | 422 `CONTRACT_VIOLATION` |
| `decideCacheAffinity` | 409 | 403 `PERMISSION_DENIED` |
| `startCacheParityRun` | 409 | 422 |

四条都会为一个从未被授权的请求写下 `idempotency_records` 行。
修法是在 `_authorize_resource_preflight` 里加一个子句，与本轮给 provider 路由加的完全同形；
但对 `decideCacheAffinity` 而言，把 ownership 提到 claim 之前会改变
`test_default_control_plane_denies_unwired_serving_routes` 钉住的错误优先级
（它对不存在的 project 期望 `403 NOT_WIRED`）。**这是 BC-10 owner 的决定。**

### 缺陷 3：composition 的 `request_id` 是客户端头，无 principal 绑定

`_composition_request_id` 直取 `X-Elmos-Request-Id` 或 `Idempotency-Key`（api.py:853-858），
只有 fallback digest 含 `principal_digest`；`explain_cache_outcome` 按
`(tenant, project, request_id)` 读，**不校验 principal**（parity_api.py:1699-1706）。
同租户内两个 principal 用同一个 request id，轨迹会落进同一个桶（实测 24 行），
其中一方可以通过 `GET /cache/explain/{requestId}` 读到另一方复用了哪个缓存结果，也能污染对方轨迹。

## 六、本轮改动清单（15 个文件，零附带改动）

**新增 4：**

- `src/elmos_build_cache/parity_composition_wiring.py`（578）
- `tests/test_slo_service.py`（1924 / 52 条）
- `tests/test_parity_composition.py`（1967 / 230 条）
- `tests/test_api_composition_wiring.py`（1275 / 42 条）

**修改 11：** `src/elmos_build_cache/api.py` · `parity_api.py` · `slo_service.py` ·
`openapi/cache-parity-control-plane.openapi.yaml` 与其打包镜像
`src/elmos_build_cache/_data/openapi/…`（保持逐字节一致）·
`tests/test_api.py` · `test_metadata_store_contract.py` · `test_parity_api.py` ·
`test_parity_contract_assets.py` · `test_provider_prompt_runtime.py` · `test_sota_acceptance.py`

**未动**：`migrations/**`（16 个文件与打包镜像本就逐字节一致，`cmp` 验过）、
`parity_composition.py`、`prompt_cache.py`、`cli.py`、`tests/test_e2e.py`。

对 pristine 基线做过 `diff -rq`，改动集恰好是上面 15 个，没有第 16 个。

**没有删除任何测试，没有放宽任何断言。** 逐条比对过六个被修改的测试文件：
唯一的删除是一次重命名，替换版本严格更强。一处覆盖退化已修复并拆成两条：
`test_postgres_project_scope_migration_failure_is_retryable_and_contiguous`
原本用 `POSTGRES_MIGRATIONS[-1]`，`0009` 落地后这个索引静默指向了 SLO 迁移，
它以为自己在测 project-scope 其实没有——现在按名字指定，并另开一条测 SLO 迁移。

## 七、仍然 `NOT_RUN`，不得上调

1. **真实 provider 执行**（OpenAI / Anthropic / 自托管）。容器无网，也没有造假 provider。
   两个新 operation 都返回 `provider_execution_performed: false`，
   `/status` 的 parity 块仍报 `external_provider_evidence: NOT_RUN`。
2. **live PostgreSQL**。`psycopg` 装不上，26 个 postgres 参数化全部 skip。
   `0009_slo_control.sql` 只验了**文本与字节一致性**——它的 `JSONB`/`TIMESTAMPTZ` 列类型、
   `guard_cache_slo_control_event_v12()` plpgsql 触发器、`NOT VALID` + `VALIDATE CONSTRAINT`
   的 FK 序列、部分唯一索引，**从未在真实服务端上执行过**。
   现有的 `_FakePostgresConnection` 不是数据库。
3. **Mac 精确工具链门禁**。本轮全部结果来自云端 CPython 3.11.15 / aarch64-linux。
4. **PROMPT / CONTEXT / ENVIRONMENT / AFFINITY 四层未接真实服务**。
   `ParityRepository` 只有 `get_prompt_manifest`（按 `manifest_id`）与
   `get_environment_snapshot`（按 `snapshot_key`）两个只读取数器，两个 key 都无法从
   `GET /cache/actions/{actionKey}` 或通用 `_serving_call` 推出；context ledger 与 affinity
   连「这一层对这个作用域是否热」的只读查询都没有。四层因此是注入缝、默认作用域外 `BYPASS`。
   它们的热行为**已经**通过真实路由注入 probe 端到端验过（6 个参数化用例），
   但接到真实 key 需要一条携带这些 key 的路由——那是另一行的事。
5. **没有任何层写入器（`layer_writers`）接线**，serving 路径不 populate 任何缓存。
6. **composition result 层级的签名/认证不存在**。模块不给 `CompositionResult` 签名，
   `to_dict()` 明写 `"certification": "NOT_CERTIFIED"`。已验的是 `SignedStatement` 对
   layer set / tenant / project / principal / 授权 / 兼容性 / 签发与过期的绑定与防重放。
7. **并发**。composition 不持跨调用状态（`_Recorder` 是 per-`execute` 的），但没跑并发测试。

## 八、你需要在 Mac 上做的

```bash
cd engines/build-cache-engine
uv sync --locked
# 注意：不要再传 -q，pyproject 的 addopts 已含 -q，再传一次摘要整行不打印
uv run --locked python -m pytest tests/ -o addopts="--strict-markers"
uv run --locked ruff check src tests      # 预期仅 tests/test_e2e.py I001（既有，未动）
uv run --locked mypy --strict             # 装上 psycopg 后应当零错误
```

装上 `psycopg` 后，26 个 postgres 参数化会从 skip 转为真跑——那一段正是本轮
最可能藏矛盾的地方（参照 #1 PHP 枚举的教训：云端只验了一层，Mac 上的完整管线
才暴露出上下游口径不一致）。
