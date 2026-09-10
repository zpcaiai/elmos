# Synthetic schema examples only

所有demo-*、摘要、身份、证明绑定与证书对象仅用于JSON Schema/参考代码的示例，不是客户数据、实际工具摘要、外部审计签署或部署配置。临时Ed25519私钥只在生成/测试进程内存在，不交付私钥。示例signed-envelope即使验签，也只能指向演示report。真实trust root永远不能从这些文件读取。

auditor-config为未登记、已过期的PENDING_REVIEW示例；configs/ethen.example.yaml才是默认UNCONFIGURED配置模板。proof-obligation保持NOT_RUN；gate-decision显式DEMO_ONLY_NOT_A_CERTIFICATE。
