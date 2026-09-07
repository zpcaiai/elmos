# Security and sandbox

## Threat model

测试输入可能包含恶意构建脚本、Prompt Injection、压缩炸弹、路径穿越、symlink、依赖混淆、秘密、PII、后门测试和资源耗尽。模型输出同样不可信。

## Required controls

- 每个 case 使用独立短生命周期 workspace/container/VM；
- rootless、只读基础层、无宿主 Docker socket；
- 默认断网，按域名/仓库/包 digest 临时放行；
- 不挂载生产凭据；测试 secret 短期、最小权限、运行后销毁；
- CPU/内存/PID/磁盘/时间限制；
- 禁止访问其他租户 workspace、cache、artifact 和 trace；
- 工具权限归属具体 execution environment，不使用 thread-global 权限；
- stdout/stderr/artifact 自动秘密和 PII 扫描；
- 构建产物、SBOM、依赖和证据签名。

## Security cases

横切矩阵包含 sandbox escape、path traversal、zip bomb、Prompt Injection、secret/PII、恶意 build、dependency confusion、typosquat、unsigned binary、跨租户泄漏、审批绕过和日志脱敏。

## Failure policy

安全控制无法建立时，case 状态必须是 `unavailable`/`blocked`，不得降级到宿主直接执行后宣称通过。
