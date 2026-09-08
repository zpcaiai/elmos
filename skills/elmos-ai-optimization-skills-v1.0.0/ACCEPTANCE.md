# 宿主验收矩阵

以下定义尚未在实际Elmos执行。包内参考测试不自动更新它们。

| AC | Task | 必须满足 | 状态 |
|---|---|---|---|
|AO-AC-001|AO-T01|existing项有真实路径和源码证据。|not_run|
|AO-AC-002|AO-T01|只匹配文件名/设计文档不能标已实现。|not_run|
|AO-AC-003|AO-T02|基线配置和数据可复现。|not_run|
|AO-AC-004|AO-T02|不得同时默认启用所有候选技术。|not_run|
|AO-AC-005|AO-T03|公共请求不含自造可信权限，scope由host解析。|not_run|
|AO-AC-006|AO-T03|伪造tenant/approved和repo-snapshot混配均拒绝。|not_run|
|AO-AC-007|AO-T04|样例有qrels和版本、repo家族隔离holdout。|not_run|
|AO-AC-008|AO-T04|toy样例不能当客户资格或真实转换结果。|not_run|
|AO-AC-009|AO-T05|至少一个真实消费者可获取固定版本证据。|not_run|
|AO-AC-010|AO-T05|身份服务故障不得缓存兜底放行。|not_run|
|AO-AC-011|AO-T06|exact的LLM/Embedding/rerank调用均为0。|not_run|
|AO-AC-012|AO-T06|精确miss不偷换成相似方法，查询不注入引擎语法。|not_run|
|AO-AC-013|AO-T07|中文emoji/CRLF/BOM截断后范围与真实字节一致。|not_run|
|AO-AC-014|AO-T07|引用存在不等于引用支持结论。|not_run|
|AO-AC-015|AO-T08|同scope版本可复用，版本变化不误命中。|not_run|
|AO-AC-016|AO-T08|撤权和删除同时阻断cache、graph、检索和导出新读取。|not_run|
|AO-AC-017|AO-T09|入口到实际源码再到解释的闭环可复现。|not_run|
|AO-AC-018|AO-T09|关flag回安全旧路径，Mock不算完成。|not_run|
|AO-AC-019|AO-T10|选型有质量/latency/cost/运维对照。|not_run|
|AO-AC-020|AO-T10|无证据不得同时增加重复向量后端。|not_run|
|AO-AC-021|AO-T11|未变化内容复用，受影响依赖重建。|not_run|
|AO-AC-022|AO-T11|同blob不同配置不得盲目复用完整语义。|not_run|
|AO-AC-023|AO-T12|仅expected_head正确且完整代次可发布。|not_run|
|AO-AC-024|AO-T12|乱序不能复活删除内容，不混新旧代次。|not_run|
|AO-AC-025|AO-T13|同模型比较keyword/hybrid/graph增量。|not_run|
|AO-AC-026|AO-T13|ANN不足不放宽ACL，隐藏节点不泄漏后继。|not_run|
|AO-AC-027|AO-T14|达到预声明主目标/guardrails才开flag。|not_run|
|AO-AC-028|AO-T14|RRF不能标概率，退化时回滚。|not_run|
|AO-AC-029|AO-T15|返回typed状态且调用都经过原网关。|not_run|
|AO-AC-030|AO-T15|图DONE不写Run完成，不新增准入权威。|not_run|
|AO-AC-031|AO-T16|恢复校验权限、snapshot和图版本。|not_run|
|AO-AC-032|AO-T16|课程恢复不能给过期600秒资源续命。|not_run|
|AO-AC-033|AO-T17|无进展到上限就结构化停止。|not_run|
|AO-AC-034|AO-T17|不得改oracle/删失败测试/放宽容差。|not_run|
|AO-AC-035|AO-T18|同意图重试无第二动作，unknown先对账。|not_run|
|AO-AC-036|AO-T18|过期/撤权/旧generation/新intent沿旧批准都拒绝。|not_run|
|AO-AC-037|AO-T19|恢复不重复已提交动作且版本迁移明确。|not_run|
|AO-AC-038|AO-T19|InMemory和自制状态机不能当原生持久恢复证明。|not_run|
|AO-AC-039|AO-T20|验证适用路由/Session/Filter/事务/异常。|not_run|
|AO-AC-040|AO-T20|编译通过不能代替迁移行为验收。|not_run|
|AO-AC-041|AO-T21|实际源目标运行定位首个差异并有证据。|not_run|
|AO-AC-042|AO-T21|source不可用就明确说明，不能伪造双运行。|not_run|
|AO-AC-043|AO-T22|明确需求下产出可运行入口与测试。|not_run|
|AO-AC-044|AO-T22|相似模板不覆盖用户选择，不污染私有/holdout数据。|not_run|
|AO-AC-045|AO-T23|类型/NULL/时区/事务/routine副作用按先验oracle检查。|not_run|
|AO-AC-046|AO-T23|SQLite参考不得冒充其他数据库兼容性认证。|not_run|
|AO-AC-047|AO-T24|不能映射用户ACL时拒绝共享或独立授权绑定。|not_run|
|AO-AC-048|AO-T24|application token不自动具有任意用户权限。|not_run|
|AO-AC-049|AO-T25|真实实例返回权限/版本正确的来源。|not_run|
|AO-AC-050|AO-T25|不把raw RRF当概率，不复制私有语料为第二真相。|not_run|
|AO-AC-051|AO-T26|目标可实际导入/运行，调用账本唯一。|not_run|
|AO-AC-052|AO-T26|DSL导出不等于完整工程，未选目标不引依赖。|not_run|
|AO-AC-053|AO-T27|分层报告质量/延迟/成本及样本不确定性。|not_run|
|AO-AC-054|AO-T27|不删失败样例、不混冷暖、不事后调阈值。|not_run|
|AO-AC-055|AO-T28|启用能力的安全硬门禁均有实际证据。|not_run|
|AO-AC-056|AO-T28|安全失败不能用性能收益或waiver抵消。|not_run|
|AO-AC-057|AO-T29|关flag恢复安全路径且不重复副作用。|not_run|
|AO-AC-058|AO-T29|不删日志/账本假装撤销已发生动作。|not_run|
|AO-AC-059|AO-T30|本地检查至多ready_for_host_review，批准来自宿主。|not_run|
|AO-AC-060|AO-T30|缺证据/not_run/reference/tamper不可生产通过。|not_run|
