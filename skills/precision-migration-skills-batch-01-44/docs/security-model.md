# Security Model

执行客户代码和AI生成代码时默认：无外网、非root、只读基础镜像、临时工作区、资源限额、最小Secret作用域、无宿主Docker Socket、完整审计。高风险任务使用轻量VM或完整VM。
