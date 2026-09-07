---
name: elmos-debug-sandbox-orchestration
description: 为在线调试创建一次性、可复现、最小权限的运行沙箱。用于 Runtime Profile、构建与启动、资源配额、网络和密钥策略、会话心跳、清理、生产环境禁用与紧急审批。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills and Claude Code. Requires an isolated debug runtime; production attach is denied by default.
metadata:
  version: 1.1.0
  category: debug-platform
  title_zh: 调试沙箱、运行环境与会话编排
  batch: BATCH-14-online-debug-and-learning
  owner: elmos-project-intelligence
---

# 调试沙箱、运行环境与会话编排

## 目标

让用户能够运行和调试项目，同时确保调试代码、表达式、依赖和测试数据无法逃逸到宿主机、其他租户或未授权网络。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个调试、学习、运行时或转换能力时，先调用 `elmos-insight-orchestrator`。
- 读取 `references/module-spec.md` 和 `docs/27-online-debug-learning.md` 后再修改代码。
- 不得把设计稿、协议桩、Mock Adapter、未运行的沙箱或手工截图标记为完成。
- 调试默认只允许固定 revision、非生产、一次性沙箱与脱敏数据；任何例外必须由策略和审计显式授权。

## 输入

- 固定 Project Revision
- 依赖锁文件与工具链镜像摘要
- Runtime Profile 与启动目标
- Debug Policy、数据集与 Secrets 引用

## 必须输出

- Ephemeral Debug Workspace
- Debug Target Lease
- Sandbox Attestation
- 清理与资源使用报告

## 执行流程

1. 定义语言/框架 Runtime Profile，并绑定构建命令、启动目标、端口、环境、adapter 和镜像摘要。
2. 创建非 Root、只读根文件系统、临时可写层、资源配额、进程限制和系统调用隔离的容器或微型虚拟机。
3. 实现 launch/attach 环境资格策略；生产进程默认不可暂停或附加。
4. 接入 Secrets Broker、短期凭证、合成/脱敏数据集和默认拒绝的出站网络策略。
5. 实现 provision→build→launch→heartbeat→terminate→cleanup→attest 全生命周期和超时回收。
6. 实现表达式/调试控制台策略：默认只读，副作用表达式仅在一次性环境经显式审批后执行。

## 实施要求

- 每个会话使用独立运行边界，禁止挂载宿主 Docker Socket 或跨租户共享可写卷。
- 同一 manifest、镜像摘要和输入数据应能重建等价调试环境。
- 生产 attach 默认拒绝；紧急模式需职责分离、到期授权、只读优先和完整审计。
- 会话终止后必须回收进程、端口、卷、凭据、网络策略和 adapter lease。
- 构建、依赖下载、表达式求值和网络访问均受配额、白名单与 kill switch 控制。

## 安全与可信度约束

- 禁止把真实长期凭据写入环境变量快照、日志、变量面板或 Replay Bundle。
- 调试数据集默认使用合成或脱敏副本，不直接连接生产数据库。
- 所有 cleanup 失败进入隔离队列，并阻止同一资源被重新分配。

## 依赖技能

- `elmos-reference-architecture`
- `elmos-security-threat-model`
- `elmos-deployment-private-cloud`
- `elmos-observability-slo`

## 预期交付物

- `services/debug-session-orchestrator`
- `workers/debug-sandbox-runner`
- `debug-sandbox-security-report.md`

## 完成定义

- [ ] 跨租户、宿主文件、Docker Socket、特权系统调用和未授权网络访问测试全部 fail closed。
- [ ] 会话结束后不存在残留进程、端口、凭据或可写工作区。
- [ ] 未获得 break-glass 授权时生产 attach 请求被拒绝并生成审计事件。
- [ ] Fork bomb、内存/磁盘耗尽、无限输出和网络滥用被配额与 kill switch 控制。
- [ ] 固定 manifest 的重复启动得到相同工具链、依赖和入口配置。

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
