# 使用示例

## Codex

```text
$elmos-git-pr-automation 在当前 Elmos 仓库实施本技能。先读取 references/module-spec.md，检查现有实现，然后完成代码、测试、文档和验收证据。
```

## Claude Code

```text
/elmos-git-pr-automation 检查当前实现与模块规格差距，直接完成最高优先级缺口，并运行相关测试。
```

## 验收调用

```text
使用 elmos-git-pr-automation 只做验收：根据 AC 与任务追踪矩阵检查真实实现，禁止把 TODO、mock 或未运行测试视为完成。
```
