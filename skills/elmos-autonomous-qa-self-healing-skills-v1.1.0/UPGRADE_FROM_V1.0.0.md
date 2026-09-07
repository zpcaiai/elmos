# 从 v1.0.0 升级到 v1.1.0

## 1. 必需变更

1. 在 Run 模型加入 `project_output` 请求和 `output_refs`。
2. 在状态机加入 `materializing_test_artifacts` 与 `publishing_output`。
3. 增加 `project_outputs`、`output_artifacts`、`output_bundles`、`artifact_lineage` 表。
4. 所有测试生成 Skill 不再只返回代码字符串，而是返回 `MaterializationPlan + ArtifactRefs`。
5. 执行前必须完成测试文件的格式化、发现、构建和冒烟校验。
6. 报告后执行 Project Output Publisher，生成三套标准 Bundle。
7. API/CLI 暴露项目产出列表、Manifest、完整性校验和下载。
8. 更新 CI 门禁：禁止 Required 测试没有文件产物，禁止未登记生成文件。

## 2. 旧运行数据迁移

- v1.0.0 历史 Run 可建立 `legacy` ProjectOutput，引用已有报告和证据。
- 无法恢复的临时测试代码不得伪造为测试文件产出；Manifest 中标记 `missing_legacy_artifact`。
- 新运行不得使用 legacy 例外。

## 3. 对象存储迁移

建议键格式：

```text
{tenant}/{project}/{revision}/artifacts/{sha256-prefix}/{sha256}
{tenant}/{project}/{revision}/bundles/{bundle-id}/{filename}
{tenant}/{project}/{revision}/manifests/{manifest-version}.json
```

认证产出开启对象锁或不可变版本；临时上传成功校验后再原子发布。

## 4. 验收

- 运行 `generate` 后可下载完整项目包和 tests-only 包。
- tests-only 包可在干净环境中按 README 完成测试发现和冒烟运行。
- 删除任一 Manifest 文件或篡改测试文件后，完整性校验必须失败。
- 测试失败时仍可下载 partial Bundle，且发布状态不是 certified。
