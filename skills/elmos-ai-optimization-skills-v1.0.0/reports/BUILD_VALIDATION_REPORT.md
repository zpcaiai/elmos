# 实际验证报告：Elmos AI Optimization v1.0.0

## 交付结论
**PACKAGE_VALIDATED；HOST_NOT_INTEGRATED；PRODUCTION_NOT_APPROVED。**
本次交付实施规格/Skills/契约/可执行参考和实际测试记录；没有修改或部署Elmos主仓库。

## 本次实际执行
| 检查 | 结果 | 证据 |
|---|---|---|
| Python参考/契约/负向/安装/扫描器测试 | 131项，失败0，错误0，跳过0 | reports/reference-tests.log / .json |
| SQLite FTS5检索样例 | 12查询；10有答案、2无答案；未返回越权/旧版本样例 | reports/retrieval-demo.json |
| TypeScript宿主端口严格类型检查 | PASS | reports/typescript-check.log / environment.json |
| 包Schema/示例/DAG/摘要校验 | PASS（最终由scripts/validate_package.py复核） | 14 schemas，14 examples，30 tasks，60 host definitions |
| 发布证据本地预检查 | EXPECTED BLOCK；退出码2 | reports/release-precheck.json |
| 原生LangGraph | not_run：optional native dependency missing | reports/langgraph-native.json |

测试覆盖：源码字节/路径、范围过滤、ACL epoch撤权、tombstone、精确零模型调用、真实FTS、合成向量/RRF/锚点去重、图预算、缓存篡改与版本、SQLite索引CAS/重开、稳定动作ID/审批绑定/旧worker拒绝/unknown对账、有限循环、查询builder、指标、证据篡改/越界、本地安装/卸载/改动保护。
SQLite持久模型不是生产索引CDC或实际远程动作执行器；自制有界状态机不是LangGraph原生实现。

## 仍未执行的宿主与原生资格
实际Elmos代码盘点、真实解释消费者E2E、模型语义/引用支持评测、生产多租户ABAC与注入红队、ES/pgvector原生查询计划、Dify实例与终端用户身份、LangGraph宿主持久恢复、云端沙箱、真实600秒/DAP、Spring与跨语言/SQL原生差分、性能负载与灰度均未完成。
60条宿主验收仍全部not_run。功能可按批准范围逐条资格，但不能通过减少原批准范围来伪造完整支持。

## 性能与成本口径
参考套件本次机器wall-clock=1.820秒；这是小型本地测试时长，不是Elmos任务ETA。
演示耗时包含按查询重建小型授权FTS索引，不能用于生产性能外推。
合成3维向量未调用Embedding，模型调用0；没有比较实际模型输出，也没有证明检索语义质量提升。
未执行模型和云资源成本记not_run/unknown，不把零模型调用误解为生产运行零成本。
本包没有宣传任何生产提速百分比或模型成功率提升。

## 重跑
```bash
python3 scripts/validate_package.py
python3 scripts/run_checks.py --output-dir /tmp/elmos-aiopt-reference-tests
python3 scripts/demo_retrieval.py --output /tmp/elmos-aiopt-demo.json
python3 scripts/release_gate.py reports/qualification.json
```
最后一条在宿主资格缺失时应返回2；这不是让用户绕过门禁。
最终SHA256仅保护内容一致性，不是签名、来源授权、语义正确性或生产审批。
