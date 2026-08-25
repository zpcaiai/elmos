# 本地构建配置与步骤

本文档对应一次真实的 `assemble_project` + `verify_assembled_project` 运行产物：
一个由 3 个已通过 `typed-pure-function-v1` 剖面认证的翻译单元
组成的 java 库工程。这是一个**库**，不是一个服务——本地"运行"指的是
构建、类型检查和单元验证，不存在需要监听的端口或健康检查地址。

## 硬件建议

- 最低配置：2 vCPU / 4 GB RAM / 5 GB 可用磁盘
- 推荐配置：4 vCPU / 8 GB RAM / 10 GB 可用磁盘
- 精确工具链：`OpenJDK 21.0.11 + Maven`（与生成该工程时 `exact_toolchain()` 强制校验的版本一致）

## 构建步骤

```bash
cd <assembled-project-directory>
mvn -q -DskipTests package
```

## 完成标准与限制

- 本地完成仅表示：精确工具链可用、全项目编译/类型检查通过（`assembly-manifest.json`
  中 `build_verification_status: "PASSED"`）。
- 每个翻译单元位于独立命名空间/模块下，彼此从不合并；跨单元同名声明的语义等价性
  未被验证，调用方必须按单元 ID 单独导入，不能假设可以做统一的批量导入。
- 独立验证与外部认证仍为 `NOT_RUN` / `NOT_CERTIFIED`；`assembly-manifest.json` 中
  `excluded_units` 列出的失败/跳过单元不在本工程覆盖范围内。
