# 可执行参考内核：明确边界

`reference/`是一个离线、可测试、没有网络服务与生产签署权限的参考实现。
它用Python数据结构展示：可信配置与不可信report分离，签名与artifact摘要核验，基于义务集合的coverage，mandatory证据缺失阻断，Ethen签名身份/control domain分离，有限模型fencing与幂等。

签名采用Ed25519演示格式 `elmos-demo-envelope-v1`，签名覆盖固定规范化JSON字节。为避免跨语言数值规范化歧义，该格式拒绝float；小数用字符串。它不是DSSE实现，不是生产证书格式。
生产采用审定的in-toto statement与DSSE/Cosign/KMS集成，见schemas与signer skill；签署必须绑定artifact及policy/evidence root，并验证issuer/subject/audience/revocation。

参考内核可信假设：operator传入的policy/approval/trust store与clock是可信的；演示runner仍可能签署错误事实，故真实系统需要受控执行器、独立复跑、raw reports核验与外审。签名保证完整性/来源，不保证业务正确。

参考测试不证明下列事实：生产多租户DB RLS、网络隔离、外部effect exactly-once、完整API功能、所有语言转换、Spring transaction、真正Lean theorem、Ethen真实身份或客户验收。
示例fixtures使用合成数据和临时密钥，只验证kernel约束，不得进入正式信任根。
