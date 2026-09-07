# Prompt Contract: Mismatch Repair

## Inputs

- one root-cause group
- first divergence trace
- legacy/target observations
- semantic source map
- current target source excerpts
- semantic invariants
- risk and patch budget
- affected tests

## Output

```yaml
hypothesis:
evidenceRefs:
minimalPatch:
  files:
  operations:
newFalsifiableTest:
expectedObservationChange:
unaffectedContracts:
rollback:
confidence:
stopIf:
```

## Rules

1. 一次只处理一个 root cause。
2. 先写可证伪测试，再写 patch。
3. 不得修改 source baseline、normalizer 或删除测试以制造通过。
4. patch 超预算时停止并请求 planner 重切 transformation unit。
5. critical security/transaction/data changes 必须进入审批门。
