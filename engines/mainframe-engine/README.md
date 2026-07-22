# ELMOS Mainframe Engine

Batch 19 的独立 Java 21 Worker。它管理主机资产、Copybook/COBOL 语义、JCL/CICS/IMS/Db2/VSAM 图、规则候选、现代化路径、语义等价和双跑切换。

默认端口为 `8093`。真实 z/OS 操作必须通过 Allowlist 与短期 Job Lease；仓库内所有外部适配器初始均为 `NOT_CONFIGURED`，生产写、任意 JCL 和控制面执行默认拒绝。
