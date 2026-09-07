# Batch 17 Vertical Solution Factory acceptance checklist

Repository implementation does not close field acceptance. Every row remains `NOT_RUN` until the named external system of record supplies current, authorized, version-bound evidence.

| Skill | Gate | Capability | Authoritative acceptance | Field status |
| --- | --- | --- | --- | --- |
| 593 `vertical-solution-factory-orchestrator` | V17-A | 组织行业研究、领域模型、监管控制、Recipe、测试、产品打包和渠道复制。 | 行业版本有完整Roadmap； 领域、监管和技术工作流互相连接； Design Partner参与； 产品化和定制边界清楚； 行业资产可版本化； 交付和渠道可以复用。 -- | `NOT_RUN` |
| 594 `vertical-solution-pack-registry` | V17-A | 登记VSP、地区Overlay、客户Extension和依赖关系。 | 所有行业资产可查询； 版本和兼容性清晰； 私有资产隔离； 地区Overlay组合正确； 更新和回滚可执行； Marketplace可引用同一注册表。 -- | `NOT_RUN` |
| 595 `industry-domain-meta-model-builder` | V17-A | 定义跨行业通用的领域元模型，使行业实体能够映射到UIR、API、数据、事件和控制。 | 行业实体和状态可查询； 领域关系可生成图谱； 数据、API和事件可关联； 控制可绑定实体和动作； 迁移差异可用行业语言表达； 模型支持客户扩展。 -- | `NOT_RUN` |
| 596 `industry-terminology-code-set-and-semantic-governor` | V17-A | 管理行业术语、枚举、Code Set、标识规则和语义版本。 | 行业术语一致； Code迁移可验证； 多语言显示不改变业务语义； 未知值不造成数据丢失； 历史版本可读取； 文档、API和测试使用同一术语。 -- | `NOT_RUN` |
| 597 `regulatory-control-model-builder` | V17-A | 把行业标准、监管条款、合同义务和客户政策转换为统一Control Model。 | 监管要求可机器查询； Control关联代码和配置； Control关联测试和证据； 地区差异可覆盖； 审计Gap可识别； 变更可追踪。 -- | `NOT_RUN` |
| 598 `jurisdiction-regulatory-overlay-manager` | V17-A | 把行业基础包与国家、地区、监管机构及客户义务组合。 | 每个Deployment有适用Overlay； 控制冲突可发现； 数据驻留和保留正确； 区域报告可生成； 监管更新可影响客户； 商业承诺与适用范围一致。 -- | `NOT_RUN` |
| 599 `control-code-test-evidence-crosswalk` | V17-A | 建立监管控制到架构、代码、配置、测试、运行证据和Owner的完整Crosswalk。 | Mandatory Control有Crosswalk； Evidence可自动采集； 审计人员可钻取； 失效控制可发现； 责任人明确； 合规包可自动生成。 -- | `NOT_RUN` |
| 600 `industry-data-classification-and-residency-manager` | V17-A | 定义行业数据类型、敏感度、访问、驻留、保留和脱敏规则。 | 核心数据分类覆盖100%； 权限和Encryption与分类一致； 模型路由符合数据政策； Retention可自动执行； 脱敏保持业务引用； Data Flow可导出。 -- | `NOT_RUN` |
| 601 `industry-identity-role-and-authorization-model` | V17-A | 定义行业Actor、职责分离、资源授权、紧急权限和委托。 | 行业角色完整； 高风险操作职责分离； Emergency流程有效； 跨机构访问受控； Agent与Human权限一致； 权限证据可审计。 -- | `NOT_RUN` |
| 602 `industry-workflow-state-machine-and-invariant-builder` | V17-A | 建立行业关键流程、状态转换、时间约束和Invariant。 | 关键流程有状态机； 非法转换可检测； Invariant可自动验证； 迁移前后状态可映射； 补偿路径完整； 生产监控可引用Invariant。 -- | `NOT_RUN` |
| 603 `industry-event-api-and-integration-model` | V17-A | 定义行业API、事件、命令、消息和外部系统边界。 | 行业集成边界完整； Schema兼容可验证； 消息副作用可比较； 外部调用证据可采集； Recipe可生成Adapter； Partner可获得标准接口包。 -- | `NOT_RUN` |
| 604 `industry-recipe-sdk` | V17-C | 为行业专家和工程师提供开发领域Recipe、Validator、Collector和Adapter的SDK。 | 行业Recipe开发标准化； Recipe可测试和签名； 领域和Control绑定； Marketplace可发布； 伙伴可在Sandbox开发； 共享内核无需Fork。 -- | `NOT_RUN` |
| 605 `industry-evaluation-golden-and-test-corpus` | V17-D | 建立行业行为等价、合规、安全、韧性和边界测试语料。 | 关键Invariant覆盖； 正常、异常和攻击路径完整； Source/Target可双运行； 事故语料可复现； 伙伴交付使用同一语料； 商业认证引用评测结果。 -- | `NOT_RUN` |
| 606 `industry-reference-architecture-builder` | V17-E | 定义可组合、可替换的行业目标架构，而不是固定单一厂商方案。 | 客户可选择适合Profile； 架构满足行业控制； 组件边界清晰； 迁移路径完整； Partner可按模板交付； Architecture Decision可追踪。 -- | `NOT_RUN` |
| 607 `industry-deployment-isolation-profile-manager` | V17-E | 为行业定义默认部署、隔离、边缘、离线和高可用要求。 | 行业默认部署可用； 隔离满足风险； 网络和数据流明确； HA/DR目标可配置； 成本可估算； POC和Production Profile分开。 -- | `NOT_RUN` |
| 608 `industry-slo-telemetry-and-dashboard-manager` | V17-E | 定义行业关键SLI、SLO、业务指标和监管证据Dashboard。 | 关键业务旅程有SLI； Control Evidence可查询； SLO可自动计算； Alert和Runbook完整； 行业管理层可理解； 迁移前后可比较。 -- | `NOT_RUN` |
| 609 `industry-risk-security-and-safety-case-manager` | V17-E | 汇总领域风险、控制、测试、残余风险和批准，形成行业Safety或Assurance Case。 | 高风险行业有Assurance Case； Claim和证据一致； 限制明确； 风险获得有权人员批准； 审计和客户可复核； 上线决策有行业依据。 -- | `NOT_RUN` |
| 610 `vertical-product-packaging-and-entitlement-manager` | V17-E | 把行业能力打包为SKU、模块、Entitlement和部署Edition。 | 行业能力可独立销售； Entitlement自动执行； 版本和地区正确； 套餐升级平滑； 成本和毛利可计算； 合同与部署一致。 -- | `NOT_RUN` |
| 611 `vertical-pricing-roi-and-business-case-manager` | V17-E | 建立行业特定定价、价值模型和ROI模板。 | 行业报价可标准生成； ROI符合客户语言； 成本和风险透明； 毛利可管理； 不同Segment可区分； 价值可在项目后验证。 -- | `NOT_RUN` |
| 612 `vertical-solution-lifecycle-and-compatibility-governor` | V17-E | 管理行业标准、控制、Recipe、架构、评测和商业版本生命周期。 | 行业版本持续更新； 兼容性影响可查； 客户升级可计划； 监管变化及时处理； 资产维护责任清晰； 无永久过时Pack。 -- | `NOT_RUN` |
| 613 `finance-domain-model` | V17-E | finance domain model | Ledger与可修改业务表分开； 金额使用明确Decimal； 币种和精度显式； Value Date、Trade Date和Posting Date分开； Reversal不能删除原交易； 外部Transaction ID稳定； 客户私有产品模型通过Extension扩展。 -- | `NOT_RUN` |
| 614 `finance-ledger-transaction-and-consistency-control` | V17-E | finance ledger transaction and consistency control | 不能以最终余额相同代替交易轨迹一致； 不删除原账务记录； Retry不得重复记账； 并发余额更新需验证； Batch结算需保留Checkpoint； 时间和时区边界需测试； 交易迁移需业务和财务共同验收。 -- | `NOT_RUN` |
| 615 `finance-regulatory-audit-and-resilience-pack` | V17-E | finance regulatory audit and resilience pack | 监管Overlay按机构类型和地区配置； 不宣称VSP自动实现监管合规； Card数据边界单独定义； 审计证据绑定生产版本； 重大业务服务定义中断容忍度； 第三方和模型服务纳入韧性； 未解决财务差异阻止Cutover。 -- | `NOT_RUN` |
| 616 `finance-migration-recipe-pack` | V17-E | finance migration recipe pack | 财务计算Recipe需Golden； Interest和Fee不可仅靠模型生成； Batch重启点必须保持； Legacy Encoding明确； 外部清算边界使用Adapter； 业务规则有Owner； Agent Patch需增强审批。 -- | `NOT_RUN` |
| 617 `finance-evaluation-and-test-corpus` | V17-E | finance evaluation and test corpus | Authoritative hard rules apply. | `NOT_RUN` |
| 618 `finance-reference-architecture` | V17-E | finance reference architecture | Authoritative hard rules apply. | `NOT_RUN` |
| 619 `finance-delivery-and-channel-pack` | V17-E | finance delivery and channel pack | Authoritative hard rules apply. | `NOT_RUN` |
| 620 `manufacturing-domain-model` | V17-E | manufacturing domain model | Authoritative hard rules apply. | `NOT_RUN` |
| 621 `ot-device-and-real-time-boundary-model` | V17-E | ot device and real time boundary model | 普通Cloud Retry不能直接用于设备控制； 设备写入需显式授权； 时间戳来源保留； Edge断连需定义； 旧协议通过Adapter隔离； 安全控制与业务分析分离； Agent不得直接越过Safety PLC。 -- | `NOT_RUN` |
| 622 `manufacturing-security-and-safety-control-pack` | V17-E | manufacturing security and safety control pack | OT安全不能直接复制IT默认策略； 生产可用性和安全共同评估； Remote Access短期授权； 关键设备升级需维护窗口； 不允许自动重启关键控制器； Safety Case与Cybersecurity Case关联； 设备证书和生命周期纳入。 -- | `NOT_RUN` |
| 623 `manufacturing-migration-recipe-pack` | V17-E | manufacturing migration recipe pack | Tag地址与业务名称分开； Alarm Priority和Ack语义保持； Recipe版本不可覆盖； 设备写入默认Disabled； Edge Store-and-forward可恢复； Vendor SDK封装在Compatibility Boundary； Factory Acceptance Test必须支持。 -- | `NOT_RUN` |
| 624 `manufacturing-simulation-hil-and-validation-corpus` | V17-E | manufacturing simulation hil and validation corpus | Authoritative hard rules apply. | `NOT_RUN` |
| 625 `manufacturing-reference-architecture` | V17-E | manufacturing reference architecture | Authoritative hard rules apply. | `NOT_RUN` |
| 626 `manufacturing-delivery-and-channel-pack` | V17-E | manufacturing delivery and channel pack | Authoritative hard rules apply. | `NOT_RUN` |
| 627 `energy-domain-model` | V17-E | energy domain model | Authoritative hard rules apply. | `NOT_RUN` |
| 628 `grid-metering-and-dispatch-semantics` | V17-E | grid metering and dispatch semantics | 测量值与质量标志一起迁移； Command和Confirmation分开； Event Time与Processing Time分开； 计量修正保留版本； 拓扑变化影响计算； 控制指令需严格Authorization； 关键动作保留人工或操作员边界。 -- | `NOT_RUN` |
| 629 `energy-critical-infrastructure-control-pack` | V17-E | energy critical infrastructure control pack | 不同地区使用各自监管Overlay； Cyber Asset分类需客户确认； 关键区域默认无公网； Remote Access强审计； Patch需兼顾可靠性； 时间同步受保护； Critical Control失败阻止交付。 -- | `NOT_RUN` |
| 630 `energy-migration-recipe-pack` | V17-E | energy migration recipe pack | 控制面和分析面分开； 遥测丢失和质量差异可检测； 时序数据精度保持； 大规模数据迁移支持分区； 调度Algorithm需行为对比； OT Protocol通过受控Adapter； 不能将模拟结果直接替代现场验证。 -- | `NOT_RUN` |
| 631 `energy-digital-twin-and-failure-validation` | V17-E | energy digital twin and failure validation | Authoritative hard rules apply. | `NOT_RUN` |
| 632 `energy-reference-architecture` | V17-E | energy reference architecture | Authoritative hard rules apply. | `NOT_RUN` |
| 633 `energy-delivery-and-channel-pack` | V17-E | energy delivery and channel pack | Authoritative hard rules apply. | `NOT_RUN` |
| 634 `healthcare-domain-model` | V17-E | healthcare domain model | Authoritative hard rules apply. | `NOT_RUN` |
| 635 `clinical-patient-and-consent-semantics` | V17-E | clinical patient and consent semantics | 患者合并不可仅按姓名； Consent撤销影响后续访问； 临床数据不允许普通覆盖更新； Provenance保留； Break-glass需审计； 敏感医疗类别可有更严格控制； Agent不得自主作出临床最终决定。 -- | `NOT_RUN` |
| 636 `healthcare-privacy-security-and-clinical-risk-pack` | V17-E | healthcare privacy security and clinical risk pack | 隐私规则按地区Overlay； Clinical Safety与Security共同评估； 测试数据必须脱敏或合成； Audit访问不可删除； 临床Decision Support需Human Oversight； Patient Access和更正流程纳入； 高风险临床功能需Safety Case。 -- | `NOT_RUN` |
| 637 `healthcare-interoperability-migration-recipe-pack` | V17-E | healthcare interoperability migration recipe pack | FHIR Resource存在不代表符合地区Profile； Extension不能丢失； Reference完整； Terminology Binding保留； Missing与Unknown区分； Bundle事务语义明确； 历史Version和Provenance迁移。 -- | `NOT_RUN` |
| 638 `healthcare-behavior-clinical-safety-and-evaluation` | V17-E | healthcare behavior clinical safety and evaluation | Authoritative hard rules apply. | `NOT_RUN` |
| 639 `healthcare-reference-architecture` | V17-E | healthcare reference architecture | Authoritative hard rules apply. | `NOT_RUN` |
| 640 `healthcare-delivery-and-channel-pack` | V17-E | healthcare delivery and channel pack | Authoritative hard rules apply. | `NOT_RUN` |
| 641 `government-domain-model` | V17-E | government domain model | Authoritative hard rules apply. | `NOT_RUN` |
| 642 `public-service-identity-case-and-record-model` | V17-E | public service identity case and record model | 政府身份和平台账户分开； 代理授权有期限； Case决定保留依据； Records不可任意删除； Appeal独立； 公共数据和受限数据分开； 无障碍和多语言属于功能要求。 -- | `NOT_RUN` |
| 643 `government-security-privacy-sovereignty-control-pack` | V17-E | government security privacy sovereignty control pack | 地区政府规则使用专用Overlay； Sovereign要求覆盖运维和支持； 管理员访问受严格审计； 公共透明不等于公开个人数据； 采购供应链证据完整； Offline和分级网络需独立架构； 政务AI高影响决定需人类监督。 -- | `NOT_RUN` |
| 644 `government-legacy-modernization-recipe-pack` | V17-E | government legacy modernization recipe pack | 法定业务规则有来源； PDF/Form字段需语义映射； 大型Batch可Restart； 历史决定和文档不可丢失； 公共API兼容； Accessibility进入测试； 旧系统Read-only归档可查询。 -- | `NOT_RUN` |
| 645 `government-service-public-interest-evaluation` | V17-E | government service public interest evaluation | Authoritative hard rules apply. | `NOT_RUN` |
| 646 `government-reference-architecture` | V17-E | government reference architecture | Authoritative hard rules apply. | `NOT_RUN` |
| 647 `government-delivery-and-channel-pack` | V17-E | government delivery and channel pack | Authoritative hard rules apply. | `NOT_RUN` |
| 648 `commerce-domain-model` | V17-E | commerce domain model | Authoritative hard rules apply. | `NOT_RUN` |
| 649 `order-inventory-payment-and-fulfilment-semantics` | V17-E | order inventory payment and fulfilment semantics | Inventory Reserve与实际扣减区分； Price Snapshot保留； Promotion应用顺序明确； Payment Timeout后检查实际状态； Order Retry幂等； Shipment可分单； Refund和Return分开。 -- | `NOT_RUN` |
| 650 `commerce-payment-fraud-and-consumer-control-pack` | V17-E | commerce payment fraud and consumer control pack | 支付卡数据尽量Token化； Fraud模型不自动拒绝高影响用户而无申诉； 价格展示和结算一致； Promotion防重复使用； Seller数据严格隔离； 用户删除不破坏财务保留； 退款权限和审批明确。 -- | `NOT_RUN` |
| 651 `commerce-migration-recipe-pack` | V17-E | commerce migration recipe pack | 业务规则先提升为Policy Model； Promotion Recipe需大量边界测试； 库存使用明确Consistency； Search是派生数据； 订单事件保持因果顺序； 支付Adapter隔离Provider； Flash Sale路径单独设计。 -- | `NOT_RUN` |
| 652 `commerce-scale-and-business-rule-evaluation` | V17-E | commerce scale and business rule evaluation | Authoritative hard rules apply. | `NOT_RUN` |
| 653 `commerce-reference-architecture` | V17-E | commerce reference architecture | Authoritative hard rules apply. | `NOT_RUN` |
| 654 `commerce-delivery-and-channel-pack` | V17-E | commerce delivery and channel pack | Authoritative hard rules apply. | `NOT_RUN` |
| 655 `telecom-domain-model` | V17-E | telecom domain model | Authoritative hard rules apply. | `NOT_RUN` |
| 656 `subscriber-network-usage-and-charging-semantics` | V17-E | subscriber network usage and charging semantics | Usage Event具有稳定ID； Event Time和Ingest Time分开； Late Event有处理策略； Charging Rule版本保留； Session关联完整； Subscriber Privacy受保护； Network Function和业务Service边界分开。 -- | `NOT_RUN` |
| 657 `telecom-security-privacy-and-operations-control-pack` | V17-E | telecom security privacy and operations control pack | 网络管理权限与普通IT权限分开； 运营指令有审批和审计； Subscriber数据最小化； 关键Network Function故障有Fallback； 配置变更可回滚； 漫游和互联边界需Contract Test； 地区通信法规通过Overlay处理。 -- | `NOT_RUN` |
| 658 `telecom-bss-oss-network-function-recipe-pack` | V17-E | telecom bss oss network function recipe pack | BSS和OSS对象不可简单合并； Product、Service和Resource层次保持； Usage处理支持高吞吐和重放； Charging计算使用确定性规则； Network Function API需授权； Legacy Protocol通过Adapter； 业务和网络流程使用Saga或状态机。 -- | `NOT_RUN` |
| 659 `telecom-scale-event-and-charging-evaluation` | V17-E | telecom scale event and charging evaluation | Authoritative hard rules apply. | `NOT_RUN` |
| 660 `telecom-reference-architecture` | V17-E | telecom reference architecture | Authoritative hard rules apply. | `NOT_RUN` |
| 661 `telecom-delivery-and-channel-pack` | V17-E | telecom delivery and channel pack | Authoritative hard rules apply. | `NOT_RUN` |
| 662 `vertical-poc-and-demo-factory` | V17-F | 为每个行业建立可信Demo、Sample Data、评测和POC模板。 | Demo不得使用真实敏感数据； POC不等于监管认证； 不能只展示Happy Path； 行业结论需专家确认； POC结果不能无条件外推； Sample可重复； POC资产可区域本地化。 -- | `NOT_RUN` |
| 663 `vertical-proposal-sow-and-pricing-template-manager` | V17-F | 生成行业专用Discovery、Assessment、POC、实施和Managed Service方案。 | 适用监管由客户确认； 不承诺“自动合规”； 行业专家成本计入； 地区Overlay进入Scope； 现场、Edge和设备工作单独报价； 临床、金融和Safety验收角色明确； 控制变化使用Change流程。 -- | `NOT_RUN` |
| 664 `vertical-partner-recruitment-and-capability-matrix` | V17-F | vertical partner recruitment and capability matrix | 通用平台认证不等于行业认证； 高风险行业需领域专家； 合规伙伴不能替代技术交付能力； 客户数据访问单独批准； Partner冲突披露； 地区资质需验证； 能力定期复审。 -- | `NOT_RUN` |
| 665 `vertical-training-certification-and-delivery-authorization` | V17-F | vertical training certification and delivery authorization | POC认证不能执行生产Cutover； 高风险验收需高级认证； 认证绑定个人； 标准更新需续证； 交付质量影响认证； 严重事故可暂停； 地区语言认证不降低技术标准。 -- | `NOT_RUN` |
| 666 `regional-vertical-channel-replication` | V17-F | regional vertical channel replication | 全球行业Pack不能直接宣称符合本地监管； 地区Overlay需专业Review； 本地Partner需行业认证； 首批客户必须有强化支持； 本地案例不得由其他地区案例替代； 销售主张与当前Overlay一致； 未达到支持能力不得规模销售。 -- | `NOT_RUN` |
| 667 `vertical-marketplace-and-industry-asset-ecosystem` | V17-F | vertical marketplace and industry asset ecosystem | Regulatory Overlay只能由授权Publisher发布； 行业Code Set License明确； 医疗、金融和关键基础设施资产需增强审核； 客户私有控制不可公开； 资产更新触发客户影响分析； Certification不可购买； Critical资产可紧急撤销。 -- | `NOT_RUN` |
| 668 `batch-17-vertical-solution-conformance-gate` | V17-G | 综合领域模型、监管控制、Recipe、评测、Reference Architecture、商业打包和渠道能力，决定行业版本是否可商业交付。 | 七个行业使用共享平台内核； 每个行业拥有真实领域模型； 监管控制可追踪到技术和证据； 行业Recipe经过完整测试； 关键业务Invariant得到验证； Reference Architecture可以生产交付； 行业POC和报价标准化； 行业伙伴具备交付能力； 地区Overlay可以安全复制； 行业版本具备持续维护机制。 -- | `NOT_RUN` |
