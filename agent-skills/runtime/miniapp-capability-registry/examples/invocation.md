# 调用示例

## Codex

```text
$miniapp-capability-registry 读取 runs/demo/conversion-request.json，执行任务 MAPP-013, MAPP-014。
保持源仓库只读；将输出写入 runs/demo/；先验证 Schema，再执行门禁。
遇到需要真实凭证、支付、上传、审核或发布时停止并报告 blocked。
```

## Claude Code

```text
/miniapp-capability-registry runs/demo/conversion-request.json
```

## 预期回复摘要

```yaml
skill: miniapp-capability-registry
task_ids: ['MAPP-013', 'MAPP-014']
status: passed | blocked | failed
artifacts:
  - path: <relative-path>
    sha256: <hash>
gate_results:
  - gate: <name>
    status: passed | failed | unknown
next_action: <next skill or approval>
```
