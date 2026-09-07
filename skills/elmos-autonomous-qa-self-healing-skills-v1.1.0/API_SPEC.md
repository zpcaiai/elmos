# QA Control Plane & Project Output API Draft

Base path: `/api/v1/qa`

## 1. 创建运行

### `POST /runs`

```json
{
  "project_id": "elmos-demo",
  "snapshot_ref": "git:sha256:...",
  "mode": "repair",
  "scope": {"requirements": ["REQ-*"], "changed_since": "<git-sha>"},
  "test_profiles": ["functional", "ui", "performance", "stress"],
  "quality_gate": "strict-default-v2",
  "budgets": {"wall_clock_seconds": 14400, "repair_iterations": 3},
  "project_output": {
    "enabled": true,
    "mode": "both",
    "include_test_sources": true,
    "include_qa_evidence": true,
    "include_replay": true,
    "bundle_formats": ["zip"],
    "publish_partial_on_failure": true
  },
  "idempotency_key": "client-generated-key"
}
```

`plan-only` 可将 `project_output.enabled` 设为 false；其他模式默认 true，且不能通过关闭输出绕过质量门禁。

## 2. Run 控制

- `GET /runs/{run_id}`：状态、阶段、进度、ETA、预算、阻塞项、测试摘要和产出摘要。
- `POST /runs/{run_id}:pause`
- `POST /runs/{run_id}:resume`
- `POST /runs/{run_id}:cancel`
- `POST /runs/{run_id}:approve`

## 3. 测试计划与测试文件

- `GET /runs/{run_id}/plan`
- `GET /runs/{run_id}/cases?status=&type=&requirement_id=`
- `GET /test-cases/{test_case_id}`
- `POST /test-cases/{test_case_id}:replay`
- `GET /runs/{run_id}/test-artifacts`
- `GET /test-artifacts/{artifact_id}`
- `GET /test-artifacts/{artifact_id}/content`（受权限与大小限制）
- `GET /test-artifacts/{artifact_id}/lineage`
- `POST /test-artifacts/{artifact_id}:revalidate`

测试用例响应应包含 `materialized_artifact_refs`，测试文件响应应包含需求、用例、原生路径、哈希、验证状态和重放入口。

## 4. 缺陷与修复

- `GET /runs/{run_id}/defects`
- `GET /defects/{defect_id}`
- `GET /defects/{defect_id}/repair-plans`
- `POST /repair-plans/{repair_plan_id}:execute`
- `POST /patches/{patch_id}:approve`
- `POST /patches/{patch_id}:reject`

修复测试文件或产品代码后，必须创建新的 Artifact 版本和 `supersedes` 谱系，禁止原地覆盖已认证文件。

## 5. 项目产出与下载

- `GET /runs/{run_id}/outputs`：列出该运行发布的 ProjectOutput。
- `GET /outputs/{output_id}`：产出状态、修订、质量摘要、Bundle 和下载权限。
- `GET /outputs/{output_id}/manifest`
- `GET /outputs/{output_id}/test-artifact-set`
- `GET /outputs/{output_id}/bundles`
- `POST /outputs/{output_id}:verify-integrity`
- `POST /outputs/{output_id}:supersede`
- `GET /projects/{project_id}/outputs?revision=&status=`
- `GET /projects/{project_id}/outputs/latest`

### 下载

- `GET /outputs/{output_id}/bundles/project-with-tests:download`
- `GET /outputs/{output_id}/bundles/tests-only:download`
- `GET /outputs/{output_id}/bundles/qa-evidence:download`
- `GET /outputs/{output_id}/bundles/repair-patches:download`

下载接口返回短期签名 URL 或流式响应；必须验证租户、项目权限和 Bundle 状态。未认证/失败产出在文件名和响应元数据中明确标记。

## 6. 报告与证据

- `GET /runs/{run_id}/report`
- `GET /runs/{run_id}/certificate`
- `GET /evidence/{evidence_id}`
- `GET /runs/{run_id}/evidence-manifest`

## 7. 事件

至少发布：

- `qa.run.created|started|paused|resumed|cancelled|completed`
- `qa.plan.generated`
- `qa.test.generated|materialized|validated|started|passed|failed|blocked|flaky`
- `qa.test_artifact.created|updated|stale|superseded|published`
- `qa.defect.created|triaged`
- `qa.repair.planned|patched|verified|rejected|approved`
- `qa.gate.passed|failed`
- `qa.report.published`
- `qa.project_output.assembling|published|failed|superseded`
- `qa.output_bundle.created|verified|downloaded`

每个事件包含 `event_id`、`tenant_id`、`project_id`、`run_id`、`sequence`、`occurred_at`、`causation_id`、`correlation_id` 和 `payload_schema_version`。

## 8. 幂等与一致性

- 创建 Run、发布 Output、创建 Bundle 和执行修复均需幂等键。
- 产出先写临时对象键，校验完成后原子切换为可见状态。
- Manifest 是文件集合的事实来源；对象存储中存在但不在 Manifest 的文件不得对用户展示。
- 已认证 Manifest 与 Bundle 不得原地修改，只能发布新修订。
