# 执行安全、可靠性与运维

## 不可信输入

源码、构建脚本、测试、proof、OpenAPI external $ref、归档、DB dump、日志都视为不可信。禁止通过prompt或repo文件提升权限。
解压校验path traversal/symlink/压缩炸弹/绝对路径；解析器限depth/bytes/time；外部引用默认离线禁用，按allowlist resolver获取后固定hash，防SSRF/元数据地址/DNS rebinding。

## Runner

生产用现有安全隔离方案，普通容器不自动等于足够的敌对代码沙箱。按风险采用microVM/强化隔离；禁止host docker socket、hostPath、privileged、root凭据；限制syscalls、CPU/内存/PID/磁盘/egress。构建取依赖与测试执行分阶段，依赖mirror审批锁定，测试默认无公网。
旧Spring runtime放隔离lane，不把过时服务暴露公网。DB credentials和测试数据按scenario划分，执行销毁/TTL并记录清理证据。

## Workflow

现有durable workflow为首选，不为接入再强制引入Temporal/LangGraph。引擎需要：持久状态、可重放history、租约/epoch、取消、超时、版本隔离、幂等与outbox。
Control plane: admit/reserve预算与3并发名额→持久plan→dispatch；worker仅可执行lease内步骤。
结果进入Result Interception，检查schema/authority/epoch/subject/provenance后原子commit。旧worker的迟到结果拒绝且留审计。

## 预算与费用

预留≠消费；每次attempt实际CPU秒、DB秒、token和供应商usage按唯一计费键入账。超时usage未知标记pending reconciliation，不计作0。
重试消耗原任务retry预算且独立usage记录；同一真实attempt重复回执不得双记。退款/纠错用反向ledger，不删历史。
Ethen有独立成本中心，不因Builder预算不足跳过Ethen。未知残余费用保守留reservations。

## 可观测性

trace: tenant(受控内部)、project/run/step/attempt、revision hash、worker epoch、model plan、oracle/checker版本。默认不记录源码/提示词/测试真实PII。
指标：queue wait、各stage wall-clock、mandatory NOT_RUN、coverage debt、critical survivors、evidence rejection、audit waiting、false-pass calibration、cache hit、cost per certified artifact。
告警：签署绕过=page；cross-tenant访问=page；证据seal失败=block；deadline和预算耗尽=可见暂停。

## 灾难与演练

故障矩阵包括：worker启动前/副作用后/commit前崩溃、重复dispatch、消息乱序、DB failover、对象存储不可用、签署服务故障、时钟偏差、lease吊销、租户噪声、KMS轮换。
Backup/restore必须恢复run状态与证据hash一致，不能恢复已吊销证书为有效。RPO/RTO按真实环境实测批准；不在包中编造已达到指标。

## 数据保留

客户源码不进入跨租户cache或训练语料。跨项目规则可以复用抽象结构，但需provenance/授权/IP扫描，禁止重用客户机密片段。
WORM/证据保留与客户删除策略存在冲突时，以合同和合法授权的分层保留策略解决；脱敏摘要并不总等于匿名数据。正式政策须由责任人批准。
