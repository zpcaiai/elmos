# 与 Elmos 项目生成、语言转换和旧系统翻新的集成

## 1. 统一 Revision 模型

```text
Source Revision
   ↓ Parser
Source Code IR
   ↓ Semantic Normalization
Semantic IR
   ↓ Rule/Mutation/Generator
Target Code IR
   ↓ Emit
Target Revision
   ↓ Build/Test/Runtime Diff
Certification Evidence
```

每个阶段都进入同一 Project Intelligence Studio：

- 在线代码阅读；
- Source/IR/Target 多栏；
- 规则命中；
- 编译/测试失败；
- 自动修复；
- 架构、流程、API、数据前后对比；
- 文档、图表、PPT 和认证报告。

## 2. Mapping

```yaml
mapping_id:
source_symbol_id:
source_revision_id:
semantic_ir_node_id:
target_symbol_id:
target_revision_id:
rule_ids: []
repair_attempt_ids: []
confidence:
evidence_refs: []
status: mapped | partial | unsupported | manual
```

## 3. 专用视图

- 源模块—目标模块；
- 源 API—目标 API；
- 源表/字段—目标表/字段；
- 源事件—目标事件；
- 源流程—目标流程；
- 架构 current/target；
- 未支持能力；
- 低置信度热图；
- 编译失败分布；
- 修复迭代；
- 行为差分；
- 性能差分；
- Strangler 切换；
- E1–E5 矩阵。

## 4. 验证层

| 层 | 证据 |
|---|---|
| Syntax | Parser/Compiler |
| Build | 可重现构建 |
| Unit | 单元测试 |
| Contract | API/Event/Schema |
| Behavior | 相同输入输出、副作用 |
| Data | 数据迁移与约束 |
| Performance | 延迟、吞吐、资源 |
| Security | Auth、数据和依赖 |
| Operations | 部署、可观测、回滚 |
| Certification | E1–E5 |

## 5. 关键边界

- 编译通过不等于功能保持；
- 单元测试通过不等于外部契约等价；
- 静态映射不等于运行路径确认；
- 人工修复不自动升级全局 Rule；
- Source/Target revision 必须冻结；
- 认证失败时，PPT/报告不得宣称迁移成功。
