# miniapp-migration-evidence-reporter — 执行契约

## 调用边界

- 阶段：`evidence`
- 任务 ID：MAPP-039, MAPP-040
- 上游技能：miniapp-ci-build-release, miniapp-differential-testing, miniapp-visual-regression-testing, miniapp-privacy-permission-auditor
- 该技能只修改其声明的工作区；源仓库默认只读。
- 所有目标平台输出位于 `runs/<run-id>/platforms/<platform>/`，不得交叉覆盖。
- 任何文件写入使用临时文件 + 原子 rename；中断后可从最近成功 checkpoint 恢复。

## 输入契约

- all run artifacts
- gate results
- task ledger
- approval records
- cost records

每项输入至少包含：

1. `artifact_id`
2. `content_hash`
3. `producer`
4. `schema_version`
5. `created_at`
6. `source_revision`（适用时）

## 输出契约

- migration-evidence.json
- compatibility-report.html
- validation-report.md
- release-readiness.md
- artifact-index.json

每项输出必须登记到 `artifacts-index.json`：

```json
{
  "artifact_id": "miniapp-migration-evidence-reporter:example",
  "path": "relative/path",
  "sha256": "<64-hex>",
  "schema": "schemas/<name>.schema.json",
  "producer": "miniapp-migration-evidence-reporter",
  "task_id": "MAPP-039",
  "status": "passed"
}
```

## 幂等与缓存

- 幂等键：`sha256(skill-name + skill-version + normalized-input-hashes + policy-hash + toolchain-profile-hash)`。
- 命中成功缓存时仍需确认产物存在且哈希一致。
- 工具链版本、平台 profile、能力注册表或 Schema 变化必须使缓存失效。
- 失败缓存只用于抑制完全相同且已知不可重试的请求，不得掩盖新输入。

## 可观测性

至少记录以下事件：

- `skill.started`
- `skill.input_validated`
- `skill.checkpoint_saved`
- `skill.output_emitted`
- `skill.gate_failed`
- `skill.blocked`
- `skill.completed`

每个事件包含 `tenant_id`、`run_id`、`task_id`、`skill_name`、`attempt`、`trace_id`、`duration_ms`、`cost` 和脱敏错误信息。

## 测试契约

- 所有关键 claim 有证据
- 产物索引无悬空引用
- 最终结论与门禁一致
- 成本与运行状态可追溯

最低测试层级：

- Schema/静态契约测试
- 成功路径 fixture
- 至少一个阻断或失败 fixture
- 幂等重放测试
- 中断恢复测试
- 对有副作用技能执行 dry-run 测试

## 安全边界

- 仅记录 secret reference，例如 `vault://miniapp/wechat/app-secret`。
- 不执行源仓库中的 postinstall、build hook 或任意脚本，除非在沙箱中被审批。
- 任何网络调用必须通过 allowlist、超时、重试预算和审计日志。
- 平台上传、审核、发布、支付或退款必须满足审批策略。

## Handoff

成功后向 orchestrator 返回：

```json
{
  "skill": "miniapp-migration-evidence-reporter",
  "task_ids": ["MAPP-039", "MAPP-040"],
  "status": "passed",
  "artifacts": [],
  "gate_results": [],
  "next_skills": []
}
```
