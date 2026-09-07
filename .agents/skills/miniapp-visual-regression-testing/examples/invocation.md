# 调用示例

## Codex

```text
$miniapp-visual-regression-testing 读取 runs/demo/conversion-request.json，执行任务 MAPP-033, MAPP-034。
保持源仓库只读；将输出写入 runs/demo/；先验证 Schema，再执行门禁。
遇到需要真实凭证、支付、上传、审核或发布时停止并报告 blocked。
```

## Claude Code

```text
/miniapp-visual-regression-testing runs/demo/conversion-request.json
```

## 预期回复摘要

```yaml
skill: miniapp-visual-regression-testing
task_ids: ['MAPP-033', 'MAPP-034']
status: passed | blocked | failed
artifacts:
  - path: <relative-path>
    sha256: <hash>
gate_results:
  - gate: <name>
    status: passed | failed | unknown
next_action: <next skill or approval>
```
