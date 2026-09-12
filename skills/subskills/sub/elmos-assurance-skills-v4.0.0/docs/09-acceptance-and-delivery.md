# 从Skill完成到产品验收

## 完成定义

每个skill必须交付：实际集成代码；versioned契约；数据库变更（如有）；unit+negative+native integration；observability；权限；rollback；验收ID→原始运行证据映射。
只有文档/接口桩/mock可标 SPECIFIED/REFERENCE_TESTED，不是 IMPLEMENTED/NATIVE_VERIFIED。

## 四层验收

1. Package validation：结构、依赖DAG、schema/examples、文档必需文件。
2. Reference validation：本包小型内核、负例、demo实测。
3. Product integration：真实Elmos代码、实际工作流/DB/原生runner/API与UI。
4. Customer route acceptance：客户scope、隐藏集、真实Ethen/K8、上线回滚与有效期。

本次交付仅执行validation报告中明确列出的1/2；3/4不假冒完成。

## 必需系统反例

提交空suite/删接口/放宽精度；重放旧run证据；修改同commit产物；跨tenant引用证据；假审计身份；Builder用另一个key冒充外部；proof statement收窄前提；critical case跳过；重试掩盖flake；暂停预算却PASS；unknown external effect盲重试；取消后的旧workercommit；旧证书密钥被撤销仍显示有效。

## 交付清单

每batch报已有功能复用清单、代码diff摘要、所有测试命令/退出码、NOT_RUN理由、dependency/support matrix变化、风险/成本、可恢复checkpoint。没有实测wall-clock基线时报告unknown，不编造ETA。
