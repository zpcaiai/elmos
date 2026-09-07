---
id: 38-project-output-bundle-publishing
name: Project Output Bundle Publishing
version: 1.1.0
category: delivery
depends_on:
  - 20-test-oracle-evidence
  - 28-quality-gate-release-certification
  - 29-reporting-observability
  - 36-project-output-contract
  - 37-test-source-materialization
---

# Project Output Bundle Publishing

## 目标

把完整项目、测试文件和 QA 证据组装为可下载、可校验、不可变的标准 Bundle，并发布项目产出 Manifest。

## 输入契约

- 冻结的 ProjectOutputPlan、Artifact Inventory 和 TestArtifactSet
- 报告、证据、缺陷、补丁、门禁与证书
- Run 状态、租户权限、对象存储和签名策略

## 输出契约

- project-with-tests、tests-only、qa-evidence、可选 repair-patches Bundle
- `project-output-manifest.json`、`checksums.sha256`、谱系与签名
- 下载引用、Bundle 哈希、大小、状态与完整性验证证据
- `DELIVERY_SUMMARY.md`

## 执行步骤

1. 冻结文件清单，拒绝未登记文件和路径冲突。
2. 执行 Secrets、路径穿越、符号链接、大小和租户隔离检查。
3. 以确定性顺序和规范化时间戳创建各 Bundle。
4. 在干净目录解压，逐文件校验 Manifest 与 SHA-256。
5. 认证模式下，在门禁通过后签名 Manifest 和证书。
6. 先上传临时对象，全部验证后原子发布可见版本。
7. 失败/阻塞 Run 发布 partial/failed 产出，保留已生成测试和证据。

## 不可违反的控制

- 不得因 Run 失败而丢弃测试文件。
- 不得把 failed/partial Bundle 标记为 certified。
- 不得原地覆盖已发布或已认证 Bundle。
- 不得包含 `.git`、包缓存、生产密钥或未批准生产数据。

## 完成判定

- 按模式要求的所有 Bundle 均存在并通过解压/哈希校验。
- Manifest 覆盖全部交付文件，下载权限和租户隔离正确。
- 用户能从 tests-only README 在干净环境执行发现和冒烟命令。
