# 精确优化改造规格 ao.v1

## 0. 范围与原则
本包优化现有上下文获取、选择性Agent流程和验证方式，不重建软件工厂。
覆盖Spring旧项目现代化、仓库级跨语言转换、多语言项目生成、SQL方言/routine转换，以及Live Workbench。
质量、延迟、成本、可恢复性、安全与维护成本分别测量；不保证同时改善。
当前Elmos主仓库未检查。B0必须确定真实路径、owner、实现程度、编排语言和宿主契约。
不增加第9 Kernel或新Elmos路由；不复制权限、租户、财务账本或认证系统；不把框架名称当实施结果。

## 1. 宿主端口与所有权
下列是逻辑接口，不是必须创建的新微服务，也不是声称当前仓库存在的路径。

| 端口 | 输入→输出 | 边界 |
|---|---|---|
| ScopeResolver | 原session身份+选定版本→TrustedScope | 宿主鉴权；用户不能自行填写可信tenant/roles/approved |
| RevisionCatalog | 仓库/工作树→不可变snapshot及manifest | 脏工作区先固定快照；分支名不是证据版本 |
| EvidenceContextService | public query+host scope→EvidenceContext | 组织检索，不能授予权限或宣称语义已证明 |
| SymbolGraphPort | snapshot+anchor+预算→typed edges | 编译器/LSP/IR优先；候选边不同于运行观测 |
| SearchProjectionPort | scope+typed plan→候选ID与方法信息 | ES/PG可替换；不作为业务真相 |
| ModelGateway | finalized model-specific plan+预算→typed output | 原模型路由、费用、隐私、审计不变 |
| AgentSubflowPort | goal/evidence/versioned state→有界状态 | 局部教学/修复，不写Run完成 |
| ExecutionGateway | intent+host capability→committed receipt或unknown | 唯一动作入口；授权、围栏、幂等、对账 |
| AcceptanceService | exact revisions+sealed evidence→独立decision ref | 原K8/认证边界，不由生成Agent自签 |

公共请求包含request_id、query、mode(auto/exact/lexical/hybrid)、selector、snapshot_refs、top_k、context_token_budget。
不接受客户端自报的trusted tenant、授权仓库列表、role、approved、安全上下文或任意索引名；未知字段拒绝。
TrustedScope由host生成，包含tenant、principal、ACL epoch、host安全上下文引用/期限及精确(repository,snapshot,generation)集合。
多仓库必须按tuple配对，禁止用repository IN与snapshot IN导致范围笛卡尔积。
source/target对照分别授权、分别绑定版本；不得悄悄扩大普通阅读scope。
文档/路径级ABAC存在时必须映射宿主分区，repo级参考授权不代表已实现所有生产权限。

## 2. SourceAnchor、事实与引用
内部anchor=repository+snapshot+generation+canonical relative path+blob SHA256+symbol+[start_byte,end_byte)。
规范POSIX相对路径拒绝绝对路径、..、反斜杠、NUL、盘符及非规范路径。读取正文核对CAS摘要。
UTF-8字节边界与LSP/Monaco/DAP下标、列编码分别转换；中文、emoji、CRLF、BOM、空文件、无末尾换行加入测试。
编辑生成新snapshot；旧证据读旧字节，不把新文件的相同行号冒充旧证据。
事实分verified-static/runtime-observed/inferred/unknown/recommended。运行结论必须有实际run/session/event/stop epoch引用。
引用存在、引用字节正确、引用是否支持句子是三个独立问题；模型摘要不能成为sole source。
注释/README/RAG文档/工具结果均为数据，不能提升为指令、tool authority或认证。
输出HTML/Markdown安全渲染，不将敏感信息放到日志、URL或trace标签。

## 3. 三条服务路径
### 即时精确路径
确知path/symbol/anchor走已有文件/符号/字符串索引。模型、Embedding、rerank调用默认均为0。
path与symbol同时给定取交集；未命中明确not_found/insufficient_evidence，不能返回相似函数假装精确命中。
旧anchor或未知版本返回STALE_REVISION，不从latest版本自动补齐。
### 固定问答路径
授权→快照绑定→规范化查询→精确/关键词候选→必要typed graph扩展→按需重排→上下文打包→一次生成→Schema/引用校验。
原始标识符保留；query rewrite默认关闭。所有扩展受deadline、candidate、depth、fanout预算控制。
### 条件混合路径
仅对语义意图查询且B2已批准启用：关键词和向量并行→source anchor去重→RRF融合→可选rerank→打包。
RRF是排序分数不是概率。Embedding模型/维度/归一化/空间不兼容时拒绝，不能混合旧新向量空间。
每个召回分支都携带相同可信scope；不能全库TopK再删除越权结果。后端优先只返回ID，正文hydration前再次鉴权。
ANN过滤后不足K时有界扩大候选、迭代扫描或小集合精确回退；不能放宽ACL/换版本补满。
搜索后端失败，只有权限及版本仍能验证时才降级关键词并标degraded；Auth失败绝不兜底放行。

## 4. 代码图谱与语义单元
按方法/类型/路由/配置段/SQL routine/测试/ADR索引，不按固定字数机械切割全部源码。
原文用于证据，编译器/IR结构用于语义关系，自然语言摘要只辅助意图召回。
命中函数后按需获取直接类型、配置、调用者/被调用者和相关测试，避免永久拼巨大块。
图边标明静态候选、配置解析、编译器确认、运行观测、分析推断；无传播上下文的异步链路标缺口。
BFS/路径查询限制depth/nodes/fanout；未授权节点不能当穿越通道，不泄漏被过滤节点名称或后继。
不要让模型从源码重新猜一张图来替代已有Semantic IR；普通GraphRAG不等同编译器调用图。

## 5. 增量索引、发布与删除
复用key至少包含tenant partition、blob、parser/schema、toolchain、dependency/config指纹；embedding另含model/dimension/chunk策略。
同blob不同编译配置可能有不同符号关系，不能只按文件hash复用整个语义图。
新generation先BUILDING→完整性/引用/覆盖/权限/embedding空间校验→VALIDATED→expected_old_generation CAS发布。
每个请求固定generation直至结束；失败代次不能成为read alias；保留旧代次证据供审计。
业务revision/outbox同数据库事务提交，搜索投影异步幂等消费，按source sequence处理乱序，删除留tombstone。
不假装PostgreSQL与ES之间有原子事务；用outbox、manifest、幂等、对账保证可恢复。
撤权/删除先同步阻断访问（epoch/tombstone），再异步物理清除关键词、向量、摘要、图边、缓存和导出。
已发送到浏览器的文字无法使用户“失忆”；新访问必须撤销，客户端缓存与备份保留策略单独说明。

## 6. 打包、缓存与数据控制
生产使用已选模型的实际tokenizer，预留系统指令/问题/工具/输出预算；参考demo的bytes不能当tokens。
优先直接实现/入口证据、必要类型/配置和测试，再加背景；截断显式标注并修正实际传入范围，不能切坏UTF-8。
缓存key含tenant/principal或严格等价授权分区、scope/ACL epoch、snapshot tuple、generation、query/selector、retrieval/embedding/reranker/tokenizer/prompt/model/redaction版本及deletion epoch。
每次命中仍鉴权。模型答案语义缓存默认关闭，当前调试状态/修复建议禁止仅凭问题相似复用。
分开统计应用缓存、解析/向量缓存、provider prompt cache、构建缓存，不能混成一个命中率。
客户私有源码、评测holdout、未批准经验不得进入跨租户共享记忆。

## 7. LangGraph/Agentic设计
只为分支、有限反复取证、人工等待和受控修复引入图；单次问答、编译、exact定位和DAP不绕图。
首两条图evidence_tutor、bounded_repair；conversion_differential在真实差分接口存在后增加。
Graph state只存goal、refs、hypotheses、pending intent、budget、schema/graph/prompt/tool版本；大正文CAS，业务账本PG。
旧暂停会话按原graph版本恢复或显式迁移；不能随意更名节点/删除状态字段后声称恢复兼容。
Graph checkpoint是Agent状态，不是目标进程/VM快照；interrupt不是DAP断点。
宿主持久编排负责Job/Run、生命周期、资源deadline、取消与跨步骤等待；图负责局部决策，一个逻辑动作只有一个retry owner。
模型和外部请求在Worker/Activity边界执行，不塞进需确定性重放的Workflow代码。
预算包含rounds、tool/model calls、输出、并行度与deadline；重复失败指纹无进展达到上限就NO_PROGRESS。
第一版单协调者＋按需技能，只有独立read/write-set和明确收益才增加多Agent并行；冲突写必须隔离/合并校验。

## 8. 动作、审批与副作用
ActionIntent绑定tenant/run/logical_step、base_revision、patch或命令摘要、requested capabilities、budget及verification plan。
模型仅提出意图；host检查当前身份、审批范围、policy、lease、permission epoch、executor generation。
Graph内approved=true或thread_id不是授权。改变补丁/参数/版本即新intent，旧审批不可沿用。
action_id绑定逻辑意图，排除retry attempt和generation；不能每次重试生成新ID绕幂等。
PROPOSED→DISPATCHED→SUCCEEDED/FAILED；结果不明进入UNKNOWN_RESULT，先查执行器receipt和工作区状态，再由host对账提交。
恢复不能盲重发创建沙箱、应用补丁、计费、step/continue/evaluate。旧generation结果拒绝；新host可核验旧receipt完成对账，不重新执行旧动作。
Result Interception→校验/脱敏/授权→Commit→模型/消费者；未提交结果不能发布。
CANDIDATE_READY仍需独立验收。不得改变oracle、删除失败测试、放宽容差或把图结束当E0–E5证书。

## 9. 业务消费者
### Live Workbench
行级解释接EvidenceContext；模块/架构分析接typed graph；Source/IR/Target映射来自转换器而非相似度猜测。
课程可等待回答/恢复notes；原600秒资源已到期，只能恢复历史学习状态。再次执行必须新租约。
正常预览通过交付manifest、预构建/干净预热和最小业务依赖闭包加速；异常才进入诊断图。
DAP基础控制、stop epoch、句柄失效、原3槽和清理器保持原逻辑。
### Spring现代化
规则按源/目标框架、版本、配置和前提筛选；用真实业务slice验证路由、绑定、Session、Filter顺序、事务、异常、安全与视图。
编译通过不是迁移通过；必要兼容例外须明确记录。
### 仓库跨语言转换
IR和确定性规则优先；RAG提供候选案例，Agent选择边界实验与首差异定位。
事先批准null、整数、decimal、时间时区、集合顺序、异常、协程/资源、事务的归一化规则。
无法运行source时标source-unavailable并保留静态证据，禁止捏造双运行。场景一致不等于全仓等价。
### 多语言生成
先检索合格模板/组件的许可、依赖、版本、验收，再契约驱动生成；明确用户技术选择不得被相似模板覆盖。
生成阶段同时产出可运行manifest、源码锚点、测试与限制，不到预览点击后才猜入口。
### SQL方言与routine
解析器/IR、方言版本规则优先；检索类型、NULL、排序、时区、事务及副作用案例。
在真实源目标数据库执行预先定义的差分；SQLite参考不能冒充Oracle/PG/SQL Server资格。
### Skills与经验库
条目含环境前提、版本、修改摘要、真实测试/receipt、known counterexample、批准/过期/撤销条件。
先资格/兼容/权限筛选，再相似检索；成功样例与失败教训分开，不能把模型自评写成verified经验。

## 10. Dify/LangChain/存储选型
LangChain是可选集成层；复用ModelGateway/ToolGateway和原费用审计，Java控制面不为框架迁到Python。
ES或pgvector依据已有设施、全文/过滤/向量负载和实测成本选择；无独立扩缩容证据不同时维护重复向量后端。
ES需专门设计keyword路径/符号/异常字段与text/标识符/中文分析；原生功能与订阅版本锁定后核验。
Dify适合可视化业务流程和客户生成目标；优先External Knowledge API调用共享EvidenceContext，不复制私有源码为第二真相。
application token不能自动代表最终用户。缺少终端身份时用独立授权knowledge binding、可信host网关或拒绝共享接入。
score threshold必须绑定定义好的归一化profile，不把RRF塞入0–1概率阈值。
DSL导出不是完整可执行项目；需要插件/知识库/环境/Secret依赖清单与目标运行验收。
Dify多租户与品牌附加许可、模型数据策略、ES功能许可在选定版本上线前核验；本包不替代法律审查。

## 11. 质量、性能、成本评测
对照A当前→B精确/关键词→C混合→D图谱/重排→E局部Agent，逐层判断增量收益。
固定revision、dataset、模型、硬件/并发、授权选择性、冷暖和价格版本；成对交错执行，避免先后缓存偏差。
按repo家族拆分开发/调优/holdout；重复运行不是独立样本，不得将holdout答案沉淀后重新评测。
测Recall@k/MRR/nDCG、引用字节和支持率、业务验收、无依据结论、正确拒答、安全泄漏、p50/p95/TTFT/整任务时间。
无答案问题单列，不能把空qrels直接当召回0/1；失败/超时保留在分母并报告censoring及失败率。
单位合格任务成本=(所有尝试模型/检索/执行/存储成本+索引摊销)/独立验收通过任务数；通过0时undefined不写0。
分语言/规模/权限过滤/任务类型报告及repo聚类置信区间。quality noninferiority、主目标最小改善、latency/cost guardrails及安全同时检查。
policies/optimization.yaml中的数值只是待B0批准初始提案，不是已测服务承诺；不得事后改阈值来通过。
本地小fixture只验证算法/流程，不支持生产性能或模型能力宣传。

## 12. 错误、灰度与发布
错误包括UNAUTHORIZED、ACL_STALE、REVISION_UNAVAILABLE、INDEX_NOT_READY、EMBEDDING_SPACE_MISMATCH、BUDGET_EXHAUSTED、INSUFFICIENT_EVIDENCE、DEPENDENCY_UNAVAILABLE、UNKNOWN_RESULT、FENCED、CANCELLED。
错误不返回越权资源名；read的429/503可有界退避，401/403不放松权限，unknown写只对账。
Trace记录scope-safe请求/run/step/action、代次、阶段耗时、候选/截断、调用和成本；不默认把源码/Secret写标签。
feature flag默认关闭；shadow只读且受预算，不重复产生写动作；灰度scope由host批准。
回滚flag/读路径/index alias/graph版本但保留新证据。不能删日志假装撤销已发生副作用。
数据库变更走expand→backfill/兼容验证→switch，不提供假定宿主表名的自动DDL。
本地release_gate只核验证据缺项/摘要，不验签、不裁定语义、不授予生产；原K8/发布权威保留。
条件功能未启用不阻挡B1；已启用则对应资格必需。不得缩减分母或暗改enabled scope来伪造全支持。
