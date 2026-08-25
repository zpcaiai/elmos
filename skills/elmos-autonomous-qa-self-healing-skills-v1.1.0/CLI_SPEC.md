# Elmos QA CLI Draft

命令前缀：`elmos qa`

```bash
# 仅生成计划和系统 wall-clock ETA
elmos qa plan --project . --profile strict

# 生成并物化测试文件，产出完整项目包与 tests-only 包
elmos qa generate --project . --output-mode both --emit project-with-tests,tests-only

# 生成并执行，不修改产品代码
elmos qa verify --project . --tests functional,api,ui,performance \
  --output-mode both --emit project-with-tests,tests-only,qa-evidence

# 隔离分支自动修复低风险缺陷
elmos qa repair --project . --max-iterations 3 \
  --approval-policy policies/auto-fix-policy.yaml --output-mode both

# 发布前全量认证
elmos qa certify --project . --quality-gates QUALITY_GATES.yaml \
  --sign-manifests --emit project-with-tests,tests-only,qa-evidence,repair-patches

# 查看状态与 ETA
elmos qa status <run-id> --watch
elmos qa attach <run-id>
elmos qa pause <run-id>
elmos qa resume <run-id>
elmos qa cancel <run-id>

# 查看生成的测试文件及其需求映射
elmos qa test-artifacts list <run-id> --type ui_e2e --requirement REQ-123
elmos qa test-artifacts inspect <artifact-id>
elmos qa test-artifacts diff <old-output-id> <new-output-id>

# 重放指定测试
elmos qa replay-test <test-case-id> --evidence <manifest-id>

# 项目产出
elmos qa output list --project <project-id>
elmos qa output inspect <output-id>
elmos qa output verify <output-id>
elmos qa output download <output-id> --bundle project-with-tests --dest ./downloads
elmos qa output download <output-id> --bundle tests-only --dest ./downloads
elmos qa output download <output-id> --bundle qa-evidence --dest ./downloads

# 从交付目录重新校验
python tools/validate_project_output.py ./deliverables/<project>/<revision>
```

## 输出模式

- `embedded`：生成到当前项目 Worktree，并输出 Patch/分支。
- `sidecar`：输入项目只读，在交付目录生成完整项目副本。
- `both`：两者都生成，默认值。

## 退出码

- `0`：所有质量门禁通过，所需 Bundle 完整；
- `2`：测试失败或存在阻塞项；
- `3`：规格歧义/输入不完整；
- `4`：环境或基础设施失败；
- `5`：等待审批；
- `6`：预算耗尽；
- `7`：内部错误但已保存检查点，可恢复；
- `8`：项目产出、Manifest 或 Bundle 完整性失败；
- `9`：检测到测试文件未物化、未登记或存在路径/Secrets 风险。
