# Batch 66–80 略严苛测试策略

## 强度定位

这不是Smoke Test，也不是完整的第三方安全认证。它要求每个Source Skill至少一个真实成功路径与一个负向/故障路径，并对跨语言构建、契约、数据、并发、UI、Native、Shell、容器、IaC、CI/CD、供应链和Evidence执行统一门禁。

## 数量

- 195个Source Skills（PG223–PG417）
- 390个Source-specific Cases（每项2个）
- 60个Cross-cutting Cases
- 35个测试Skills
- 合计450个Case

## Gate

- P0=100%；普通P1>=98%；P2>=95%。
- 零容忍：Secret泄漏、越权、不可逆数据丢失、供应链/签名绕过、危险IaC Apply、伪Evidence。
- 未运行、Skipped、Flaky、Mock-only和陈旧Evidence不计Pass。
- Waiver不能覆盖零容忍Case，且必须有Owner、批准者、范围和过期时间。
