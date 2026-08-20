# FINDINGS 2026-08-19 — CAS 与 Action Cache 的代码级实现

口径声明（沿用 `.ai/CODE_LEVEL_BACKLOG.md` 的判据）：本文所称「实现」= 真实业务逻辑 +
有测试覆盖行为 + **在本会话中执行过并记录结果**。目录存在、Skill 存在、schema 存在都不算。
本次**没有**接进真实调用链——`modules/cas` 目前没有任何调用者，这一条明确未闭合。

## 输入

`elmos-infrastructure-foundation-skills-v1.0.0.zip`（22 Skill / 719 任务 / 14 schema）。
和上一个 polyglot 包一样，**这个包本身是 0 行业务代码**：136 个文件里只有 install/verify/
package/validate 五个脚本和 8 个包自检的 Python 文件。它的价值是把 `ELMOS-CAS-001..042`
这样的带稳定 ID 的验收点写清楚了，可以逐条对照。

包已按 `--profile all` 安装：`.agents/skills`、`.claude/skills`、`.codex/skills` 各 22 个，
附带 `docs/` `schemas/` `templates/` `scripts/` `plans/` 五个 `elmos-infrastructure-foundation/`
子目录。解压副本在 `.ai-tmp/infra-skills-pkg/`，可删。

## 仓库现状核对（动手前）

- `modules/portfolio-scale/…/TenantContentAddressedCache.java` —— **66 行**，`HashMap<String,byte[]>`，
  cache key 只拼 7 个摘要字符串（`String.join("\0", …)`），无分层、无落盘、无 GC、无权限校验。
- `modules/integrations/…/LocalContentAddressedArtifactStore.java` —— 58 行。
- `modules/snapshot` 1036 行、`object-storage` 959 行已有真实内容，但都不提供 action cache。
- 全仓没有 action key / ActionResult / 可达性 GC / 分块续传的实现。

结论：CAS 这一块不是「补齐」，是**从零写**。

## 产出

新模块 `modules/cas`（artifactId `elmos-cas`），Java 21，**零 JDK 外依赖**，已注册进根 `pom.xml`
（插在 `modules/snapshot` 之后）。

- 主代码 **3500 行 / 16 个文件**
- 测试 **1444 行 / 10 个文件 / 90 条**
- `modules/cas/README.md` 写了设计取舍与**未实现清单**

## 执行证据（云端容器，2026-08-19）

Maven Central 在云端被墙（`repo.maven.apache.org` 返回 403），所以**跑不了 `mvn test`**。
用 `javac` + 一份 `org.junit.jupiter.api` 的桩（`@Test` / `Assertions` / `Executable`）+ 反射 runner
执行了**同一份测试源码**：

```
passed=90 failed=0
```

完整输出见随附的 `cas-cloud-test-run.log`。桩只提供断言语义，不改测试源码；Mac 上用真 JUnit 跑的
是同样的文件。

包自检也在云端跑过（这两条 device 上跑不了，缺 jsonschema）：

```
PASS: 14 JSON Schemas are valid Draft 2020-12 schemas
PASS: 14 mapped fixtures validate
Ran 11 tests ... OK
```

## 实现期抓到的两个真 bug

**1. 淘汰会丢掉唯一副本。** `TieredCasStore.put()` 原本先 `admitLocally()` 再登记 write-back 债务。
于是新对象在 `reclaim()` 眼里是「已持久化、可淘汰」的，容量一紧张就被删掉——而它此时**只有 L1 一份**。
`objectsStillOwedToSharedStorageAreNeverEvicted` 抓到了。修法是把登记挪到 admit **之前**。
这个顺序在代码里写了注释，改这段务必保住。

**2. 空 signature 之外的第二个「形状陷阱」：UTF-16 排序。** 目录项若用 `String.compareTo` 排序，
补充平面字符（如 U+10000）会排在部分 BMP 字符（如 U+FF21）**之前**，而 UTF-8 字节序相反。
两台 runner 对同一份内容会算出两个不同的 root digest。`MerkleTree.compareUtf8` 按字节比，
`namesAreOrderedByUtf8BytesNotUtf16CodeUnits` 锁住这条。

## 逐条对照 `ELMOS-CAS-001..042`

**已实现且有执行过的测试（36 条）**：001–010、012、013、015–017、019–025、028–040、042。

**部分实现（4 条）**：

| 条目 | 做到的 | 没做到的 |
|---|---|---|
| 011 批量读写 | `missing()` 批量存在性查询；重复写幂等跳过 | 没有批量 put/get API |
| 018 租户密钥与区域策略 | AES-GCM 租户信封加密；读路径强制 residency 相等 | 没有区域放置/多区域复制 |
| 026 写入方身份 | 要求 `attested` 且节点未被隔离 | mTLS/SPIFFE 认证本身在本模块之外 |
| 027 高风险结果签名 | HIGH 档必须带 `verified` 的 attestation | 验签本身在签名平面 |

**完全未实现（2 条）**：

- **014 共享 S3/MinIO L2**。端口 `CasStore` 定义了，分层逻辑用堆内实现真跑过，但**没有**
  endpoint / 凭据 / multipart / 区域策略。`InMemoryCasStore` 的 Javadoc 里写明了这一点。
- **041 ≥95% 精确重跑命中率基准**。**没有跑过任何负载**，不能声称达标。

另外，Skill 的 Required artifacts 里的**数据库迁移、OpenTelemetry、告警、runbook** 都没做；
`modules/cas` **没有任何调用者**，控制面/工作流/runner 都还没接。

## 待你在 Mac 上做的

```bash
cd /Users/stephen/DevProjects/AIProjects/elmos
mvn -q -pl modules/cas -am test
```

（`-am` 会连带 build 父 pom；`modules/cas` 只依赖 junit-jupiter，不依赖其他 elmos 模块。）

## 下一步的判断题

`elmos-content-addressed-cache` 的依赖是 `elmos-architecture-contract-governance` 与
`elmos-repository-snapshot-workspace`。真正把这块变成收益，需要**接调用方**——
最短的一条是把 `modules/snapshot` 的产物写进 `modules/cas`，再让 Java 迁移闭环用 action key
判定重跑。在接上之前，本模块的价值是 0，这一点不要在状态表里写成别的。
