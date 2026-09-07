---
name: elmos-semantic-navigation
description: 实现跳转定义、查找引用、实现列表、调用层级、类型层级以及页面/API/服务/数据双向追踪。用于代码阅读和问题定位。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: experience
  title_zh: 语义导航与跨层追踪
  batch: BATCH-03-code-reader-and-explanation
  owner: elmos-project-intelligence
---

# 语义导航与跨层追踪

## 目标

让用户从任意代码或业务节点快速追踪到上下游实现，并显示证据与不确定性。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Code Graph
- Project Intelligence Graph
- 当前 symbol/context
- 权限

## 必须输出

- definition/reference/call APIs
- 跨层导航 UI
- 导航路径
- 未解析候选

## 执行流程

1. 实现 Definition、References、Implementations、Type Hierarchy、Call Hierarchy 查询。
2. 实现页面→API→Service→Repository→Table 与反向路径。
3. 实现 Topic→Producer/Consumer、Config→Reader、Test→Target 的导航。
4. 为动态候选显示置信度和多个可能目标。
5. 支持路径限制、深度、边类型和 revision 过滤。
6. 记录导航性能与失败原因。

## 实施要求

- 查询结果必须分页并支持图过大保护。
- 候选边与确认边视觉区分。
- 跨语言 FFI、RPC 和生成代码需保留跳转桥。
- 导航结果可保存为阅读路径或分享链接。
- 结果必须检查节点和证据权限。

## 安全与可信度约束

- 不得隐藏解析歧义。
- 不得因图查询超时返回不完整结果却标记成功。
- 不得跨 revision 混合节点。

## 依赖技能

- `elmos-online-code-reader`
- `elmos-project-intelligence-graph`

## 预期交付物

- `semantic-navigation-api.yaml`
- `navigation-accuracy-report.md`

## 完成定义

- [ ] 基准项目主要语言导航准确率达到目标。
- [ ] 跨层路径可从页面追到数据表并返回证据。
- [ ] 大扇出查询有摘要和继续加载。
- [ ] 失效 symbol 链接有重定位或明确错误。
- [ ] 导航权限测试全部通过。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
