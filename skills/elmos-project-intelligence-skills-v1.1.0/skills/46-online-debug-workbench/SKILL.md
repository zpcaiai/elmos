---
name: elmos-online-debug-workbench
description: 在在线代码阅读器中加入安全、可恢复的调试体验。用于断点、单步、调用栈、线程、变量、Watch、表达式、调试输出、运行时间线以及代码—架构—流程—数据联动。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills and Claude Code. Requires an isolated debug runtime; production attach is denied by default.
metadata:
  version: 1.1.0
  category: debug-experience
  title_zh: 在线调试工作台
  batch: BATCH-14-online-debug-and-learning
  owner: elmos-project-intelligence
---

# 在线调试工作台

## 目标

让用户不用离开 Elmos 就能观察项目实际执行，并在固定 revision 和隔离数据环境中把每次暂停理解为可回源的项目知识。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个调试、学习、运行时或转换能力时，先调用 `elmos-insight-orchestrator`。
- 读取 `references/module-spec.md` 和 `docs/27-online-debug-learning.md` 后再修改代码。
- 不得把设计稿、协议桩、Mock Adapter、未运行的沙箱或手工截图标记为完成。
- 调试默认只允许固定 revision、非生产、一次性沙箱与脱敏数据；任何例外必须由策略和审计显式授权。

## 输入

- Project Revision、文件/符号/测试或流程入口
- Runtime Profile 与 Debug Target
- Adapter Capabilities
- 用户 Debug Policy 与学习模式

## 必须输出

- Browser Debug Session UI
- Breakpoints 与 Watches
- Runtime Timeline 与 Side-effect Overlay
- 可分享的调试深链与会话摘要

## 执行流程

1. 实现创建会话向导：revision、runtime profile、入口/测试/场景、数据集、学习模式和资源预算。
2. 在 Monaco 中实现行断点、条件断点、Logpoint、异常/函数/数据断点的能力感知 UI。
3. 实现 Continue、Pause、Step Over/Into/Out、Run to Cursor、Restart 和 Terminate 控制栏。
4. 实现 Thread、Call Stack、Scope、Variable、Watch、Evaluate、Module 和 Breakpoint 面板及懒加载。
5. 实现 Output、Log、HTTP/RPC、SQL、Cache、MQ、File I/O、Lock/Coroutine 与状态差异时间线。
6. 把当前 Frame、调用栈和副作用映射到 Code Graph、架构图、流程图、数据资产、测试和证据。

## 实施要求

- 所有调试状态、深链和会话摘要绑定固定 revision、runtime profile 和 adapter version。
- UI 只显示适配器声明且策略允许的命令；不使用伪按钮或静默失败。
- 变量和对象按需展开、限制深度/大小，并显示截断与脱敏状态。
- 浏览器刷新或短暂断线后可恢复 UI 状态，但不得重放有副作用命令。
- 用户权限被撤销、策略变化或会话到期时立即终止访问并清除浏览器缓存。

## 安全与可信度约束

- Debug Console 不是任意 Shell；命令与表达式必须通过策略引擎。
- 变量、日志、响应体和 SQL 参数在服务端脱敏后才发送浏览器。
- 禁止通过断点条件、Watch 或 Evaluate 绕过文件、网络、密钥和租户权限。

## 依赖技能

- `elmos-online-code-reader`
- `elmos-semantic-navigation`
- `elmos-debug-adapter-gateway`
- `elmos-debug-sandbox-orchestration`

## 预期交付物

- `apps/insight-web/src/modules/debugger`
- `services/debug-session-api`
- `online-debug-e2e-report.md`

## 完成定义

- [ ] 用户可从测试、方法或流程入口启动会话并完成断点、单步、变量查看和终止闭环。
- [ ] 当前 Frame 可准确跳转代码，并同步高亮所属模块、流程步骤和数据副作用。
- [ ] 网络、SQL、缓存、消息和文件副作用按时间排序且标注证据来源。
- [ ] 浏览器重连可恢复只读状态和面板，不重复执行上一条控制命令。
- [ ] 权限撤销后会话访问立即失效，敏感变量和本地缓存不可继续查看。

## 验证

1. 执行本模块的单元、协议合规、集成、E2E、沙箱逃逸、权限、恢复和性能测试。
2. 至少使用一个真实小型 fixture 项目完成“启动→断点→单步→变量→副作用→终止/回放”闭环。
3. 将需求、实现文件、测试、运行 revision、adapter/runtime 版本和证据写入追踪矩阵。
4. 运行：

```bash
python3 scripts/validate_skillpack.py --strict-jsonschema
python3 -m unittest discover -s tests -v
```

5. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
6. 对运行时不支持的能力、低置信度因果关系和不可复现外部依赖明确标注。
