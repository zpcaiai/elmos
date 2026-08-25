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

---

# 九、第二轮：Mac 暴露的 11 条 + 两条既有安全缺陷，全部处置完毕

> 2026-08-25 下午。第一轮（上面一到八节）之后，用户在 Mac 上跑了全量，
> 得到 **11 failed / 1626 passed / 26 skipped**（1663 collected，含 live PostgreSQL 17.5）。
> 这 11 条**没有一条属于本轮改动集**——6 个相关测试文件对本轮改过的模块 import 数全为 0，
> 且同样这 11 条在云端（带着改动）全绿。它们是 darwin-普通用户 与 linux-root 之间的差。
>
> 本节把这 11 条连同两条既有安全缺陷一并处置完。

## 9.1 云端基线的方法论漏洞：以 root 跑，权限断言全是空转

容器 `id -u` = **0**。root 绕过文件权限检查，所以**任何依赖「权限被真正强制」的断言在云端都没有效力**。
第一轮报的 1600 passed 在这一类上不构成证据。

这跟 `#1 PHP 枚举` 是同一个教训的**新形状**：不是「云端跑不了这一段」，是
**「云端跑了，但跑得没有意义」**。后者更危险，因为它以绿色的形式出现。

处置时用 `capsh --drop=cap_dac_override` 在容器内复现了 macOS 的权限语义
（仍是 uid 0，但内核按普通用户强制文件模式）：改动前四条失败**逐字复现**，改动后
五个文件 `118 passed, 2 skipped`。这个手法值得复用——它让「只有 Mac 能验」的一类问题
在云端可验。

## 9.2 十一条的归类与处置

| # | 测试 | 归类 | 处置 |
|---|---|---|---|
| 4 | `test_cas` ×3、`test_checkpoint` ×1 | root 绕过 `BLOB_MODE = 0o444` | 篡改前显式解锁再复原；**并补上真正测这条加固的测试** |
| 2 | `test_the_xcode_swift_adapter_holds_without_a_swift_toolchain`、`test_the_flutter_pub_adapter_holds_without_a_flutter_sdk` | **有意的绊线，正确触发** | 写了真认证替换 skip |
| 1 | `test_msbuild_incremental_build_through_the_sandboxed_nuget_cache` | **两个真缺陷** | 测试侧路径断言 + 产品侧解析器缺口 |
| 2 | `test_overlay` ×2 | Linux-only / 平台拼写 | 一条按平台 skip，一条**不 skip**并加了 macOS 拼写 |
| 2 | `test_coordinator`、`test_observability` | 测量的是宿主机不是产品 | 重写为测真正的语义 |

### 4 条权限：加固此前**没有有效测试**

`cas.py:45` 的 `BLOB_MODE = 0o444` 由 `_link_commit`（**不是** `put_bytes`，交接说明这里说错了）
在 `os.link`/`os.replace` 前 chmod 暂存文件——所以它是**所有入库路径的唯一咽喉**。
既有的 `test_blobs_are_stored_read_only` 只断言 `& 0o222 == 0`，
`0o400`、`0o000` 或**别的入库路径**回归都看不见。

已替换为 `test_every_store_path_leaves_the_blob_read_only`：对 `put_bytes` / `put_document` /
`put_stream`（压缩与非压缩两条分支，用 `info().compression` 钉住走的是哪条）/ `put_file` /
`repair_from` 全部断言 `stat().st_mode & 0o777 == BLOB_MODE == 0o444`，
并断言镜像不变式——`materialize` 默认给 `0o644`、按需 `0o755`，物化副本是调用者的，
**永远不继承规范模式**。

用 `stat` 而不是「尝试写入应当抛 PermissionError」是刻意的：后者在 uid 0 下永远不会触发，
又会变成一条空转的测试。

**变异证明**：`BLOB_MODE = 0o644` → 1 failed；`0o400`（仍只读但契约不同）→ 1 failed；
删掉 `_link_commit` 里的 chmod → 2 failed。

### 2 条绊线：这不是失败，是仓库在通知你可以关掉两个 NOT_RUN

`test_native_toolchains.py:478-480` 与 `:489-491` 的形状是
「工具缺席则 skip，**工具出现则 `pytest.fail`**」，fail 信息直说
`replace this skip with a real Xcode/SwiftPM certification`。
写测试的人知道 CI 装不上，于是留了绊线。用户 Mac 上 Swift 6.3.3 与 Flutter 3.44.1 都在，
绊线正确触发。

已写真认证（参照物是 `test_gradle_build_cache_is_redirected_and_actually_hits` 的
冷→毁→热三段，以及 `test_go_build_cache_...` 的「无事发生即命中信号」）：

- **Swift**：三个声明的缓存目录 empty→non-empty；`.build`、`~/Library/Caches/org.swift.swiftpm`、
  `~/.swiftpm/cache`、Xcode DerivedData **全部不被创建**；然后**删掉链接产物**再构建，
  `misses == 0` 把它放回来——产物只可能来自沙箱 DerivedData。这一步是承重的，
  「在没动过的目录里再构建一次」什么都证明不了。
- **Flutter**：`PUB_CACHE` 填充且 `~/.pub-cache` 不被创建；然后**销毁全部解析产物**
  （`.dart_tool/` 与 `pubspec.lock`）用 `--offline` 重解析——`--offline` 禁网，
  能重建 `package_config.json` 就只可能是沙箱缓存供的。
- 两者的无工具契约断言**一条不减**，而且从 skip 后面挪了出来，现在**每台机器都跑**。

### 1 条 msbuild：一个测试缺陷 + 一个产品缺陷

- 测试侧：`endswith` 拿整个 stdout+stderr 去后缀匹配路径。darwin 上 `tmp_path` 在
  `/var/folders`（`/private/var` 的符号链接），工具与我们可以用不同字符串指同一目录；
  且 SDK 往 stderr 写一个字节就破坏后缀。已改为 `Path(...).resolve()` 相等——**更强，不是更弱**。
- **产品侧**（`native_adapters.py:296`）：MSBuild 有**两种** skip 消息，解析器只认一种。
  `because all output files are up-to-date` 是增量复用；
  `because it has no inputs` 是这个目标本来就没事干——后者在无资源项目的 `CoreResGen`、
  无 copy-local 引用的 `_CopyFilesMarkedCopyLocal` 上必然出现，却被计成**热构建的 miss**。
  四个 header 里哪个走这条路由宿主 SDK 的目标集决定，所以 `misses == 0`
  在写它的那个 SDK 上可满足、换一个就不可满足——**一个没有产品成因的平台相关失败**。
  已把 `_SKIPPED` 扩到匹配两种消息（没干活不等于没命中缓存），`_HIT` 仍只数真正的增量复用。
  新增 `test_msbuild_counts_both_of_msbuilds_skip_messages_as_not_a_miss` 钉住，
  并反向断言「有 header 无 skip 行 = 执行了」，防止解析器被钝化成恒返回 0。
  **变异证明**：把 `_SKIPPED` 改回单消息 → 1 failed。

### 2 条 overlay：一条 skip，一条**拒绝** skip

- `test_the_workspace_works_on_top_of_a_kernel_overlayfs` → `skipif(sys.platform != "linux")`。
  不加的话 macOS 在 `ctypes.CDLL("libc.so.6")` 就死了，连体内既有的 skip 都到不了。
- `test_host_system_paths_cannot_be_mounted[/home/someone]` → **没有 skip**。
  `/home/someone` 在 darwin 上同样是「别人的家目录」，一样危险，skip 掉会藏起一个真实缺口。
  改为：把 macOS 的拼写 **`/Users/someone` 加进参数表**（`/Users` 本就在
  `DENIED_MOUNT_PREFIXES` 里却从没被测过——两个平台都是净增覆盖），并把 `pytest.raises`
  换成显式 `try/except → pytest.fail`，**失败时打印 `SandboxPolicy.check` 自己解析出的路径**
  与 `platform.system()`。
  **这一条是唯一没有在云端关闭的**：若 macOS 把 `/home/someone` 解析成自身（autofs 挂载点是目录
  不是符号链接，`realpath` 不动它），`/home` 前缀就命中、测试通过；若仍失败，失败信息会指名
  解析后的路径，那就是 `overlay.py` 的 `DENIED_MOUNT_PREFIXES` **产品缺口**，
  修法是补一条前缀，跟当初补 `/private/etc`、`/Users` 一样。没有瞎猜着加一条。

### 2 条时序：它们测的是宿主机，不是产品

- `test_coordinator`：睡 0.05s 却断言 `elapsed < 0.04`。而且
  `reason_code == "LOOKUP_TIMEOUT"` **根本没测到意图**——`_poll_probe_worker` 在「等到了迟到的探针」
  时报同一个码。已改为：探针睡 5s 且**只在跑完时**写标记文件，
  `assert not finished.exists()` 是无时钟的直接证据；同时注入 `monotonic` 钉住预算算术，
  让 20ms 决策截止不会在负载下过期改写原因码。
  **实测旧写法确实会飘**：2 核机器 4× 超订下测到 38.5ms / 39.5ms，紧贴 40ms 上限。
  新写法 11/11 通过，其中 5 次在同样负载下。
- `test_observability`：`Tracer.span` 用 `perf_counter` 计时（注入的 `ManualClock` 只盖
  `started_at`），`Histogram.summary` 把 p95 **四舍五入到微秒**。空 span 在快机器上是几百纳秒，
  舍入成 `0.0`，而 `0.0 <= 0.0` 正确地报告「没有超标」。**测的是宿主机速度。**
  `Slo.evaluate` 的 `observed <= budget_ms` 是**对的**——预算是「至多」，正好落在上面不算超标，
  改成 `<` 会让 `DEFAULT_SLOS` 每一条都拒绝自己声明的预算。所以**没动 `src/`**。
  已改为真超标（5ms span vs 1ms 预算，`sleep` 只会超不会欠），并补一条
  `test_a_measurement_exactly_at_budget_is_not_a_breach` 钉住 `50.0→pass / 50.001→fail /
  49.999→pass`，让「把 `<=` 改成 `<`」这个诱人的错误变成一次可见的、故意的改动。

## 9.3 两条既有安全缺陷：已修，且两个方向都用变异验过

### 缺陷 1：`compile_prompt_prefix` 的存在性预言机与全局名抢注

根因是 `_ensure_scope` **未命中即创建**。已改为：没有显式的
`project_scope_claim` 就**不创建**，且**absent 与 foreign 返回同一个拒绝**。
认领项目名是一个**刻意的动作**，归 `MetadataStore.ensure_project`（经 `POST /runs`），
它对自己无权的名字答 `CONFLICT`。

代码里留了理由（`parity_store.py:738-753`）：在这里创建会让**每一次 cache-parity 写入
都兼任一次对全局唯一名字的认领**，于是「编译一个 prompt prefix」就能把另一个租户
尚未创建的项目变出来，并因为 `ensure_project` 随后 fail closed 而**永久堵死它**。

**变异证明**：把创建行为改回去 → `test_the_control_planes_parity_repository_cannot_claim_a_project`
与 `test_a_request_serving_repository_answers_absent_and_foreign_alike` 双双失败。

### 缺陷 2：四条路由的幂等 key 预言机

六条路由现在都在 preflight 名单里：`append_context_ledger_event`、`compile_prompt_prefix`、
`decide_cache_affinity`、`prepare_provider_prompt`、`record_provider_usage`、
`start_cache_parity_run`。新增 `tests/test_route_project_authorization.py`（11 条）。

**变异证明**：把 preflight 移到幂等 claim 之后 → **25 条失败**，覆盖
「被拒请求必须零 `idempotency_records` 行」「已用 key 与未用 key 对未授权者不可区分」
「跨 principal」以及 BC-10 既有的三条 tenant-scope 断言。

### 仍然可利用的部分：`projects.project_id` 是**全局** PRIMARY KEY

`0001_init.sql:12` 声明它为全局主键，`0006` 在其上加复合唯一索引作 FK 目标却**没有撤掉它**。
API 层已经堵死「未授权即可抢注」，但**一个合法授权的租户仍然可以占掉另一个租户想要的名字**。

这是产品/schema 决定，不是缺陷判定：`project_id` 到底是不是全局命名空间？
**本轮刻意没改**——改主键会牵动九个迁移里的每一个 FK，且必须在 live PostgreSQL 上验证。
若判定它应当是租户内唯一，迁移大致要做：把 `projects` 主键改为 `(tenant_id, project_id)`；
把每个引用 `projects(project_id)` 的 FK 改为复合；对既有跨租户重名先 fail closed 再建约束
（照 `V70` 的做法）；并且这是**破坏性变更**，任何按裸 `project_id` 寻址的调用方都要同步改。

## 9.4 本轮之后的口径

云端（linux/aarch64，CPython 3.11.15，uid 0）：
**1652 passed, 52 skipped, 0 failed**；`ruff check src tests` **全绿**
（顺手修掉了 `test_e2e.py` 那条既有的 `I001` 导入排序，那是全仓最后一条 lint 失败）；
`mypy --strict` 仅剩 `psycopg` import-not-found，装上 dev group 即消失。

改动集 **27 个文件：5 新 22 改**，对 pristine 基线 `diff -rq` 核过，没有第 28 个。

**这些仍然只是本地工程证据。** 不是 provider、生产、多主机、独立验证者或认证证据。
BC-18 仍 `NOT_RUN`，BC-19 仍 `NOT_CERTIFIED`。

Mac 上仍需你跑一遍，重点看三处：
1. `test_host_system_paths_cannot_be_mounted[/home/someone]` —— 见 9.2，失败即为产品缺口，
   失败信息会指名解析后的路径。
2. 两条新的工具链认证（Swift / Flutter）—— 只有你的机器能执行。
3. `mypy --strict` 应当零错误。

---

# 十、第三轮：Mac 全量把四个真缺陷逼了出来

> 用户在 Mac 上跑了两次全量（shell 的续行被吞了，所以两条命令都变成了全量——反而更有用）：
> **4 failed / 1658 passed** 与 **3 failed / 1659 passed**，1663 collected，live PostgreSQL 17.5。
> 两次的差是并发那条在第二次通过了——那本身就是证据。

## 10.1 `DENIED_MOUNT_PREFIXES` 在 macOS 上有一个真实的挂载拒绝缺口（安全）

第二轮把这条**刻意留成失败**并让它打印解析后的路径，现在答案有了：

```
/home/someone resolved to /System/Volumes/Data/home/someone on Darwin
and SandboxPolicy accepted it
```

macOS 把根分成只读的系统卷和可写的数据卷，`realpath` 会把一部分路径解析到数据卷的真实挂载点。
`/home` 正是被咬的那个：它是 autofs 挂载，解析后变成 `/System/Volumes/Data/home/...`，
于是字面量 `/home` 前缀**永远匹配不上**——**在 darwin 上，别人的家目录可以被挂进构建阶段**。

注意 `/Users/someone` 那条是**通过**的：`/Users` 是 firmlink，`realpath` 不改写它。
所以两个"另一个用户的家目录"的拼写里，只有一个被挡住——这正是"逐个枚举拼写"这种做法的失败模式。

**修法不是再补一条前缀**，那正是当初 `/private/etc` 和 `/Users` 被一个一个手工补进去、
却仍然漏掉 `/home` 的原因。改为在匹配前**剥掉数据卷前缀**（`_denied_spellings`），
于是 `DENIED_MOUNT_PREFIXES` 里**现有的和以后新增的**每一条都自动覆盖它的数据卷拼写。

新测试直接驱动 `_denied_spellings`（不是 `check`）——重写是**宿主的 realpath** 做的，
linux 上不会发生，走 `check(Path("/home/someone"))` 在容器里什么都测不到。
并且断言了反向：`/System/Volumes/Data/opt/workspace` 与 `/System/Volumes/Data` 本身
**必须仍然放行**，防止剥前缀退化成"在 darwin 上拒绝一切"。
**变异证明**：撤销归一化 → 4 条失败。

## 10.2 `FlutterPubAdapter` 把自己的横幅当成了下载

`--offline` 的解析成功了、缓存被消费了（`entries=306, bytes_used=7216778`），
但 `parse_diagnostics` 报 `misses=1`。原因：

```python
build_log.count("Downloading")   # 旧
```

而 `pub get --offline` 的输出是：

```
Resolving dependencies...
Downloading packages...      ← 这是段落横幅，不是下载
+ characters 1.4.1
...
```

`Downloading packages...` 是 pub 在 `+ pkg` 之前**无条件打印的横幅**，
`--offline` 被禁止碰网络，所以它根本不可能下载。真正的取包会**点名**：`Downloading foo 1.2.3...`。

**这跟 `MsbuildNugetAdapter._SKIPPED` 是同一个缺陷形状**——解析器读横幅而不是读信号——
**也是同一个修法**：要求只有真实事件才会产生的那个 token。已改为
`^\s*Downloading (?!packages\b)\S+`，并断言反向（真取包仍然计数 2），防止解析器被钝化成恒返回 0。

**这一轮两个产品缺陷都是这个形状。** 值得作为一条规律记住：
**别用「工具打印了某个词」当证据，要用「只有那件事发生才会出现的形状」当证据。**

## 10.3 msbuild：测试把作者当时的 SDK 写死了

`TargetFramework` 硬编码 `net8.0`，而 `NuGet.config` 把包源 `<clear />` 清空了——
唯一剩下的 feed 是 SDK 自带的 `library-packs`，它只带**那个 SDK 自己那一代**的引用包。
在 Homebrew dotnet **10.0.301** 上就是三条 `NU1101: Unable to find package
Microsoft.NETCore.App.Ref`。

在测试里钉死一个框架名，等于把测试变成"作者当时装的是哪个 SDK"的陈述，而不是关于适配器的陈述。
已改为 `tool_version_major(dotnet)` 向工具本身要主版本，拼出 `net{major}.0`。

## 10.4 并发那条测的是调度器，不是不变式

`test_a_concurrency_loser_never_forks_the_event_chain` 断言
`len(winners) == 1 and len(losers) == 1`——Mac 上出现 **2 个 winner**，容器上一直是 1。

`threading.Barrier` 同步的是**起跑**，不是事务：在快机器上第一个写者可以在第二个读到 head 之前
就提交完，第二个于是**合法地**对新 head 再追加一次回滚。**那是两个写者串行化，不是分叉**——
而这条测试的名字说的是分叉。原来的断言在测调度器。

已改为断言每一轮**无论怎么落地都必须成立**的三件事：两个线程都跑完；至少有一个赢
（head 不能把两个都拒了）；**失败者必须是干净地失败**（`ConflictError`，
而不是撕裂的事务或半写链导致的契约违规）——最后这条才是真正的安全属性。
链的连续性与父指针断言**原样保留**，那才是"不分叉"的判据，一个赢还是两个赢都要过。

## 10.5 收口

云端（linux/aarch64，uid 0，CPython 3.11.15）：
**1659 passed / 52 skipped / 0 failed**；`ruff check src tests` **全绿**；
`mypy --strict` **零错误**（容器里装上 `psycopg[binary]` 3.3.4 后确认，
证实那条 import-not-found 是缺依赖不是类型问题）。

本轮改动 6 个文件：`overlay.py`、`native_adapters.py` 与四个测试文件。

仍是本地工程证据。BC-18 `NOT_RUN`，BC-19 `NOT_CERTIFIED`。
