---
name: elmos-debug-adapter-gateway
description: 建设统一调试适配器网关，规范化 DAP、浏览器调试协议和各语言原生调试器差异。用于会话代理、能力协商、断点/栈/变量事件转换、连接恢复和适配器合规测试。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills and Claude Code. Requires an isolated debug runtime; production attach is denied by default.
metadata:
  version: 1.1.0
  category: debug-platform
  title_zh: 调试适配器网关与能力协商
  batch: BATCH-14-online-debug-and-learning
  owner: elmos-project-intelligence
---

# 调试适配器网关与能力协商

## 目标

在不把某一语言调试器能力误认为所有运行时都支持的前提下，为 Elmos 提供版本化、可观测、可隔离的统一调试控制面。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个调试、学习、运行时或转换能力时，先调用 `elmos-insight-orchestrator`。
- 读取 `references/module-spec.md` 和 `docs/27-online-debug-learning.md` 后再修改代码。
- 不得把设计稿、协议桩、Mock Adapter、未运行的沙箱或手工截图标记为完成。
- 调试默认只允许固定 revision、非生产、一次性沙箱与脱敏数据；任何例外必须由策略和审计显式授权。

## 输入

- Project Revision 与语言/构建指纹
- Debug Target 与 Runtime Profile
- DAP/CDP/原生适配器配置
- 用户权限与 Debug Policy

## 必须输出

- Debug Adapter Registry
- 统一 Debug Session Protocol
- 能力矩阵与降级信息
- 适配器合规与兼容性报告

## 执行流程

1. 建立 JVM、Python、.NET、Node/TypeScript、Go、Rust/C++、PHP、Dart/Flutter、Swift/Objective-C 与 Browser 的适配器注册表和版本矩阵。
2. 实现 DAP Session Broker、请求/响应序列关联和 WebSocket 双向传输。
3. 实现 Browser/CDP Bridge、Source Map 解析与前端源文件 revision 绑定。
4. 实现适配器进程生命周期、健康检查、版本钉住、能力协商和优雅关闭。
5. 统一 Breakpoint、Thread、Stack、Scope、Variable、Evaluate、Output、Module 和 Termination 模型。
6. 实现背压、事件去重、断线重连、懒加载变量分页、超大对象截断和协议错误隔离。

## 实施要求

- 每个适配器必须声明实际支持的能力；UI 不得展示或承诺未支持的命令。
- 所有消息绑定 tenant、project、revision、debug_session 与单调递增序列。
- 源码映射必须固定到同一 Project Revision，禁止映射到漂移分支。
- 适配器崩溃、恶意消息或协议失序不得影响网关和其他租户会话。
- 适配器升级必须有兼容矩阵、灰度、回滚和会话版本钉住。

## 安全与可信度约束

- 适配器只能通过受控 IPC/网络与网关通信，不得直接访问控制面数据库。
- 协议日志默认只保存元数据和脱敏值，不保存任意变量原文。
- 所有 adapter binary/image 必须签名、固定摘要并通过供应链扫描。

## 依赖技能

- `elmos-reference-architecture`
- `elmos-multilanguage-parsing`
- `elmos-observability-slo`

## 预期交付物

- `services/debug-gateway`
- `debug-adapters/registry.yaml`
- `debug-adapter-conformance-report.md`

## 完成定义

- [ ] Java/Kotlin、Python、Node/TypeScript 和 .NET 四类 P0 适配器通过统一合规套件。
- [ ] 不受支持的断点、反向执行或内存能力会被明确禁用并显示原因。
- [ ] 网络短暂中断后会话能恢复，且不会重复执行调试命令。
- [ ] Source Map 能将前端暂停位置准确定位到固定 revision 的源代码。
- [ ] 畸形、超大或恶意适配器消息被隔离，其他会话不受影响。

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
