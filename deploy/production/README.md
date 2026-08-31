# deploy/production

更新日期：2026-07-29
本目录是**第一版商业化部署的制品**。它们尚未在任何环境执行过——
RISK-DEPLOY-001 与 RISK-SRE-001 保持 `OPEN`，直到在 staging 真实起停并留下证据。

```
deploy/production/
├── README.md                              本文件
├── elmos-commercial.env.example           全部生产环境变量模板
├── compose/
│   └── docker-compose.production.yml      Tier 1 编排（YAML 已校验，未执行）
├── postgres/
│   └── configure_hosted_runtime.sql       对象存储后端显式激活
├── runner/
│   └── RUNNER_PRODUCTION_BASELINE.md      已实现托管执行面与证据边界
├── observability/
│   └── prometheus-rules.yml               12 条告警（promtool 3.5.0 校验通过）
└── backup/
    └── RESTORE_DRILL.md                   恢复演练手册（关闭 RISK-DATA-001 的唯一途径）
```

配套脚本：

- `scripts/operations/provision_runner_host.sh` —— Runner 主机预置与失败关闭校验
- `scripts/operations/configure_control_plane_runtime_role.sh` —— 控制面最小权限运行角色
- `scripts/commercial/validate_pricing_catalog_publication.py` —— 定价目录发布门禁

---

## 各制品的验证状态（不要越级引用）

| 制品 | 已验证 | 未验证 |
|---|---|---|
| `docker-compose.production.yml` | YAML 可解析、8 个服务、锚点合并正确、profile 切分正确 | **从未 `up` 过**；`read_only`/`user` 标记 VERIFY-REQUIRED 的项依赖镜像实际写入路径 |
| `prometheus-rules.yml` | `promtool check rules` → SUCCESS: 12 rules found | 未对接指标源；无一条告警被真实触发/恢复；阈值未用基线校准 |
| `provision_runner_host.sh` | `bash -n` 通过；`--check` 与 4 类危险路径守卫已实测（退出码 3/4 符合预期） | `--apply` 从未在真实主机执行 |
| `validate_pricing_catalog_publication.py` | 6 个用例实测通过（含伪造 PUBLISHED 被阻断、免费套餐被改成收费被拒） | 未接入 CI |
| `RESTORE_DRILL.md` | —— | **演练本身未执行**；这是关闭 RISK-DATA-001 的前提 |
| `RUNNER_PRODUCTION_BASELINE.md` | 持久队列、Runner Agent、租约/轮换、隔离和对象存储实现已通过本地测试 | **未部署到真实 Runner 集群**；真实 Podman、网络策略、多节点故障与独立隔离验证均 `NOT_RUN` |

---

## 起步顺序

```bash
# 1. 环境变量
cp deploy/production/elmos-commercial.env.example /srv/elmos/elmos.env
chmod 0600 /srv/elmos/elmos.env
# 逐项填写；未填项对应能力会失败关闭，这是预期行为

# 管理员登录邮件 Secret：Web 容器以 UID 10001 运行，文件必须 owner-only 且可读。
sudo install -d -o 10001 -g 10001 -m 0700 /srv/elmos/secrets
sudo install -o 10001 -g 10001 -m 0600 /dev/null /srv/elmos/secrets/resend-api-key
# 通过 Secret Manager 或无回显的受控流程写入 Resend API Key；不要写入 shell 历史。
# 网络策略仅为 Web Console 放行 api.resend.com:443；禁止重定向与其他邮件端点。

# 2. PostgreSQL 迁移完成后配置 NOBYPASSRLS 运行角色与对象后端
scripts/operations/configure_control_plane_runtime_role.sh
psql "${ELMOS_DATABASE_URL#jdbc:}" \
  -f deploy/production/postgres/configure_hosted_runtime.sql \
  -v backend_kind=S3 ...                         # 其余精确参数见脚本头

# 3. Runner 主机（独立机器）
ELMOS_RUNNER_USER=elmos-runner ELMOS_RUNNER_ROOT=/srv/elmos/runner \
  scripts/operations/provision_runner_host.sh --check
sudo -E scripts/operations/provision_runner_host.sh --apply

# 4. 每个 Runner 节点分别签发一次性 enrollment，再渲染 Agent 清单
# 同一个 enrollment Secret 绝不能跨副本复用。

# 5. 应用主机（先在 staging）
docker compose --env-file /srv/elmos/elmos.env \
  -f deploy/production/compose/docker-compose.production.yml up -d
docker compose --env-file /srv/elmos/elmos.env \
  -f deploy/production/compose/docker-compose.production.yml \
  --profile spring up -d                           # 只在售卖 Spring 升级时

# 6. 告警
promtool check rules deploy/production/observability/prometheus-rules.yml

# 7. 恢复演练（上线前必做一次）
# 按 deploy/production/backup/RESTORE_DRILL.md 执行，产出 drills/drill-<时间戳>.md

# 8. 定价目录门禁（CI 常驻 + 开售前）
python3 scripts/commercial/validate_pricing_catalog_publication.py
python3 scripts/commercial/validate_pricing_catalog_publication.py --check-publishable
```

第 8 步当前返回：

```
DECISION=PUBLICATION_BLOCKED   （--check-publishable，退出码 3）
  - sellerLegalEntityStatus='NOT_CONFIGURED'
  - taxStatus='NOT_CONFIGURED'
  - paymentStatus='NOT_CONFIGURED'
  - costValidationStatus='NOT_RUN'
  - taxPresentation='UNSPECIFIED'
```

**这是正确结果**，不是需要修的测试失败。它会一直阻断到经营主体、税务、
支付商户和单位经济性四件事真的做完为止。

---

## 建议接入 CI

在既有 `.github/workflows/ci.yml` 增加一个轻量作业，防止定价目录被误改：

```yaml
  pricing-catalog-gate:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5
      - run: python3 scripts/commercial/validate_pricing_catalog_publication.py
```

注意用 `verify` 模式（不加 `--check-publishable`）：它只在目录**声称 PUBLISHED 却没有
闭合前置条件**时失败，不会因为目录还是 DRAFT 就让 CI 变红。
`--check-publishable` 属于开售前的人工门禁，不适合放进日常 CI。
