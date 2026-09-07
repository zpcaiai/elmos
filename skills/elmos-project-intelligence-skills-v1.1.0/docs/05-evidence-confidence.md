# Evidence、Claim 与可信度模型

## 1. 证据类型

| 类型 | 示例 | 默认强度 |
|---|---|---:|
| Compiler/LSP | 精确定义、类型、引用 | 1.00 |
| Contract | OpenAPI/Proto/DDL | 0.95 |
| Runtime Trace | 特定 revision/environment span | 0.90 |
| Test Result | 固定输入、可重放测试 | 0.90 |
| Framework Rule | Spring route、ORM mapping | 0.85 |
| Static Heuristic | 字符串、命名、动态候选 | 0.40–0.70 |
| Existing Document | README/架构文档 | 0.30–0.80 |
| User Confirmation | 有身份和 revision 的确认 | 0.90 |
| LLM Statement | 无独立证据 | 0.00 |

## 2. Claim 状态

```yaml
status: confirmed | inferred | unknown | recommended | contradicted | stale
confidence: 0.0..1.0
scope:
  tenant_id:
  project_id:
  revision_id:
provenance:
  generator:
  generator_version:
  model:
  prompt_version:
evidence_refs: []
counter_evidence_refs: []
```

## 3. 冲突处理

- 声明契约与实现冲突：标记 `contradicted`，同时保留两侧证据；
- 静态边与运行 Trace 不一致：标记观测窗口和采样限制；
- 旧文档与新代码冲突：文档 claim 标记 `stale`；
- 人工确认与新证据冲突：创建 review task，不静默覆盖；
- 证据权限不足：答案显示“存在受限证据”，不泄露内容。

## 4. Artifact 绑定

- 图节点/边拥有 `claim_ids`；
- 文档段落拥有 `block_id` 和 `claim_ids`；
- PPT 页面及核心元素拥有 `slide_id/element_id` 与 `claim_ids`；
- 报告包保存 claim/evidence manifest；
- 任何 claim 失效触发 artifact stale 传播。

## 5. 防幻觉生成流程

1. 解析问题或 artifact 目标。
2. 检索最小充分证据。
3. 建立事实表。
4. 检查冲突、新鲜度和权限。
5. 生成结构化 claim。
6. 证据验证器拒绝无证据的 Confirmed claim。
7. 再将 claim 转为自然语言或图表。
8. 对 Unknown 和 Recommendation 明确标识。
