# Delivery boundaries and acceptance ownership

本包交付完整实现契约与参考内核，不代表34个生产模块都已在Elmos仓库实现。本文与VALIDATION_REPORT共同构成完成边界。

**已实现并可本地测试**：finite Assertion IR、schema/身份/摘要/签名证据核验、门禁参考逻辑、覆盖/冒烟集合选择、类型化比较、预算/租约本地模型、SQLite反例、包校验与显式无覆盖安装器。

**需要接入真实仓库实现**：接口静态/动态采集器、真实编译和测试adapter、数据库差分、Spring行为记录器、代码跨语言前后运行、客户测试数据、生产状态持久化、真实API/UI/IdP/KMS、Ethen实际身份签署、全量供应链锁定与部署演练。

**候选但未执行**：PostgreSQL DDL、Lean示例、TLC模型、四条native Golden Routes。Python里带有proof_checks字段的合成fixture只测试门禁消费该报告的逻辑，绝非Lean证明；Ed25519临时签名只测试数据真实性机制，绝非真实Ethen授权。

**不承诺**：任意项目/任意语言组合全功能穷举、99.99%真实业务正确率、付费保过、零风险上线、ISO/监管认可证书、外部副作用无条件exactly-once。

安装器信任正在操作本地工作区的用户；使用互斥lock防止并发安装，拒绝已存在目录和符号链接，但不充当对具备同一操作系统账号写权限的恶意进程的沙箱。迁移脚本必须由管理员在隔离数据库验证，再接入正式迁移系统，不能直接通过Agent对生产库执行。
