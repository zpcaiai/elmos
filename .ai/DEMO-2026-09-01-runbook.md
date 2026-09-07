# 演示动线 Runbook（A4）

> 日期：2026-09-01 · 认领：Claude/Cowork（A4 + B4）· 来源清单：`.ai/BACKLOG-2026-08-25-demo-track.md`
> 配套依据：`.ai/FINDINGS-2026-09-01-a4-b4.md`（语料选型、重量到的准入率、量测命令、未验证项）
>
> **这份文件里的每一条命令都在 2026-09-01 真跑过一遍**，除非该步骤明确标了
> `【需 Mac】` 或 `【需真库】`。跑过的步骤直接抄了真实输出，没有编造预期值。
> 标 `NOT_PROBED` 的是"这台机器没有工具链"，标 `REJECTED` 的是"引擎明确不支持"——两者不混。

---

## 0. 这条动线**不做**的事

沿用 backlog 第 0 节，动线里一个字都不提：

| 不做 | 理由 |
| --- | --- |
| 在线调试工作台（DAP / JDWP / 断点 / 单步） | 第二阶段 |
| ChinaDB 13 个国产目标的**真 renderer** | 只演示"注册表明确说 SPEC_ONLY"这一件事，不演示转换 |
| 独立验证 / 认证 / GA | Agent 不能签发独立验证证据；全程展示 `NOT_CERTIFIED` 本身就是卖点 |
| 跨语言转换线（M29）子集扩容 | 不在本轮三条线内 |
| **web-console 新页面** | C0（2026-09-01，Ethan）已拍板：**CLI + 静态 HTML 报告**。动线只用**已存在**的 `/spring` 页面，且那一步是可选加演 |

---

## 1. 演示前置：三种环境该干什么

| 环境 | 这份动线里承担 | 实测状态 |
| --- | --- | --- |
| 任意 Linux / macOS + Python 3.12 | **第 0/1/3 幕全部**、第 2 幕的 5 步中的 4 步 | 已在 Ubuntu 22.04 aarch64 + uv CPython 3.12.13 上全部跑通 |
| 云端会话容器（可装真 PostgreSQL） | 第 1 幕 S1.3 的**真执行**证据 | 已在 PostgreSQL 16.13 上跑通，`executionStatus: PASSED` |
| 你的 Mac | S2.6（真 Maven/OpenRewrite 构建）、S2.7（`/spring` 页面 + java-engine 后端） | **本次没跑**，见第 6 节 |

### 1.0 一次性准备（≈2 分钟，联网）

```bash
# 1) 一个干净的 3.12 环境（引擎用了 datetime.UTC 和 PEP 695 type 语句，3.10 起不来）
uv venv --python 3.12 ~/elmos-demo
uv pip install --python ~/elmos-demo/bin/python "sqlglot==30.14.0"

# 2) 语料（外部 schema，不入库；仓库里没有这些 .sql）
mkdir -p ~/demo-corpus/synapse
curl -fsSL -o ~/demo-corpus/synapse/synapse-postgres.sql \
  https://raw.githubusercontent.com/element-hq/synapse/develop/synapse/storage/schema/main/full_schemas/72/full.sql.postgres

export ELMOS=<仓库根目录>
export PYTHONPATH="$ELMOS/engines/sql-dialect-engine/src"
export PY=~/elmos-demo/bin/python
```

> ⚠️ **不要**用 `make sql-dialect` 或 `uv --directory engines/sql-dialect-engine run`。
> 仓库里已经有一个 `engines/sql-dialect-engine/.venv`，它是 **macOS/arm64** 建的；
> 在别的机器上跑那条命令会把它重建掉，回到 Mac 上就用不了了。演示一律用自己的 venv + `PYTHONPATH`。

---

## 2. 第 0 幕 · 工具链自证（2 分钟，最先演）

**要传达的一句话**：这个引擎在开口之前先证明自己站在钉死的工具链上，站不住就直接闭嘴。

### S0.1 语料同一性

```bash
sha256sum ~/demo-corpus/synapse/synapse-postgres.sql
```

真实输出（2026-09-01）：

```
93ee08d4584d15a23b0cc08e903dfed50818f559e4a66642a756cc204fbb8d37  synapse-postgres.sql
```

**对得上 `.ai/measurement-2026-08-21/sql-corpus-manifest.txt` 里 2026-08-21 记的同一个 SHA。**
台词：「11 天前那次测量和今天这次，读的是同一批字节。」

- **退路**：GitHub 拉不到（断网/被墙）→ 提前把这 8 个 `.sql` 拷进 U 盘/本地目录，
  现场只跑 `sha256sum` 做同一性证明。**不要**临时换个 schema 顶上——数字会全变。
- 验证状态：**REAL_RUN**（4 个外部 pg schema + 3 个 mysql schema 全部重新拉取，
  8 个 SHA-256 与 manifest 逐个一致，见 FINDINGS §2）

### S0.2 故意装错工具链 → 拒绝服务

```bash
uv venv --python 3.12 ~/elmos-badglot
uv pip install --python ~/elmos-badglot/bin/python "sqlglot==30.13.0"
PYTHONPATH="$PYTHONPATH" ~/elmos-badglot/bin/python -m elmos_sql_dialect.cli translate \
  --source-file ~/demo/access_tokens.sql --source-dialect postgres --target-dialect mysql \
  --statement-kind TABLE --output /tmp/badglot
```

真实输出：

```json
{
  "status": "BLOCKED",
  "reason": "TOOLCHAIN_MISMATCH: certified-ddl-v1 was verified against sqlglot 30.14.0, found 30.13.0. Install the exact pinned version (see pyproject.toml) before trusting certified-ddl-v1 results."
}
```

退出码 `2`。

- **退路**：这一步不会失败——它本来就是要失败。若它**没**失败，说明装错的版本没生效，
  当场 `~/elmos-badglot/bin/python -c "import sqlglot;print(sqlglot.__version__)"` 自查。
- 验证状态：**REAL_RUN**

---

## 3. 第一幕 · SQL 方言转换（主戏，全程无需 Mac）

**要传达的三句话**：① 真实生产 schema 上能到 94%；② 剩下的 6% 每一条都有原因码；
③ 原因码不是"报错"，是"告诉你补什么就能过"。

### S1.1 全量扫描一份真实生产 schema → 静态报告

```bash
cd "$ELMOS"
$PY -m elmos_sql_dialect.cli scan \
  --repository ~/demo-corpus/synapse \
  --source-dialect postgres \
  --output ~/demo-out/synapse-scan
```

产物：`~/demo-out/synapse-scan/feasibility-report.json` 与 **`feasibility-report.md`**（给不读 JSON 的人看的那份）。

真实输出（`feasibility-report.md` 开头，2026-09-01）：

```
# Feasibility scan -- certified-ddl-v1 + certified-alter-v1 + certified-drop-v1 + certified-schema-v1
  + certified-routine-v1 + certified-view-v1 + certified-comment-v1 + certified-privilege-v1
  + certified-dml-v1 + certified-rls-v1 + certified-static-do-v1

**375 of 417 statements are inside the certified subset (89.9%, upper bound), across 1 files.**
**Disposition coverage: 417 of 417 discovered units (100.0%).**
```

演示时念这三个数：**417 条语句 / 375 条进子集 / 42 条被拒且每条都有归属**。
schema 语句口径是 **375 / 397 = 94.46%**（`Select` / `Insert` / `Command` 不算 schema）。

> CLI 的退出码是 **2**（因为 `outOfSubset != 0`）。**这是设计**，不是故障——
> 演示时要主动说破，否则观众会以为崩了。

- **退路**：报告没生成 → 十有八九是 `PYTHONPATH` 没指到 `engines/sql-dialect-engine/src`。
  先跑 `$PY -c "import elmos_sql_dialect, sqlglot; print('ok')"`。
- **退路 2**：现场不想等扫描（实测 1 个文件 <2 秒，5 个语料 104 个文件 13.6 秒），
  可以把 `~/demo-out/synapse-scan/` 事先跑好，现场只 `cat feasibility-report.md`。
- 验证状态：**REAL_RUN**

### S1.2 一条真语句：PostgreSQL → MySQL

```bash
sed -n '/^CREATE TABLE access_tokens/,/);/p' ~/demo-corpus/synapse/synapse-postgres.sql > ~/demo/access_tokens.sql
$PY -m elmos_sql_dialect.cli translate \
  --source-file ~/demo/access_tokens.sql \
  --source-dialect postgres --target-dialect mysql \
  --statement-kind TABLE --output ~/demo-out/pg2my
```

真实输出（节选）：

```json
{
  "status": "PASSED",
  "profile": "certified-ddl-v1",
  "emitted": "CREATE TABLE access_tokens (\n    id BIGINT NOT NULL,\n    user_id LONGTEXT NOT NULL, ...",
  "validation": {
    "syntaxStatus": "PASSED",
    "executionStatus": "EXECUTION_NOT_ATTEMPTED",
    "executionDiagnostics": ["no --dsn supplied; execution-level evidence stays NOT_RUN"]
  }
}
```

**这里要主动指着 `EXECUTION_NOT_ATTEMPTED` 说**：没给库就不假装跑过。这正是 S1.3 的引子。

- 验证状态：**REAL_RUN**

### S1.3 回程 + 真数据库执行（PG→MySQL→PG）【需真库】

```bash
$PY -m elmos_sql_dialect.cli translate \
  --source-file ~/demo-out/pg2my/emitted.sql \
  --source-dialect mysql --target-dialect postgres \
  --statement-kind TABLE \
  --dsn "host=/tmp port=55432 user=postgres dbname=postgres" \
  --output ~/demo-out/my2pg
```

真实输出（节选，PostgreSQL 16.13）：

```json
{
  "status": "PASSED",
  "emitted": "CREATE TABLE access_tokens (\n    id BIGINT NOT NULL,\n    user_id TEXT NOT NULL, ...",
  "validation": { "syntaxStatus": "PASSED", "executionStatus": "PASSED", "executionDiagnostics": [] }
}
```

两个可以指着讲的点：
1. `executionStatus` 从 `EXECUTION_NOT_ATTEMPTED` 变成 **`PASSED`** —— 换的不是话术，是真跑了一次。
2. 回程后 `text → LONGTEXT → TEXT`，**回到原样**。往返不掉信息。

需要的库（二选一）：
```bash
# 容器/Linux，非 macOS：
initdb -D /tmp/pgdata -A trust
pg_ctl -D /tmp/pgdata -o '-p 55432 -k /tmp' -l /tmp/pg.log start
# macOS：brew services start postgresql@16，然后 --dsn "host=localhost port=5432 user=$(whoami) dbname=postgres"
```

- **退路**：现场没库 → **跳过这步，直接说"执行级证据是 NOT_RUN"**，
  然后展示 S1.2 的 `EXECUTION_NOT_ATTEMPTED` 字段。**不要**口头说"它能执行"。
- MySQL 侧 `--dsn` 要的是 **JSON**（`{"host":...,"port":...,"user":...,"password":...}`），不是 libpq 串。
  **本次未测 MySQL 执行**（这台机器没有 MySQL）→ `NOT_PROBED`，见 FINDINGS §6。
- 验证状态：**REAL_RUN**（PostgreSQL 16.13，云端容器）

### S1.4 「它敢拒绝」——故意超出子集的语句集

> backlog 说这是卖点不是缺陷。演的时候语气要正：**先给拒绝，再给修复。**

准备（7 个文件，一次性，直接抄）：

```bash
mkdir -p ~/demo/refuse && cd ~/demo/refuse
cat > r1_qualified.sql <<'SQL'
CREATE TABLE public.orders (id bigint NOT NULL, total numeric(12,2) NOT NULL);
SQL
cat > r2_unbounded_decimal.sql <<'SQL'
CREATE TABLE ledger (id bigint NOT NULL, amount numeric NOT NULL);
SQL
cat > r5_alter.sql <<'SQL'
ALTER TABLE ONLY instance_map ALTER COLUMN instance_id SET DEFAULT nextval('instance_map_instance_id_seq'::regclass);
SQL
cat > r6_trigger.sql <<'SQL'
CREATE TRIGGER check_partial_state_events BEFORE INSERT OR UPDATE ON partial_state_events FOR EACH ROW EXECUTE PROCEDURE check_partial_state_events();
SQL
cat > r7_do_control_flow.sql <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
    CREATE ROLE app_rw;
  END IF;
END
$$;
SQL
cat > r9_insert_no_columns.sql <<'SQL'
INSERT INTO appservice_stream_position VALUES ('X', 0);
SQL
cat > r10_partial_index.sql <<'SQL'
CREATE INDEX current_state_events_member_index ON current_state_events USING btree (state_key) WHERE type = 'm.room.member';
SQL
```

（`r5` / `r6` / `r9` 三条是从 Synapse 那个文件里原样抠出来的真语句，不是编的。）

然后逐条跑：

```bash
# 文件名 与 --statement-kind 一一对应，逐条跑（实测就是这么跑的）
while read -r f kind; do
  echo "### ${f}"
  $PY -m elmos_sql_dialect.cli translate \
      --source-file ~/demo/refuse/"${f}" \
      --source-dialect postgres --target-dialect mysql \
      --statement-kind "${kind}" \
      --output ~/demo-out/refuse/"${f%.sql}" \
    | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["status"],d.get("reasonCode"));print(d.get("reason"))'
done <<'LIST'
r1_qualified.sql TABLE
r2_unbounded_decimal.sql TABLE
r5_alter.sql ALTER
r6_trigger.sql TRIGGER
r7_do_control_flow.sql DO
r9_insert_no_columns.sql INSERT
r10_partial_index.sql INDEX
LIST
```

真实输出（逐条实测，2026-09-01）：

| 文件 | `--statement-kind` | `status` | `reasonCode` | 引擎给的话 |
| --- | --- | --- | --- | --- |
| `r1_qualified.sql` | `TABLE` | `BLOCKED` | `CERTIFIED_DDL_NAMESPACE_MAPPING_REQUIRED` | table name is qualified by source schema 'public'; provide an explicit namespace_map |
| `r2_unbounded_decimal.sql` | `TABLE` | `BLOCKED` | `CERTIFIED_DDL_UNBOUNDED_DECIMAL` | DECIMAL without explicit precision is arbitrary-precision in postgres; no fixed-precision target type preserves it |
| `r5_alter.sql` | `ALTER` | `BLOCKED` | `CERTIFIED_ALTER_UNSUPPORTED_ACTION` | column type/nullability/default changes need the column's full type, which a single ALTER statement does not carry |
| `r7_do_control_flow.sql` | `DO` | `BLOCKED` | `CERTIFIED_STATIC_DO_DYNAMIC_OR_CONTROL_FLOW` | DO block contains control flow, query/DML or dynamic SQL; manual migration is required |
| `r9_insert_no_columns.sql` | `INSERT` | `BLOCKED` | `CERTIFIED_INSERT_UNSUPPORTED_TARGET` | INSERT target must be one plain table with an explicit column list |
| `r10_partial_index.sql` | `INDEX` | `BLOCKED` | `CERTIFIED_DDL_INDEX_PREDICATE_UNSUPPORTED_BY_TARGET` | mysql has no exact partial/filtered index mapping |
| `r6_trigger.sql` | `TRIGGER` | `BLOCKED` | `CERTIFIED_ROUTINE_TRIGGER_TARGET_ROUTE_REQUIRED` | trigger semantics are target-specific; this route emits only PostgreSQL trigger syntax |

**这一步最有力的一句话**：`r10` 的原因不是"我们没做"，是
**"MySQL 没有精确对应的部分索引，所以我们不猜"**。

- **退路**：某条突然 `PASSED` 了（子集在变宽——2026-08-21 时 `"Order Items"` 这种带引号标识符
  还会被拒，**今天已经 `PASSED`**）。演示前 **当天** 把这张表重跑一遍，别用隔夜的表。
- 验证状态：**REAL_RUN**（7 条逐条实测；另有 1 条 `SECURITY DEFINER` 例子落到了
  `CERTIFIED_DDL_PARSE_FAILED`，是上游 sqlglot 缺陷，属 B3 范围，**不要**放进动线）

### S1.5 原因码 → 补上 → 通过（这一幕的高潮）

```bash
$PY -m elmos_sql_dialect.cli translate \
  --source-file ~/demo/refuse/r1_qualified.sql \
  --source-dialect postgres --target-dialect mysql --statement-kind TABLE \
  --namespace-map '{"public":"appdb"}' \
  --output ~/demo-out/refuse/r1_fixed
```

真实输出：

```json
{
  "status": "PASSED",
  "namespaceProfile": {
    "name": "explicit-namespace",
    "mapping": {"public": "appdb"},
    "digest": "fd1662e45c2740b20b06196804c3510a40deb43fe879f19ead76703de8042ec9"
  },
  "emitted": "CREATE TABLE appdb.orders (\n    id BIGINT NOT NULL,\n    total DECIMAL(12, 2) NOT NULL\n)"
}
```

台词：「刚才那条被拒的语句，我没有改引擎、没有改 SQL，我只是**把它要的那个决定给它**——
`public` 在 MySQL 里到底叫什么。它把这个决定**留了指纹**（digest），下次谁改了都看得见。」

- 这正面回答了 backlog B1 里那句「`public.orders` 在四个方言里含义有分歧，这是 profile 决定不是补丁」。
- 验证状态：**REAL_RUN**

### S1.6 明确说"不"：ChinaDB 注册表

```bash
$PY -m elmos_sql_dialect.cli chinadb-capabilities | head -40
```

真实输出（每个目标都是）：

```json
{"id": "dm8", "label": "DM8", "adapterId": "chinadb.dm8.target-adapter.v1",
 "implementationStatus": "SPEC_ONLY", "externalExecution": "NOT_RUN", "certification": "NOT_CERTIFIED"}
```

13 个国产目标，**全部 `SPEC_ONLY`**。台词：「问我们支不支持达梦，答案是：注册表里有它，
状态是规格层，没有验证过的目标适配器。我们不会拿一个'兼容模式'冒充精确渲染器。」

- 验证状态：**REAL_RUN**

---

## 4. 第二幕 · Spring 老项目翻新（不需要 Maven 的那 4 步 + 需 Mac 的 2 步）

### S2.1 路线契约门禁（≈3 秒，任意机器）

```bash
cd "$ELMOS" && python3 scripts/operations/validate_spring_route_contract.py
```

真实输出（单行 JSON，节选）：

```json
{"declared_routes": 38, "implemented_routes": 36, "recorded_routes": 7,
 "default_target": "Spring Boot 3.5.3 / Java 21",
 "external_evidence_status": "NOT_RUN", "status": "PASSED"}
```

三个数字连起来讲：**声明 38 条路线 / 实现 36 条 / 真跑出证据的只有 7 条**。
「差额我们自己写在门禁输出里，不是等你去发现。」

- **退路**：这一步在任何机器上都能跑（纯 Python，不碰 git，不需 JDK）。若 `FAILED`，
  说明仓库当前确实有漂移——**照实演**，那本身就是门禁在工作。
- 验证状态：**REAL_RUN**（device 上 Python 3.10 即可）

### S2.2 Pack 校验与门禁

```bash
python3 scripts/batch30/validate_framework_pack.py framework-packs/spring-boot-2-7-18-to-3-5-3
python3 scripts/batch30/run_framework_gate.py     framework-packs/spring-boot-2-7-18-to-3-5-3
```

真实输出：

```
OK: framework-packs/spring-boot-2-7-18-to-3-5-3
OK: .../framework-packs/spring-boot-2-7-18-to-3-5-3
GATE PASS: spring-boot-2-7-18-to-3-5-3 status=limited decision=NOT_CERTIFIED
```

**最值钱的一行是 `status=limited decision=NOT_CERTIFIED`。**
台词：「门禁通过了，但它给自己的结论是'受限、未认证'。这条产品线不会自称认证。」

- 验证状态：**REAL_RUN**

### S2.3 复算配方 SHA-256（对应 A4 原始要求里的"浏览器复算 SHA-256"，离线版）

```bash
python3 -c "import json;print(json.load(open('evidence/spring-routes/boot-2.7-maven-to-boot-3.5.3-java-21.json'))['transformation']['recipe_sha256'])"
sha256sum apps/java-engine-worker/src/main/resources/rewrite/spring-boot-2.7.18-to-3.5.3.yml
```

真实输出（两行一致）：

```
4640b23ffb5fe35801e42b59ee21c0d36a33fcfcfab8b1508be138cec4189d7c
4640b23ffb5fe35801e42b59ee21c0d36a33fcfcfab8b1508be138cec4189d7c  apps/java-engine-worker/.../spring-boot-2.7.18-to-3.5.3.yml
```

台词：「证据里写的那个配方指纹，就是仓库里这个文件此刻的指纹。当场算，不是我提前贴的。」

- ⚠️ **同一份证据里的 `jar_sha256` 你现在算不出来**——那两个 jar 是 Mac 上构建时产生的，
  不在仓库里。要复算 jar 必须走 S2.6。**演示时别顺手承诺**。
- 验证状态：**REAL_RUN**

### S2.4 失败分支（第一种）：真实失败的运行记录

```bash
cat evidence/spring-routes/attempts/boot-2.7-maven-to-boot-4.1.0-java-21.latest-attempt.json
```

真实内容（节选）：

```json
{"attempted_at": "2026-08-26T11:01:17Z",
 "execution_status": "FAILED",
 "failure": "JAVA_HOME_INVALID:ELMOS_JAVA_17_HOME -> /Users/stephen/.sdkman/candidates/java/17.0.11-tem has no bin/java",
 "record_type": "NON_CERTIFYING_ROUTE_ATTEMPT",
 "evidence_scope": "LOCAL_ATTEMPT_AUDIT_ONLY",
 "canonical_evidence": {"path": "evidence/spring-routes/boot-2.7-maven-to-boot-4.1.0-java-21.json", "updated": false}}
```

台词（这段是整场最能建立信任的 30 秒）：
「这是一次**真失败**。失败原因是具体的：某个 JDK 路径下没有 `bin/java`。
注意最后一行 —— `updated: false`：**失败的这次没有去覆盖正式证据**。
我们的失败记录和成功记录不是同一类文件。」

- 验证状态：**REAL_RUN**（只读文件）

### S2.5 失败分支（第二种，现场制造）：篡改证据 → 门禁当场变红

```bash
# 演示者在自己的工作副本上做，演完 revert
python3 - <<'PY'
import json,pathlib
p = pathlib.Path("evidence/spring-routes/boot-2.7-maven-to-boot-4.1.0-java-21.json")
d = json.loads(p.read_text()); d["behavioral_parity"] = False
p.write_text(json.dumps(d, indent=1))
PY
python3 scripts/operations/validate_spring_route_contract.py; echo "exit=$?"
```

真实输出：

```json
{"reason": "BOOT_4_1_LOCAL_EVIDENCE_EXECUTION_DRIFT:boot-2.7-maven-to-boot-4.1.0-java-21", "status": "FAILED"}
exit=2
```

- ⚠️ **必须改 4.1.0 那条路线的证据。** 实测：改 `boot-2.7-...-to-boot-3.5.3` 那条证据里的
  `recorded_tuple.target_boot`，门禁**仍然 PASSED** —— 该 validator 只对
  `BOOT_4_1_LOCAL_EVIDENCE` 那两条路线做证据交叉校验（见 FINDINGS §5.3，这是个真实缺口）。
  演示时挑能红的那条，别当场翻车。
- **退路**：不想动仓库文件 → 用 `cp -rs` 做一份符号链接影子树，把要改的那个 json
  换成实体副本再改（本次就是这么验的）。注意 `scripts/` 必须**实体拷贝**，
  因为 validator 用 `Path(__file__).resolve()` 定位仓库根，符号链接会被解析回真仓库。
- 验证状态：**REAL_RUN**（在影子树上，真仓库未被写入）

### S2.6【需 Mac】真跑一次翻新

```bash
python3 scripts/batch30/run_spring_boot_reference.py --repo-root .
```

- **本次未跑。原因**：需要 Maven 3.9.11 + 两套精确 JDK，且脚本里把 JDK 路径写死成
  `/Library/Java/JavaVirtualMachines/jdk-17.jdk/...` 与 `/opt/homebrew/Cellar/openjdk@21/...`
  —— 是 macOS 专属路径。**这是 `NOT_PROBED`，不是 `REJECTED`。**
- ⚠️ **顺带核实了 backlog 第 3 节的开放前提 ①**：这个脚本**只接受 `--repo-root`
  （elmos 仓库根），不能指向任意外部仓库**，参考工程由 `execute(repo)` 内部构造。
  所以 **A1 是"先改脚本"，不是"喂语料"**。详见 FINDINGS §5.1。
- 验证状态：**NOT_PROBED（需 Mac）**

### S2.7【需 Mac + 需后端】`/spring` 页面里浏览器复算 SHA-256

- 页面在：`apps/web-console/app/spring/`（**已存在**，不违反 C0"不做新页面"）。
- 复算逻辑在 `SpringModernizationStudio.tsx` 第 582–605 行：拿 `x-content-sha256` 响应头、
  用 `crypto.subtle.digest("SHA-256", ...)` 在浏览器里重算、和证据里的 `artifactSha256`
  以及 `content-length` 三方比对，不一致就抛 `ARTIFACT_INTEGRITY_MISMATCH`。
- **本次未跑。原因**：这条路要 `ELMOS_SPRING_PROXY_ENABLED=true` +
  `JAVA_ENGINE_BASE_URL` 指向一个真在跑的 java-engine 服务（见
  `app/api/spring-upgrades/proxyPolicy.ts`），也就是要 JVM 全家桶。**`NOT_PROBED`。**
- **退路（强烈建议默认走这条）**：**不演页面**，用 S2.3 的 `sha256sum` 当场复算配方指纹。
  信息量一样（"指纹当场算"），依赖少一个数量级。C0 既然选了 CLI，动线就别把命押在页面上。
- 验证状态：**NOT_PROBED（需 Mac + 后端）**

---

## 5. 第三幕 · 代码理解 / 图 / 学习演示（CLI + 静态 HTML，C0 路线）

> ⚠️ **归属提醒**：`engines/project-intelligence-engine` 当前由 **C1 / C2 / C3 三条线同时在改**
> （2026-09-01 认领表）。下面的命令与输出是 **2026-09-01T03:45Z** 那一刻真跑的结果，
> 演示前一定重跑一遍确认没变。

### S3.1 让它自己交代能力边界

```bash
cd "$ELMOS/engines/project-intelligence-engine"
PYTHONPATH=src $PY -m elmos_project_intelligence.cli manifest | python3 -m json.tool | tail -20
```

真实输出（尾部）：

```json
"counts": {"local": 19, "partial": 26, "plan": 5, "skills": 50},
"certification": "NOT_CERTIFIED",
"external_evidence": "NOT_RUN"
```

台词：「50 个能力，**只有 19 个是本地完整实现**，26 个部分、5 个还是规划。
这句话是产品自己讲的，不是我替它讲的。」

（backlog 记的是 21 / 24 / 5，**今天实测是 19 / 26 / 5** —— 这条线正在被改，数字会动。）

- 验证状态：**REAL_RUN**

### S3.2 出一份 Diagram Spec

```bash
PYTHONPATH=src $PY -m elmos_project_intelligence.cli dispatch \
  --skill elmos-diagram-spec-engine --request ~/demo/pi-req.json
```

真实输出（节选）：

```json
{"code": "DIAGRAM_SPEC_COMPILED", "capability_state": "LOCAL", "state": "LOCAL_EXECUTED",
 "outputs": {"diagram_spec": {"diagram_id": "sha256:9827bba8...", "type": "component",
   "nodes": [{"kind":"function","label":"main"},{"kind":"module",...},{"kind":"file",...}], "edges": []}}}
```

- ⚠️ **`edges: []`**。这就是 backlog C1 说的"只收集 import 边"的现状——单文件输入没有边。
  **演示时要说破**，不要让观众自己发现图是空的。C1 正在做的就是补这一层。
- 验证状态：**REAL_RUN**

### S3.3 静态 HTML 报告 + 确定性

```bash
PYTHONPATH=src $PY -m elmos_project_intelligence.cli report \
  --spec ~/demo/pi-spec.json --output ~/demo-out/pi-report.html --title "ELMOS demo"
# 再跑一次，比指纹
PYTHONPATH=src $PY -m elmos_project_intelligence.cli report \
  --spec ~/demo/pi-spec.json --output ~/demo-out/pi-report2.html --title "ELMOS demo"
sha256sum ~/demo-out/pi-report*.html
```

真实输出：

```json
{"code": "DIAGRAM_HTML_REPORT_RENDERED", "media_type": "text/html", "bytes": 3459,
 "diagrams": 1, "raster_used": false, "certification": "NOT_CERTIFIED"}
```
```
2c770a035b6bb6e9bf2f5394d013bd442b64f235ee6ebc44555815379b53f14f  pi-report.html
2c770a035b6bb6e9bf2f5394d013bd442b64f235ee6ebc44555815379b53f14f  pi-report2.html
```

台词：「同一份 Spec 渲染两次，**字节完全一样**。这份报告可以进版本库、可以做差分。」
（`raster_used: false` 也值一句：图是矢量的，不是截图。）

- 验证状态：**REAL_RUN**

### S3.4 SVG 与 PPTX

```bash
PYTHONPATH=src $PY -m elmos_project_intelligence.cli render-svg --spec ~/demo/pi-spec.json --output ~/demo-out/pi.svg
PYTHONPATH=src $PY -m elmos_project_intelligence.cli pptx --spec ~/demo/pi-spec.json --output ~/demo-out/pi.pptx --title "ELMOS demo"
```

真实输出：

```json
{"code": "DIAGRAM_SVG_RENDERED", "nodes": 3, "edges": 0, "canvas": {"width": 496, "height": 120}, "bytes": 984}
{"code": "PRESENTATION_PPTX_WRITTEN", "slides": 1, "diagram_slides": 1, "vector_diagram": true, "bytes": 5800}
```

`pi.pptx` 是合法的 OOXML 包（13 个条目，含 `ppt/presentation.xml`、`ppt/slideMasters/`）。

- **退路**：**用真 PowerPoint / WPS 打开这一步，本次没做**（这台机器没有 Office）。
  演示前必须在演示机上**亲手打开一次**再上台。`NOT_PROBED`。
- 验证状态：**REAL_RUN（生成）/ NOT_PROBED（用 Office 打开）**

---

## 6. 全动线验证状态一览

| 步骤 | 内容 | 状态 |
| --- | --- | --- |
| S0.1 | 语料 SHA-256 同一性 | **REAL_RUN** |
| S0.2 | 错版本工具链 → `TOOLCHAIN_MISMATCH` | **REAL_RUN** |
| S1.1 | Synapse 全量扫描 → 静态报告 | **REAL_RUN** |
| S1.2 | 单语句 PG→MySQL | **REAL_RUN** |
| S1.3 | 回程 + 真 PostgreSQL 执行 | **REAL_RUN**（PG 16.13） |
| S1.4 | 7 条越界语句 → 7 个原因码 | **REAL_RUN** |
| S1.5 | namespace-map 补齐 → PASSED | **REAL_RUN** |
| S1.6 | ChinaDB 13 目标全 `SPEC_ONLY` | **REAL_RUN** |
| S2.1 | Spring 路线契约门禁 | **REAL_RUN** |
| S2.2 | pack 校验 + 门禁（`NOT_CERTIFIED`） | **REAL_RUN** |
| S2.3 | 复算 recipe SHA-256 | **REAL_RUN** |
| S2.4 | 真实失败记录（`JAVA_HOME_INVALID`） | **REAL_RUN** |
| S2.5 | 篡改证据 → 门禁 FAILED | **REAL_RUN**（影子树） |
| S2.6 | 真跑 OpenRewrite 翻新 | **NOT_PROBED（需 Mac）** |
| S2.7 | `/spring` 页面浏览器复算 | **NOT_PROBED（需 Mac + java-engine 后端）** |
| S3.1 | 能力清单自曝 19/26/5 | **REAL_RUN** |
| S3.2 | Diagram Spec | **REAL_RUN** |
| S3.3 | 静态 HTML + 确定性 | **REAL_RUN** |
| S3.4 | SVG / PPTX 生成 | **REAL_RUN** |
| S3.4b | 用真 Office 打开 PPTX | **NOT_PROBED（无 Office）** |

**19 步真跑通 / 3 步标注需 Mac 或需 Office。**

---

## 7. 现场一定会被问到的 5 个问题（照实答，别绕）

1. **「覆盖率到底多少？」**
   → 「看语料。真实生产 schema（Matrix Synapse）**schema 语句 94.5%**；
   把带种子数据的 dump 也算进分母就掉到 89.9%；混合语料整体 **75.95%**（2026-09-01 实测）。
   一个数字回答不了这个问题，我们从来不报单一数字。」

2. **「那 42 条为什么不行？」**
   → 打开 `feasibility-report.md` 的 blocker 表。**看 `Distinct` 列不是 `Count` 列**：
   24 条 `UNSUPPORTED_STATEMENT` 只有 **1 个**不同原因，就是同一个惯用法抄了 24 遍。

3. **「你们认证了吗？」**
   → 「没有。你刚才看到的每一份输出里都写着 `NOT_CERTIFIED` / `NOT_RUN`。
   独立验证不是我们能自己签的。」

4. **「支持国产数据库吗？」**
   → S1.6，13 个目标全 `SPEC_ONLY`。「有注册表，没有验证过的渲染器。」

5. **「Spring 那条线跑过几个真项目？」**
   → 「参考工程一个 controller，行为等价靠 3 个探针。这是演示级，不是交付级。
   路线声明 38 条、实现 36 条、**有真证据的 7 条**——门禁自己把这个差额打印出来。」
   （对应 backlog A1/A2，尚未开工。）

---

## 8. 演示前 30 分钟的自检清单

```bash
# 1 工具链
$PY -c "import sqlglot;print(sqlglot.__version__)"            # 必须 30.14.0
# 2 语料同一性
sha256sum ~/demo-corpus/synapse/synapse-postgres.sql          # 93ee08d4...
# 3 三个能立刻红/绿的门禁
python3 scripts/operations/validate_spring_route_contract.py  # 期望 status PASSED
python3 scripts/batch30/run_framework_gate.py framework-packs/spring-boot-2-7-18-to-3-5-3
# 4 拒绝表当天重跑（子集在变宽，隔夜的表可能已经失效）
# 5 PPTX 用演示机上的真 Office 打开一次
```
