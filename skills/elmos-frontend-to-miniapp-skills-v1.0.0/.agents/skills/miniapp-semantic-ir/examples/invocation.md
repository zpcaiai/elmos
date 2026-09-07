# 调用示例

## Codex

```text
$miniapp-semantic-ir 读取 runs/demo/conversion-request.json，执行任务 MAPP-011, MAPP-012。
保持源仓库只读；将输出写入 runs/demo/；先验证 Schema，再执行门禁。
遇到需要真实凭证、支付、上传、审核或发布时停止并报告 blocked。
```

## Claude Code

```text
/miniapp-semantic-ir runs/demo/conversion-request.json
```

## 预期回复摘要

```yaml
skill: miniapp-semantic-ir
task_ids: ['MAPP-011', 'MAPP-012']
status: passed | blocked | failed
artifacts:
  - path: <relative-path>
    sha256: <hash>
gate_results:
  - gate: <name>
    status: passed | failed | unknown
next_action: <next skill or approval>
```
