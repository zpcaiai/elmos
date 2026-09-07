# Changelog

## 1.1.0 — Project Deliverables Edition

### Added

- 将测试源文件集定义为每次项目任务的一等产出。
- 新增 `embedded`、`sidecar`、`both` 三种输出模式。
- 新增 Project-with-tests、Tests-only、QA-evidence 和 Repair-patches Bundle。
- 新增项目产出 Manifest、测试文件集 Schema、Bundle Schema、文件哈希和谱系。
- 新增测试文件物化、项目产出发布、版本保留与生命周期四个 Skills。
- 新增原生测试目录映射、项目产出策略、项目产出工作流、下载 API/CLI。
- 新增产出校验与打包参考工具。
- 失败/阻塞运行也强制发布 partial/failed 产出。

### Changed

- QA 主工作流增加 `MATERIALIZING_TEST_ARTIFACTS` 和 `PUBLISHING_OUTPUT` 阶段。
- 质量门禁禁止临时目录独占测试源、未登记文件、过期 Required 测试和 Bundle 校验失败。
- 自动修复后必须重新物化受影响测试并记录谱系。
- 发布认证必须同时签名 Evidence Manifest 与 Project Output Manifest。

## 1.0.0

- 初始自主测试、严格执行、缺陷定位、安全自动修复、回归和发布认证 Skills Package。
