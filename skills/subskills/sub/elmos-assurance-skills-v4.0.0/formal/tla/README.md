# Bounded executor model — NOT_RUN

此模型是单step、最多3个epoch的候选TLA+/TLC模型。检查的是提交时租约epoch与有效状态，不表示提交后epoch永不更新。Cancel与Commit在模型中是原子动作；生产代码必须通过DB锁/CAS实现同一边界，否则模型不适用。

模型未包含数据库故障、超时、不可信权限、网络、真实外部副作用或liveness/fairness。TLC未在本次环境执行；java存在不等于TLC存在。选择审核过的tla2tools.jar、保存SHA256、运行 `java -cp <approved-tla2tools.jar> tlc2.TLC -config ExecutorFence.cfg ExecutorFence`，记录完整输出后才可写BOUNDED_MODEL_CHECKED。有限模型通过不是无限证明。
