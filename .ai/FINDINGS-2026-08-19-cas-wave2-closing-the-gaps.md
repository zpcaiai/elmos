# FINDINGS 2026-08-19（第二轮）— 把 CAS 的 6 个缺口和「零调用者」逐条关掉

口径声明不变：「实现」= 真实业务逻辑 + 接进真实调用链 + 有测试覆盖行为 + **执行过并记录结果**。
本轮的目标就是把第一轮里明确写着「没做」的那几条做掉，**包括最后那条「零调用者」**。

## 一句话结果

`modules/cas` 现在 **35 个主文件 / 19 个测试文件 / 178 条测试**，云端全绿；
外加接线模块 16 条测试、V65 迁移在**真 PostgreSQL 16.2** 上 45 项约束校验全过、
CAS-041 基准**实际跑出数字**。合计 **194 条测试 + 45 项数据库约束检查**，全部执行过。

## 逐条交代

### CAS-011 批量 API —— 已做

`CasStore.putAll/getAll` + `CasBatch`。两个性质是重点，都写了测试：
整批只做**一次**存在性探测（4000 个依赖 blob 不再 4000 次往返）；
**单项失败不中止整批**——第 300 个对象损坏时其余 499 个照样落盘，调用方拿到精确到 digest 的失败原因。
`TieredCasStore.putAllDurable` 是批量版的「返回即持久」。

### CAS-018 区域放置 —— 已做

`RegionalPlacement`：residency → 主区/副本区映射、写入前放置裁决、复制积压队列。
两个设计决定：**未映射的 residency 直接拒绝，绝不回落默认区**（回落正是这个类要防的事故）；
`requiresReplication` 的 residency 在写入时同步复制，其余进积压队列由调用方决定何时排空。
读路径也过同一套裁决——bytes 够得着不等于这个区的读者能读。

### CAS-026 mTLS 身份 —— 已做（本模块该做的部分）

`WorkloadIdentity`：对钉死的 trust bundle 做 **PKIX 链校验**（不是 JVM 默认信任库——
公共 CA 签出来的 runner 身份不是 runner 身份）、验证时刻由参数传入（过期用例才可确定性复现）、
**恰好一个 SPIFFE URI SAN**（两个身份就是歧义，歧义总是往攻击者那边解）、trust domain 相等、
clientAuth EKU、序列号吊销名单、可选的最大叶证书寿命。
`ActionCache` 消费的 `attested` **只能**由 `attestedWriter()` 产出。
测试用 keytool 预生成并内嵌 7 份 PEM（同 SPIFFE ID 的冒充证书、过期证书、serverAuth 证书、
外域证书各一），纯 JDK、无外部依赖。

**边界**：签发与轮换是 SPIRE 的事，本模块只验。

### CAS-027 验签 —— 已做（本模块该做的部分）

`ResultSignature`：Ed25519 分离签名。**信封比算法重要**——只签 output manifest 的签名近乎无用，
攻击者把低权限动作的真签名重放到高权限 key 上照样通过。信封绑定了
action key digest、输出与 provenance、生产方租户/权限域/驻留地/密级、状态与退出码、密钥 id 与签名时刻。
测试逐条证明：换 action key 不通过、扩大权限域不通过、把签过名的失败重放成成功不通过、
未知密钥/轮换过期/过期签名/未来签名/算法不在白名单全部拒绝。
选 Ed25519 是因为它**确定性**——同一信封两次签名字节相同，缓存条目本身才还是内容可寻址的。

**边界**：私钥不进本模块，生产签名在 KMS。

### CAS-014 S3/MinIO L2 —— 已做

`S3CasStore`，**零第三方依赖**：JDK HttpClient + 复用 `modules/object-storage` 的 `SigV4Presigner`
（第三轮改的，见下方「我造了第二套 SigV4」）。
HEAD/GET(Range)/PUT/DELETE/ListObjectsV2 分页/CreateMultipartUpload+UploadPart+Complete/Abort。

测试用**进程内 mock S3**（`com.sun.net.httpserver`），它**用同一个 signer 重算签名**并对不上就回 403 ——
所以规范化写错会在这里红，而不是变成对着真 bucket 的 403。15 条测试覆盖：
签名往返、错密钥被拒、假 digest 根本不上网络、对象被存储端改坏能在下载时抓到、
长度不对的 key 不算命中、Range、分片上传逐片摘要、失败时 abort 掉悬空 upload、5xx 重试、
分页列举跳过非 digest 的野 key、与 `TieredCasStore` 组合的读穿透。

**顺带一条**：`URLEncoder` 不能用于 SigV4——它把空格编成 `+`、放过 `*`，两者都会签名不匹配。
`AwsV4Signer.uriEncode` 按 RFC 3986 未保留集自己编，有专门测试锁住。

### CAS-041 基准 —— 已跑出数字

`ActionCacheBenchmark`（可执行 `main`）。**故意测四件事而不是一个命中率**——
只看「不变输入命中率」的基准会奖励一个忽略工具链摘要的缓存（它能拿满分并发出陈旧产物）：

| 场景 | 命中率 | 期望 |
|---|---:|---|
| `unchanged-rerun` | **1.0000** | ≥ 0.95 |
| `one-file-changed` | 0.9950 | 恰好一个模块失效（无过度失效） |
| `toolchain-changed` | 0.0000 | 全部失效 |
| `permission-downgraded` | 0.0000 | 全部拒绝 |

200 模块 × 25 文件，节省 1.995 GB / 16758 秒 CPU / 24339 秒墙钟；基准自身 615 ms。
报告在 `.ai/CAS-041-benchmark.md`。**仍然是合成负载 + 模拟执行**，这一点写在报告正文里，
生产数字要拿真仓库跑，别拿这个替代。

### 数据库迁移 —— 已做，且在**真 Postgres 上执行过**

`V65__content_addressed_store_and_action_cache.sql`：7 张表（对象目录 / 区域放置 / 动作缓存条目 /
引用根 / 上传会话 / 删除清单 / 隔离事件），全部 RLS + **FORCE** + `cas_b65_tenant_isolation` 策略，
删除清单与隔离事件挂既有的 `elmos_forbid_append_only_mutation` 触发器。

Schema 层把服务层的不变量钉死了，绕过服务层也建不出这种行：
`cas_action_cache_high_risk_signed`（HIGH 档必须带签名）、
`cas_action_cache_failure_ttl`（只有 CODE/POLICY/SECURITY 能缓存且必须有 TTL）、
`toolchain_image ~ '@sha256:...$'`（可变 tag 直接拒）、
`cas_object_placement_single_primary_uq`（只能有一个主区）、
`cas_object_catalog_shared_needs_provenance`（可跨租户的内容必须可归因）。

**云端用 pypi 的 `pgserver` 起了真 PostgreSQL 16.2**（无 Docker、无网络），
`scripts/cas/verify_v65_migration.py` 跑了 **45 项检查**：每条 CHECK、唯一索引、外键、
append-only 触发器、RLS 策略都用一条**必须被拒绝**的语句实测过，并断言了拒绝原因。全过。

JDBC 侧 `JdbcCasCatalog` 用**纯 `java.sql`**（不引 spring-jdbc），每次取连接先
`set_config('app.organization_id', ...)`——V65 的策略读的就是它，忘了设的连接看不见也写不进。
`modules/persistence` 放两个测试：`CasMigrationContractTest`（文本契约，无 Docker 任何机器可跑）
与 `JdbcCasCatalogLiveTest`（Testcontainers，需 Docker，只有 Mac 能跑）。

### OpenTelemetry —— 已做

`CasTelemetry` 端口 + `Recording` 实现 + `OtlpExporter`。不引 OTel SDK（本模块零依赖硬约束），
但**数据模型不自创**：span/metric 形状、属性命名、OTLP/HTTP JSON payload 都按规范，
现有 collector 直接收。`ActionCache` 加了带 telemetry 的构造器（旧构造器委托 noop，不破坏既有调用），
`TieredCasStore.withTelemetry()` 可选接入。
埋点：`cas.action_cache.lookup`（带 outcome/reason/tenant，DENIED 记为 ERROR span）、
`cas.action_cache.store`、`cas.store.get`（带 L1/L2 tier）、`cas.transfer.bytes` 直方图。
导出器：批量切分、5xx 重试、**失败绝不往调用方抛**（遥测挂了不能挂构建）、
**全部成功才清空缓冲**（静默丢弃就是永久错误的仪表盘）。

### 告警 —— 已做

`CasAlerting` 六条规则，按**不可恢复性**而不是吵闹程度定级：
投毒 → PAGE（可能已经进了客户构建）；持久化积压**陈旧** → PAGE（唯一副本在一块随时会被回收的盘上），
仅仅**量大** → WARNING；节点隔离 → CRITICAL；引用对象缺失 → CRITICAL；
命中率塌陷 → WARNING（贵，但没丢东西）；孤儿字节 → INFO。
节流是**按规则 + 按 key**：一个坏节点不能刷 4000 条页，但两个坏节点必须出两条——
合并掉第二条正是漏掉第二起事故的方式。被抑制的次数在下次触发时一并报出。
`HealthSnapshot.from(...)` 直接从活组件装配，调用方不用手搓。

### Runbook —— 已写

`docs/runbooks/cas.md`：投毒、节点隔离、持久化积压、S3 不可用、命中率下降、对账漂移、
「GC 误删了东西」、冷启动恢复，八个场景 + 升级矩阵。
其中两条值得单独记：403 的排查顺序是**先查时钟偏移**（SigV4 签 `x-amz-date`，>15 分钟直接拒），
再查凭据轮换，最后查 path-style；以及**永远不要靠从 action key 里删输入来提升命中率**——
每删一项都是正确性风险，且失败模式是静默的错误产物而不是变慢。

### 「零调用者」—— 已接线

这是第一轮里最重要的那条未闭合项，现在关掉了：

1. **`io.elmos.integrations.CasBackedArtifactStore`** 实现 `SnapshotPorts.ArtifactStore` 与
   `ArtifactReader`。原来的 `LocalContentAddressedArtifactStore` 也按 digest 存，但**只存字节**：
   没有租户、没有密级、没有驻留地、没有保留级别，因此 GC 和读路径都无从判断。
   现在每个 snapshot 产物落库时都带齐这些事实。引用格式 `cas://sha256/<hex>/<size>`——
   拿到引用的人不用问任何人就能自证内容。读路径校验：产物是要被解包进工作区编译的，
   这是最后一道能抓住静默损坏的关卡。
2. **`TenantContentAddressedCache` 改为委托 `modules/cas`**，公开 API 不变（既有
   `PortfolioScaleTest` 照样过）。改掉了三件事：cache key 变成**长度前缀**编码
   （原来 `String.join("\\0", …)` 拼 7 个摘要，任何一个字段拼出 `\\0` 就能让两组不同输入塌成一个 key，
   有专门测试锁住）；读路径由 store 校验并隔离，而不是只重算一遍还留着毒字节；
   构造器换成 `TieredCasStore` 就直接变成跨机共享缓存。

三个 pom 加了 `elmos-cas` 依赖：integrations、portfolio-scale、persistence。

## 本轮抓到的真 bug / 真坑

1. **`TieredCasStore.put` 登记持久化债务的时机**（第一轮修的那条）在本轮批量路径上复现风险仍在——
   `putAllDurable` 复用 `putAll` 后立刻 `flushWriteBack`，顺序不能反。
2. **JUnit 桩的重载歧义**：`assertEquals(2L, map.get(k))` 在只有 `(Object,Object)` 和 `(long,long)`
   两个重载的桩下会歧义，测试里改用 `Long.valueOf(2)`。
3. **keytool 生成的证书 notBefore 是「现在」**，测试里把验证时刻钉在一个固定的未来时间戳
   （`1_800_000_000_000L`）才不会 NOT_YET_VALID；这也顺带证明了验证时刻是参数而非系统时钟。
4. **`URLEncoder` 不能用于 SigV4**（见上）。
5. **`HttpServer` 对带 Content-Length 的 HEAD 响应会刷 WARNING**，但 S3 的 HEAD 必须带——
   在 mock 里静态关掉那个 logger，否则通过的测试输出没法读。
6. **psycopg 的多语句 `execute` 只能 fetch 第一个结果集**，RLS 测试要拆成多次 execute。

## 现在还剩什么（这一节请当真）

- **生产命中率数字**：没有。基准是合成负载 + 模拟执行。
- **证书签发/轮换、私钥托管、在线吊销（OCSP/CRL）**：不在本模块，也没实现。
- **`JdbcCasCatalog` 的执行证据**：云端没有 PostgreSQL JDBC 驱动（Maven Central 403），
  所以它**编译过但没执行过**。V65 本身在真 Postgres 上执行过 45 项检查，
  `InMemoryCasCatalog` 按同一份契约测过 11 条——两者一致是刻意的，
  但 `JdbcCasCatalogLiveTest` 必须在你的 Mac 上（有 Docker）跑一次才算数。
- **端到端**：`CasBackedArtifactStore` 满足 `SnapshotPorts`，但**还没有人在生产路径上构造它**——
  `SnapshotMaterializationService` 的装配点仍然接的是 `LocalContentAddressedArtifactStore`。
  下一步是改装配，那属于 wiring 而不是本模块。

## 第三轮修正（Mac 首跑之后）

你在 Mac 上跑完前两条 `mvn` 之后暴露了三件事，都已修掉。

### 1. 我造了第二套 SigV4 —— 已删，改为复用既有的

`mvn -pl modules/persistence -am test` 的输出里有
`SIGV4 PRESIGNER TEST PASSED (16 checks)` 和 `S3 OBJECT STORE TEST PASSED (27 checks)`。
一查：`modules/object-storage` 早就有 `SigV4Presigner`（211 行）和 `S3ObjectStore`（298 行）。

**这是我的漏检。** 第一轮我确实看到过 `object-storage files=4 lines=959` 这一行，
但没打开看就去写了 `AwsV4Signer`。结果仓库里一度有两份 RFC 3986 编码器——
两份最后必然会漂移，其中一份拿到 bug 修复另一份拿不到，而失败模式是
「本地验得过、生产 403」。

更难堪的是：既有那份**比我的证据更强**。它的测试用的是 **AWS 官方发布的测试向量**
（`presigned signature matches the published AWS vector`），我的只是拿自己的 mock 对跑。

修法不是二选一，因为两者**确实是不同算法**：
`presign` 是查询串签名（`X-Amz-Signature` 在 URL 里，`SignedHeaders=host`），
CAS 需要的是**头部签名**（`Authorization` 头、多个签名头、显式 payload 哈希），
presigned URL 表达不了 range 读和分片上传。既有类的 javadoc 原话是
「header-based signing is not needed and is deliberately absent rather than half-built」——
现在需要了。

所以：**把头部签名加进 `SigV4Presigner`，删掉 `AwsV4Signer`。**
新增 `authorizationHeader` / `canonicalUri` / `canonicalQuery` / `sha256Hex` / `amzDateTime` /
`EMPTY_PAYLOAD_SHA256`，全部复用它原有的 `signingKey`/`hmac`/`sha256`/`hex`/`encode`。
`modules/cas` 加 `elmos-object-storage` 依赖——那个模块**自己零第三方依赖**，
所以本模块的传递闭包仍然是纯 JDK。

顺带在移植时发现一个真 bug 并写了测试锁住：`encodePath` 会**吞掉前导斜杠**
（`"/a/b".split("/",-1)` 的第一段是空串，拼接时 `out.length()==0` 于是分隔符没加上）。
它原来只喂 bare object key 所以没暴露；头部签名要签的是 `/bucket/key` 这种整路径，
少一个斜杠就是签了另一个请求。新增的 `canonicalUri` 显式处理前导斜杠。

**需要你手工删一个文件**：`modules/cas/src/main/java/io/elmos/cas/AwsV4Signer.java`
已被移到 `_to_delete/`（挂载盘上我没有 unlink 权限），确认后删掉那个目录。

### 2. HEAD 响应的 WARNING 刷屏 —— 已修（GC 的锅）

我原来在 `MockS3Server` 的静态块里 `Logger.getLogger(...).setLevel(OFF)`，云端有效、你机器上无效。
原因是 **`java.util.logging` 只弱引用它的 logger**：没人强引用的 logger 会被回收，
级别随之丢失、回退到父级。云端和你机器的 GC 时机不同，所以一边看得见一边看不见。
已改成静态数组持有强引用，并加 `setUseParentHandlers(false)`。
云端复跑 194 条测试输出里 `sendResponseHeaders` 出现 **0 次**。
这条要你在 Mac 上确认——它本来就是只在你那儿复现的。

### 3. `verify_v65_migration.py` 找不到迁移文件 —— 已修

脚本原来用 `Path(__file__).with_name(...)` 找 SQL，也就是**要求 SQL 和脚本同目录**。
但 SQL 正确的位置是 `modules/persistence/.../db/migration/`（跟其他迁移在一起，
放一份副本到 `scripts/cas/` 只会造出第二份会漂移的拷贝）。所以你就算装了 `pgserver`
也会接着报 FileNotFoundError。

已改成从脚本位置逐级向上找仓库根下的 `modules/persistence/src/main/resources/db/migration/`，
找不到时给出**列了所有查找位置**的可执行报错。缺依赖时也改成直接告诉你要跑哪条 pip。
两条路径都在云端验证过（真跑 45 项检查通过 / 报错信息正确）。

### 关于 `[Fatal Error] pom.xml:1:10: DOCTYPE is disallowed`

**不是我的改动。** 仓库里没有任何 `pom.xml` 含 DOCTYPE（全仓 grep 过，0 命中），
而且它在 `-pl modules/cas -am` 那一轮里**没有出现**，只在拉进 integrations / persistence
的两轮出现——那两轮才会解析 jgit / spring 这些第三方构件的 pom。
它是 Maven 解析**本地仓库里某个依赖的 .pom** 时打的日志，构建没有因此中断。

十秒定位：

```bash
grep -rl DOCTYPE ~/.m2/repository --include=*.pom | head
```

## 你需要在 Mac 上做的

```bash
cd /Users/stephen/DevProjects/AIProjects/elmos
mvn -q -pl modules/cas -am test
mvn -q -pl modules/integrations,modules/portfolio-scale -am test
# 先跑不需要 Docker 的那半边，立刻有结果：
mvn -q -pl modules/persistence -am test -Dtest=CasMigrationContractTest -Dsurefire.failIfNoSpecifiedTests=false
# 再跑需要 Docker 的那半边（第一次会拉 postgres:17.5-alpine，别 Ctrl-C）：
docker pull postgres:17.5-alpine && mvn -pl modules/persistence -am test

# 不要写成 `pip install ... && python3 ...`：Homebrew Mac 上 `pip` 与 `python3`
# 经常不是同一个解释器，装完依然 ModuleNotFoundError，重装也没用。
bash scripts/cas/finish-mac-verification.sh
java -cp modules/cas/target/classes io.elmos.cas.ActionCacheBenchmark 200 25 /tmp/bench.md
```

`FlywayMigrationTest` 会把 V65 一起跑掉，它断言的是「磁盘上发现的迁移数 == 实际执行数」，
新增一条迁移不需要改那个数字。
