# Batch 40 · 11 条凭据扫描发现 — 分诊工作表（2026-09-01）

`b40-credential-scan-triage` 这条 claim 现在是 `INCONCLUSIVE`，原因写在 claim 自己的
limitation 里：

> Triage is outstanding. Every actionable finding must be either fixed or added to
> `config/secret-scan-allowlist.json` with a reason, an owner and an expiry before this
> claim can pass.

也就是说，这是全仓唯一「只差人做一次判断」就能从 `INCONCLUSIVE` 推向确定态的项。
本文件把这 11 条的现场证据摊开，给出**建议判定**，供有权的人签字。
**本文件不改变任何认证状态，也没有替任何人做出判定。**

## 0. 先决条件：证据已过期，动手前必须重跑扫描

`b40-secret-scan.json` 的 `startedAt` 是 **2026-08-06T11:25:35Z**，而它引用的多个文件此后
被改过。已确认的漂移：

- 第 5 条记的是 `engines/project-synthesis-engine/tests/test_synthesis.py:1152`，
  但当前文件的该行是 `_check_exact_toolchain(...)`，与凭据无关；同类命中已移到
  **1326 / 1387** 行。
- 第 11 条所在的 `scripts/operations/rootless_project_runner.py` 最后修改于 2026-09-01，
  晚于扫描。

这一点在机制上很要紧：允许清单**按 `fingerprint` 匹配**，而
`fingerprint = sha256(相对路径, 规则, 命中值)`（`scripts/batch40_secret_scan.py:102`）。
文件一改，指纹就变，照着旧指纹写的豁免会静默失效——扫描仍报 11 条，claim 仍不通过。

所以顺序是：**先重跑扫描拿到当前指纹，再按下表落允许清单**。

```
python3 scripts/batch40_secret_scan.py --allowlist config/secret-scan-allowlist.json
```

## 1. 逐条现场证据与建议判定

`match` 列是扫描器的脱敏输出；「现场」列是本次实际读取源文件看到的内容。

| # | 严重度 | 规则 | 位置 | 现场 | 建议判定 |
|---|---|---|---|---|---|
| 1 | high | connection-string-password | `apps/control-plane/.../OperationsNotificationDispatcherTest.java:24` | **未读取**（路径层级超出文件桥限制） | 待读取后判定；路径在 `src/test/java` 下，先按测试夹具推定 |
| 2 | high | connection-string-password | `apps/web-console/e2e/generation-source-ingestion.spec.ts:130` | `new URL("https://user:secret@example.com/docs?q=token#private")`，紧接着断言 `origin` 等于 `https://example.com/docs` | **误报**。这段代码的存在目的就是证明凭据会被剥掉；删掉它等于删掉该保护的证据 |
| 3 | high | connection-string-password | `engines/.../python_production_target.py:375` | 生成代码模板里写死 `postgresql://postgres:integration-only@127.0.0.1:5432/generated` | **需要产品决策**，见 §2 |
| 4 | high | connection-string-password | `engines/.../python_production_target.py:388` | 同上，`postgresql://app_runtime:integration-runtime-only@127.0.0.1:5432/generated` | **需要产品决策**，见 §2 |
| 5 | high | connection-string-password | `engines/.../tests/test_synthesis.py:1152`（已漂移到 1326 / 1387） | `http://user:secret@127.0.0.1:7890`、`https://user:secret@maven.example.test/...` | **误报**，与第 2 条同类：脱敏行为的负例夹具 |
| 6 | high | connection-string-password | `engines/python-engine/tests/test_batch12.py:103` | 位于 `test_private_index_credentials_are_redacted`，写入 `--extra-index-url https://user:secret@packages.example/simple` 后断言 `"secret" not in value` | **误报**，同上 |
| 7 | high | connection-string-password | `scripts/batch46/synthesize_seed_data.py:180` | `COMPOSE_DSN` 常量，四条全部指向 `127.0.0.1`，口令字面量是 `smoke-local-only` | **误报 / 可接受**：本地 compose 冒烟环境，口令自述用途，无外部可达面 |
| 8 | medium | assigned-credential | `apps/java-engine-worker/.../EphemeralSpringTransformationExecutionPortTest.java:143` | **未读取**；脱敏形态 `tra…es`，长 46 | 待读取后判定；路径在 `src/test/java` 下 |
| 9 | medium | assigned-credential | `apps/web-console/e2e/usage-meter-ui.spec.ts:8` | `const token = "elmos-e2e-local-token-32-characters"`（长 35，与脱敏形态吻合） | **误报**：字面量自述是本地 e2e 令牌，只被同文件的测试头部使用 |
| 10 | medium | assigned-credential | `apps/workspace-service/.../WorkspaceSecretRegistryTest.java:12` | **未读取**；脱敏形态 `sho…en`，长 17，与 `short-lived-token` 长度一致 | 待读取后判定；高度疑似测试常量 |
| 11 | medium | assigned-credential | `scripts/operations/rootless_project_runner.py:422` | 脱敏形态 `run…rd` 长 16 == `runtime_password`。该文件里 `runtime_password` 是从 `/run/secrets/postgres-runtime-password` 读出的**变量名**，没有任何口令字面量 | **误报**：规则命中的是标识符，不是值 |

小结：11 条里 6 条有现场证据支持判为误报，2 条需要产品决策，3 条因文件桥的层级限制没读到。

读那 3 个 Java 文件（层级超限，只能在本机看）：

```
sed -n '20,28p'   apps/control-plane/src/test/java/io/elmos/controlplane/OperationsNotificationDispatcherTest.java
sed -n '139,147p' apps/java-engine-worker/src/test/java/io/elmos/worker/EphemeralSpringTransformationExecutionPortTest.java
sed -n '8,16p'    apps/workspace-service/src/test/java/io/elmos/workspaceservice/WorkspaceSecretRegistryTest.java
```

## 2. 第 3、4 条是唯一需要产品决策的

其余 9 条都落在测试或本地冒烟脚本里。只有这两条落在 `src/` 的**产品输出路径**上：
`python_production_target.py` 是项目合成引擎的目标模板，它把这两条 DSN
**写进生成给用户的项目**里。

可辩护的理由是：两条都绑 `127.0.0.1`，口令字面量自述用途
（`integration-only` / `integration-runtime-only`），是集成环境脚手架而非真实凭据。
可反驳的理由是：生成物一旦被用户直接部署，这就是一份出厂即固定的数据库口令，
而扫描器对生成项目本身不设防。

两条路，选一条：

- **接受现状**：把两条指纹写进允许清单，reason 写明「生成脚手架、仅回环、口令自述」，
  给一个较短的 expiry，到期强制复审。
- **改实现**：模板改成从环境变量或启动时生成的一次性口令取值，让扫描器自然不再命中。
  代价是生成项目的首启流程要跟着改。

这条不该由 Agent 替你选。

## 3. 允许清单条目模板

指纹**必须取自重跑后的报告**，不要照抄下表里 2026-08-06 那批（见 §0）。
`owner` 与 `expiresOn` 是问责字段，机器不能代填。

```json
{
  "allowed": [
    {
      "fingerprint": "sha256:<重跑后的指纹>",
      "reason": "e2e 负例夹具：断言 URL 凭据被剥离，非真实凭据",
      "owner": "<签字人>",
      "expiresOn": "<YYYY-MM-DD>"
    }
  ]
}
```

缺 `reason` / `owner` / `expiresOn` 任意一项，该条目会被
`load_allowlist`（`scripts/batch40_secret_scan.py:180`）直接忽略并记进 `problems`，
豁免不生效；`expiresOn` 过期后自动失效。

供对照的 2026-08-06 指纹（**仅作追溯用**）：

```
1  sha256:6988f6293f1258c524907b848d4cc4b6  OperationsNotificationDispatcherTest.java:24
2  sha256:9c0641a158e30ff03c504221d0ff3293  generation-source-ingestion.spec.ts:130
3  sha256:abdf030c0a97a1b8001e49c9e4aa6216  python_production_target.py:375
4  sha256:b236b47439b2a02f2339df76b812a5f5  python_production_target.py:388
5  sha256:fc38f9a0e102c99a8a0fe4e117d9af27  test_synthesis.py:1152
6  sha256:c1d9777ffa47cf80abf3787b95b63ad7  test_batch12.py:103
7  sha256:0ffdd027187fe01914b69e31c350a89e  synthesize_seed_data.py:180
8  sha256:60ca2f98bb555164426d3b79a0ae24d0  EphemeralSpringTransformationExecutionPortTest.java:143
9  sha256:08132931d15f9236622c0e99f99d8cc2  usage-meter-ui.spec.ts:8
10 sha256:c50738d29f6851da3ef5c4e7d237d476  WorkspaceSecretRegistryTest.java:12
11 sha256:350a330eea913b5ba9991f2bd2ea0d88  rootless_project_runner.py:422
```

## 4. 关于那 2,615 条 advisory

它们是熵值命中，扫描器已按 `limitations` 第一条降级为咨询性、不参与门禁，
`secretLeakCount` 只数 actionable 的 11 条。这批不需要逐条分诊，也不阻塞这条 claim。

## 5. 做完之后

允许清单落地并重跑扫描后：

1. 报告里 `findings` 应剩 0 条 actionable、`suppressed` 增加对应条数，退出码回到 0。
2. `b40-credential-scan-triage` 的 statement 需要改写——它现在明写「none has been
   confirmed as a live credential or dismissed as a fixture」，这句在分诊完成后就不成立了。
3. claim 状态可从 `INCONCLUSIVE` 推进。注意这只解开 Batch 40 的**这一条**；
   pack 的 `decision: BLOCKED` 还有 25 项阻塞（指标未测量、零容忍未评估、
   evidence-manifest 未产出等），见 `docs/UNCLOSED_ITEMS_AUDIT_2026-09-01.md` §2。
