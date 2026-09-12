# 多租户商业控制与交付产品化 Runbook

## Before enable
检查repo-map的复用/冲突、所有上游skill与feature flag。核对scope、policy、identity、native toolchain与预算；演示fixture不得用于生产。

## Verify
执行本skill的acceptance.yaml对应真实测试，并检查原始报告而非Agent总结。关联输出：AssuranceAPI, EntitlementPolicy, CustomerDeliveryBundle。
至少演练：客户验收人未批准；必须观察：不伪造customer acceptance。

## Incident
停止此模块新admission，保留run/step/epoch与证据，分类业务FAIL与基础设施INCONCLUSIVE；不要反复重试未知effect。
任何证据/权限/版本不匹配，阻断依赖此结论的签署并通知当前项目责任人。

## Rollback
关闭新feature path，保留旧profile路由；在途工作按原版本安全结束或取消。只对可安全补偿的effect进行补偿；不能删证据/改历史PASS/FAIL。

## Resume
重新验证当前权限和lease、工具链/contract/target/policy摘要及预算。生成新attempt，旧epoch不可提交。输出剩余NOT_RUN项。
