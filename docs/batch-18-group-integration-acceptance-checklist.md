# Batch 18 Group Integration Factory acceptance checklist

Repository implementation does not close field acceptance. Every row remains `NOT_RUN` until the named external system of record supplies current, authorized, version-bound evidence.

| Skill | Gate | Capability | Authoritative acceptance | Field status |
| --- | --- | --- | --- | --- |
| 669 `ma-integration-orchestrator` | M18-A | 统一编排交易假设、Day 1、应用组合、身份、数据、技术整合、协同收益和退役。 | 所有Workstream使用同一整合主计划； 技术和业务里程碑一致； Day 1、Day 100和长期计划可查询； 整合风险和收益同时可见； 结果可向管理层和董事会报告。 -- | `NOT_RUN` |
| 670 `deal-thesis-and-integration-archetype-builder` | M18-A | 把交易投资逻辑转换为可执行整合模式。 | 各业务域整合模式明确； 模式与交易价值一致； 资源和时限可估算； 整合优先级有依据； 非整合范围明确。 -- | `NOT_RUN` |
| 671 `clean-team-and-pre-close-data-boundary-manager` | M18-A | 管理交割前Clean Team、敏感信息访问和分析边界。 | Clean Team成员清晰； 信息访问可审计； 输出不泄露受限细节； 交易前分析和交割后执行分开； 数据处理符合交易政策。 -- | `NOT_RUN` |
| 672 `day-one-day-hundred-plan-manager` | M18-A | 建立Day 1、Day 30、Day 100和长期整合路线。 | Day 1关键业务可运行； 员工和客户获得清晰指引； Day 100结果可追踪； 临时措施有退出计划； 重大风险已升级。 -- | `NOT_RUN` |
| 673 `integration-management-office-controller` | M18-A | 建立集团Integration Management Office，统一治理业务、技术、财务和组织整合。 | 整合拥有单一控制中心； Workstream状态一致； 重大依赖可见； 决策速度提高； 协同收益和技术进度一致； 管理层获得统一报告。 -- | `NOT_RUN` |
| 674 `group-application-portfolio-discovery` | M18-B | 盘点集团全部应用、产品、平台和业务能力。 | 关键应用覆盖率达到目标； 每个应用有Owner和能力映射； 影子IT可见； 成本和风险可估算； 为重复系统分析提供基础。 -- | `NOT_RUN` |
| 675 `automated-technology-estate-discovery` | M18-B | 自动扫描代码、运行时、云、数据库、网络、证书和工具链。 | 技术栈分布可查询； 依赖和版本可见； 未登记接口被发现； 高风险EOL组件可识别； 结果支持迁移自动估算。 -- | `NOT_RUN` |
| 676 `application-data-interface-dependency-graph` | M18-B | 建立应用、数据、身份、消息、用户和外部合作方的集团依赖图。 | 关键应用依赖完整； Wave和Cutover可基于图谱规划； 隐藏调用方减少； 共享平台单点可见； 退役风险可计算。 -- | `NOT_RUN` |
| 677 `duplicate-system-and-capability-overlap-detector` | M18-B | 识别承担相同或重叠业务能力的系统。 | 重复能力清单可查询； 真重复和合理变体分开； 成本机会可估算； 处置决策有事实依据； False Positive可纠正。 -- | `NOT_RUN` |
| 678 `application-disposition-and-target-system-manager` | M18-B | 为每项应用确定目标处置方式。 | 组合处置覆盖完整； 目标系统明确； 处置与交易逻辑一致； 时间和成本可估算； 退役前提可查询。 -- | `NOT_RUN` |
| 679 `group-business-capability-map` | M18-B | 建立跨法人、品牌和地区的集团业务能力地图。 | 业务和IT使用统一语言； 能力重复可识别； 目标Operating Model可设计； 应用组合可按能力查看； 投资和退役优先级更清晰。 -- | `NOT_RUN` |
| 680 `legal-entity-region-and-business-boundary-model` | M18-B | 定义法人、地区、品牌、数据和合同边界。 | 每项资产有法人归属； 数据共享有合法依据； 地区限制可执行； 财务和税务边界明确； 分离和整合范围可审计。 -- | `NOT_RUN` |
| 681 `transition-service-agreement-catalog-manager` | M18-B | 管理TSA服务、费用、SLA、依赖和退出路线。 | TSA清单完整； 每项有退出路线； 成本和风险可见； SLA可监控； TSA按期退出率可衡量。 -- | `NOT_RUN` |
| 682 `technical-debt-operational-and-regulatory-risk-baseline` | M18-B | 建立交易后统一风险基线。 | 高风险应用和依赖可见； 迁移Wave考虑风险； 短期缓解和长期方案分开； 管理层理解技术风险； 风险影响协同模型。 -- | `NOT_RUN` |
| 683 `group-target-enterprise-architecture-builder` | M18-C | 定义集团目标业务、数据、应用、集成、技术和安全架构。 | 目标状态清晰； Transitional Architecture可运行； 应用处置可映射目标架构； 技术标准和例外可管理； 管理层批准架构原则。 -- | `NOT_RUN` |
| 684 `technology-standard-and-exception-governor` | M18-C | 建立集团批准技术栈、生命周期和例外机制。 | 技术组合复杂度可控； 例外可查询； EOL技术有退出路线； 新项目标准采用率提高； 集团采购和人才计划得到支持。 -- | `NOT_RUN` |
| 685 `cloud-infrastructure-and-data-center-consolidator` | M18-C | 规划云账号、区域、数据中心、主机、网络和基础设施收敛。 | 基础设施目标拓扑明确； 数据中心退出日期可追踪； 云成本和合同可见； 迁移Wave与应用一致； Stranded Infrastructure可移除。 -- | `NOT_RUN` |
| 686 `developer-platform-and-software-supply-chain-integration` | M18-C | 整合Git、CI/CD、Artifact、Secrets、开发环境和安全扫描。 | 开发团队使用目标平台； Build和Release可重复； Artifact来源完整； Secret和权限安全； 旧平台使用率持续下降； 开发者生产力可衡量。 -- | `NOT_RUN` |
| 687 `group-shared-platform-migration-manager` | M18-C | 迁移身份、消息、数据、API、监控、财务等共享平台。 | 目标共享平台可承载集团负载； 内部客户迁移计划完整； 双平台期受控； 服务质量稳定； 重复平台开始退出。 -- | `NOT_RUN` |
| 688 `integration-wave-and-migration-factory-planner` | M18-C | 按业务、依赖、地区和风险建立迁移Wave。 | Wave顺序合理； 关键依赖被考虑； 迁移工厂可复用前Wave资产； 计划和收益同步； 每Wave可独立验收。 -- | `NOT_RUN` |
| 689 `group-migration-factory-capacity-manager` | M18-C | 管理集团迁移工厂的人力、Agent、Runner、伙伴和专家产能。 | 未来Wave资源可预测； 技能缺口可见； 工厂吞吐可衡量； 资源冲突可解决； 自动化和人工比例透明； 工厂成本进入Synergy模型。 -- | `NOT_RUN` |
| 690 `group-integration-control-tower` | M18-C | 提供集团级应用、数据、身份、TSA、风险、成本和收益驾驶舱。 | 管理层掌握整合全景； 关键问题可钻取； Wave和收益可关联； TSA退出风险可见； 决策和行动可追踪。 -- | `NOT_RUN` |
| 691 `identity-estate-inventory` | M18-D | identity estate inventory | 人员账户和服务账户分开； 无Owner身份进入风险； 离职账户重点检查； 共享账号必须识别； 身份源系统明确； 实际登录数据用于确认； 高权限身份提前处理。 -- | `NOT_RUN` |
| 692 `person-account-correlation-and-mastering` | M18-D | 关联两家公司中的同一员工、承包商、客户或合作伙伴身份。 | 不能仅按姓名匹配； 自动匹配需置信度； 冲突需人工处理； 同一人多个角色允许保留； 个人和服务身份不可合并； 匹配证据需保护隐私； Master ID变更有审计。 -- | `NOT_RUN` |
| 693 `day-one-identity-federation` | M18-D | 通过Federation、B2B或临时信任实现Day 1访问。 | Federation不自动合并目录； 只开放必要应用； 交割前访问边界严格； MFA要求不降低； Guest身份有期限； 高权限应用需额外审批； 临时Federation有退出计划。 -- | `NOT_RUN` |
| 694 `directory-sso-and-lifecycle-consolidation` | M18-D | 逐步合并目录、SSO、Provisioning和员工生命周期。 | HR权威源先明确； Group映射不能扩大权限； 用户迁移和应用迁移协调； Session和Token迁移有策略； 旧目录Read-only期明确； 离职撤销必须实时； 目录退役前扫描隐藏依赖。 -- | `NOT_RUN` |
| 695 `role-permission-and-separation-of-duties-harmonizer` | M18-D | 协调双方Role、Group、Permission和职责分离规则。 | 同名Role不代表同权限； 合并默认取最小必要权限； 高权限需重新认证； SoD冲突自动发现； 历史访问不自动保留； 地区和法人限制继续生效； 权限变化通知Owner。 -- | `NOT_RUN` |
| 696 `privileged-and-service-identity-integration` | M18-D | 整合管理员、机器账号、证书、Secret和PAM。 | 共享管理员账号优先消除； 服务身份有Owner； 长期Secret逐步替换； Credential不明时先轮换； 旧系统退役同步撤销； 证书和信任链纳入； 高权限活动统一审计。 -- | `NOT_RUN` |
| 697 `identity-cutover-and-rollback-manager` | M18-D | 控制身份切换、双目录期和回滚。 | Cutover前验证关键应用； 旧身份系统保留受控Fallback； 账户创建和禁用在切换窗口冻结或排队； Group Delta必须追平； 回滚不恢复不应保留的权限； Break-glass经过测试； 最终身份核对通过。 -- | `NOT_RUN` |
| 698 `data-domain-and-ownership-model` | M18-D | data domain and ownership model | Authoritative hard rules apply. | `NOT_RUN` |
| 699 `group-canonical-data-model` | M18-D | 建立集团Canonical Model，同时保留地区和业务Variant。 | Canonical不意味着物理Schema统一； 业务含义优先； Source字段血缘保留； Variant显式； Code Set统一治理； 模型版本化； 不可映射字段不得静默丢弃。 -- | `NOT_RUN` |
| 700 `master-data-management-and-entity-resolution` | M18-D | 合并客户、员工、供应商、产品和地点主数据。 | 自动Merge必须可撤销； Golden Record有来源； 冲突字段有规则； 隐私和Consent限制合并； 同名企业和个人谨慎处理； 历史ID保留； Merge和Unmerge均审计。 -- | `NOT_RUN` |
| 701 `data-quality-and-migration-readiness-assessor` | M18-D | data quality and migration readiness assessor | 数据质量问题不应全部由迁移项目承担； 必须区分迁移前缺陷和迁移引入缺陷； Critical数据规则优先； 清理责任明确； 质量阈值进入Cutover Gate； 无法修复数据有业务决策； 报告按数据域展示。 -- | `NOT_RUN` |
| 702 `data-migration-cdc-and-coexistence-controller` | M18-D | 执行全量、增量、双运行和最终切换。 | 每个数据域有权威写入者； 删除和撤销必须同步； CDC Position持久化； Backfill可恢复； Schema变化受控； 双写差异实时监控； Final Delta核对后才切换。 -- | `NOT_RUN` |
| 703 `privacy-consent-and-residency-harmonizer` | M18-D | 协调双方隐私目的、Consent、地区和数据使用限制。 | 并购不自动意味着所有数据可自由共享； Purpose of Use继续有效； Consent合并需合法依据； 跨境处理单独评估； 模型和Analytics同样受限； 数据最小化； 无法共享的数据保持隔离或删除。 -- | `NOT_RUN` |
| 704 `records-retention-and-legal-hold-integration` | M18-D | 统一保留计划、诉讼保全、审计和销毁。 | 合并Retention不能简单取最短； Legal Hold优先； 被收购方历史记录可恢复； Backup进入保留范围； 退役系统前完成归档； 重复记录删除需审慎； 销毁产生证明。 -- | `NOT_RUN` |
| 705 `data-platform-bi-and-metric-integration` | M18-D | 合并数据仓库、Lakehouse、BI、报表和指标。 | 同名指标需核对定义； Executive指标建立集团语义层； 历史时间序列保留； 合并前后口径变化明确； 报表用户迁移； 权限和行级安全协调； 旧BI退役前验证使用。 -- | `NOT_RUN` |
| 706 `group-data-reconciliation-and-quality-gate` | M18-D | group data reconciliation and quality gate | 聚合相同不能掩盖明细错误； 金融和员工数据使用更严格门槛； 核对结果绑定Snapshot； Unknown差异不能算通过； 数据Owner正式签字； 差异有修复或接受流程； 结果进入集团控制塔。 -- | `NOT_RUN` |
| 707 `api-event-edi-file-integration-inventory` | M18-D | api event edi file integration inventory | Authoritative hard rules apply. | `NOT_RUN` |
| 708 `integration-hub-facade-and-strangler-architecture` | M18-D | 通过Facade、API Gateway、Event Hub和Strangler降低直接耦合。 | Integration Hub不能变成所有逻辑的God Layer； 新接口优先Canonical Contract； 旧系统通过Adapter隔离； Facade有退出或长期定位； 延迟和可用性预算明确； 安全和审计统一； 接口版本有生命周期。 -- | `NOT_RUN` |
| 709 `event-message-and-schema-harmonizer` | M18-D | 协调Topic、Queue、事件名、Key、Header和Schema。 | 同名事件语义需核对； 业务Event和技术消息分开； Key和Ordering保留； 双消费者不能产生双副作用； Schema兼容； DLQ和Replay协调； 事件Owner明确。 -- | `NOT_RUN` |
| 710 `master-data-distribution-and-synchronization` | M18-D | 把集团主数据可靠分发至各应用。 | 主数据来源唯一； Consumer知道版本； 删除和失效传播； 离线系统支持缓冲； 数据域权限不扩大； 分发失败可重放； 旧同步方式有退出计划。 -- | `NOT_RUN` |
| 711 `integration-observability-and-flow-monitor` | M18-D | integration observability and flow monitor | 跨公司链路有统一Correlation； 接口黑洞为0； 失败告警有Owner； 业务和技术错误分开； 过渡接口单独标记； TSA接口可监控； 退役前确认流量为0。 -- | `NOT_RUN` |
| 712 `network-dns-connectivity-integration` | M18-E | network dns connectivity integration | 地址冲突提前处理； DNS切换可回滚； 临时网络桥接有期限； 不直接建立无限信任网络； East-West访问最小化； 网络变更进入Day 1演练； 旧连接退役前扫描。 -- | `NOT_RUN` |
| 713 `security-control-baseline-harmonizer` | M18-E | security control baseline harmonizer | 不默认选择较弱控制； Control差异有风险决策； Day 1最低安全基线明确； 合并SOC视图； 严重漏洞优先修复； 安全例外有期限； 集团控制映射法人要求。 -- | `NOT_RUN` |
| 714 `endpoint-device-and-digital-workplace-integration` | M18-E | endpoint device and digital workplace integration | Day 1沟通工具必须可用； 设备管理切换分Wave； 数据迁移符合隐私； 旧设备Credential清理； 地区劳动规则需确认； 员工体验可监控； 合并不应造成大规模权限丢失。 -- | `NOT_RUN` |
| 715 `infrastructure-cloud-and-data-center-integration` | M18-E | infrastructure cloud and data center integration | 资产发现完整； 运行容量和DR同时规划； 迁移期间不重复删除； Contract退出时间可见； Stranded Cost识别； 能耗和设施约束可考虑； 最终CMDB更新。 -- | `NOT_RUN` |
| 716 `backup-dr-and-business-continuity-integration` | M18-E | 协调双方Backup、Restore、RPO、RTO和危机流程。 | 合并系统需重新评估RPO/RTO； Backup格式可恢复； 旧Key和证书保留； DR环境同步迁移； TSA终止前验证替代恢复能力； 重要业务进行联合演练； 归档和Backup分开。 -- | `NOT_RUN` |
| 717 `observability-soc-and-it-operations-integration` | M18-E | observability soc and it operations integration | 告警在切换前接入； 双系统期间去重事件； On-call责任明确； 日志驻留符合要求； 监控缺失阻止Cutover； 重大事件使用统一指挥； 旧工具退役需数据导出。 -- | `NOT_RUN` |
| 718 `erp-and-group-finance-integration` | M18-E | erp and group finance integration | Day 1财务和付款连续； 科目映射由财务批准； 历史账务不删除； 法人账簿保持； Intercompany交易明确； Cutover配合财务期； 财务核对差异为0或正式接受。 -- | `NOT_RUN` |
| 719 `crm-and-commercial-system-integration` | M18-E | crm and commercial system integration | Account合并可撤销； 客户Owner冲突有规则； Pipeline不重复； 合同和价格保留来源； Consent和Marketing Preference合并； Sales Territory重新分配； CRM Cutover不影响客户沟通。 -- | `NOT_RUN` |
| 720 `hris-payroll-and-employee-system-integration` | M18-E | hris payroll and employee system integration | Payroll Day 1连续； 员工ID映射稳定； 薪酬隐私严格； 法人和地区规则保留； Manager和组织结构同步； 离职流程统一； HR数据访问最小化。 -- | `NOT_RUN` |
| 721 `procurement-vendor-and-contract-integration` | M18-E | 整合供应商、采购、合同、License和付款条件。 | 同一供应商实体解析； 重复合同识别； 价格和期限比较； 终止和转让条款需法务确认； Vendor风险重新评估； 集中采购收益可测； 不影响关键供应连续性。 -- | `NOT_RUN` |
| 722 `itsm-cmdb-and-support-integration` | M18-E | itsm cmdb and support integration | 工单历史可查询； CMDB数据质量先评估； Service Owner统一； SLA变化通知客户； Day 1支持入口明确； 双Ticket系统期间有路由； 旧系统关闭前知识迁移。 -- | `NOT_RUN` |
| 723 `ot-plant-and-edge-integration` | M18-E | 处理并购后的工厂、设备、边缘和OT环境整合。 | 不强制统一现场控制平台； 安全和生产连续优先； 设备资产与法人关联； 远程访问重新授权； OT网络不直接并入IT信任域； Edge数据同步有缓冲； 工厂整合按现场窗口执行。 -- | `NOT_RUN` |
| 724 `customer-channel-and-digital-experience-integration` | M18-E | customer channel and digital experience integration | 品牌策略先明确； 客户账号合并需谨慎； Loyalty余额不可丢失； 登录迁移可回滚； 通知Consent保留； 客户渠道切换有Fallback； 用户体验指标持续监控。 -- | `NOT_RUN` |
| 725 `carve-out-separation-orchestrator` | M18-F | 把出售或拆分业务从集团系统中安全分离。 | Separation Perimeter明确； 共享系统逐项识别； 数据复制符合最小必要； IP和源码归属确认； TSA有结束日期； 残留访问撤销； 分离后的独立能力经过验证。 -- | `NOT_RUN` |
| 726 `carve-out-data-extraction-and-sanitization` | M18-F | 提取目标业务数据并删除不属于交易范围的数据。 | 数据按法人、业务和合同筛选； 共享记录需字段级处理； Legal Hold优先； 数据提取有Hash和核对； 非交易客户数据不得复制； 测试环境同样清理； 交付后有销毁证明。 -- | `NOT_RUN` |
| 727 `identity-network-and-access-separation` | M18-F | 分离目录、账号、证书、网络和系统访问。 | 独立身份系统在TSA退出前就绪； 共享账号必须消除； 管理员和服务身份重新签发； Trust关系按计划撤销； DNS和证书独立； 原集团员工访问按期限撤销； 分离后进行越权测试。 -- | `NOT_RUN` |
| 728 `tsa-exit-and-standalone-operation-validator` | M18-F | 验证业务在不依赖卖方服务的情况下独立运行。 | TSA退出需实际演练； 不能仅依靠项目报告； 最后一日Delta核对； Support和Incident独立； 旧访问立即撤销； 延期需商业审批； 退出后监控稳定期。 -- | `NOT_RUN` |
| 729 `synergy-model-builder` | M18-G | synergy model builder | 每项收益有Baseline； 防止重复计算； 收益和技术行动关联； 时间到Run-rate明确； 风险和依赖可见； 未实现收益不提前确认； Revenue Synergy与Cost Synergy分开。 -- | `NOT_RUN` |
| 730 `cost-baseline-and-run-rate-calculator` | M18-G | cost baseline and run rate calculator | 合同承诺和当前支出分开； 人员成本需考虑重新部署； 一次性和Run-rate分开； 汇率和税明确； 双运行期成本可见； Stranded Cost不自动消失； 财务部门确认Baseline。 -- | `NOT_RUN` |
| 731 `value-capture-office-manager` | M18-G | 建立专门的Value Capture Office追踪协同收益。 | 项目完成不等于收益实现； 财务确认独立； Synergy Owner属于业务； 技术团队提供Enablement； 未实现收益有根因； 变更保持原始Target； 收益追踪持续到Run-rate。 -- | `NOT_RUN` |
| 732 `one-time-cost-and-stranded-cost-manager` | M18-G | one time cost and stranded cost manager | 系统退役不自动计为全部节省； Stranded Cost有移除行动； 共享成本分配透明； 一次性成本有上限； 超预算需审批； Cost Avoidance和Cash Saving分开； 后续年度持续核对。 -- | `NOT_RUN` |
| 733 `revenue-synergy-and-cross-sell-enabler` | M18-G | 通过客户、产品、渠道和数据整合支持收入协同。 | 收入协同不能忽视Consent； 客户重复去重准确； 销售归属明确； 不把Pipeline算作收益； 产品准备度和交付容量同步； 交叉销售实验可衡量； 客户体验不下降。 -- | `NOT_RUN` |
| 734 `synergy-reconciliation-and-financial-acceptance` | M18-G | 将计划、实际和财务账中的Synergy进行核对。 | 财务和IMO使用同一口径； 一次性收益不算永久Run-rate； 收入协同使用实现收入； 收益调整有审批； 未实现项保留； 交易模型和实际比较； 董事会获得真实结果。 -- | `NOT_RUN` |
| 735 `group-integration-governance-and-decision-rights` | M18-H | group integration governance and decision rights | 决策权限明确； 自我审批受限； 紧急决策事后复核； 两家公司管理者参与； 决策记录完整； 冲突升级有路径； 治理随整合阶段简化。 -- | `NOT_RUN` |
| 736 `architecture-review-and-exception-manager` | M18-H | 统一审查目标架构、应用处置、数据和技术例外。 | Review聚焦重大决策； 标准项目使用快速通道； 例外有Owner和期限； 不以架构治理拖延Day 1； 跨行业和地区要求可覆盖； 决策可回溯； 例外数量持续下降。 -- | `NOT_RUN` |
| 737 `compliance-audit-and-regulatory-integration` | M18-H | 协调双方控制、审计、监管申报和证据。 | 适用要求由专业团队确认； 控制Gap进入整合计划； 监管通知和批准时间纳入； 证据保留； 审计历史可访问； 控制不能在切换中失效； 合并后重新评估范围。 -- | `NOT_RUN` |
| 738 `change-management-and-communications` | M18-H | change management and communications | 技术变更必须有用户准备； 不能提前泄露交易敏感信息； 重大岗位变化由人类沟通； 不同地区使用适合渠道； 谣言和不确定性及时处理； 反馈进入整合风险； 沟通与实际状态一致。 -- | `NOT_RUN` |
| 739 `organization-role-and-workforce-transition` | M18-H | organization role and workforce transition | 组织决定不能只根据原公司身份； 关键人才提前识别； 工作和岗位随系统整合重构； 地区劳动规则由专业人员确认； 访问权限和岗位同步； 知识转移完成； 组织协同收益不以能力流失为代价。 -- | `NOT_RUN` |
| 740 `vendor-partner-and-outsourcing-integration` | M18-H | 整合供应商、外包商、合作伙伴和服务合同。 | Vendor实体和合同准确匹配； Concentration Risk分析； 同类供应商比较； 转让和终止条款确认； 服务连续性优先； 安全和数据处理重新评估； 伙伴渠道冲突协调。 -- | `NOT_RUN` |
| 741 `integration-raid-and-dependency-manager` | M18-H | integration raid and dependency manager | 所有High项有Owner； 假设失效触发Replan； 跨Wave依赖可见； Day 1阻塞优先； 风险发生转Issue； 决策进入日志； 重复问题形成Program Issue。 -- | `NOT_RUN` |
| 742 `integration-incident-command-and-freeze-manager` | M18-H | 处理Day 1、身份、数据、Cutover和TSA退出事故。 | SEV事件单一指挥； 数据完整性优先； Freeze不依赖故障系统； 证据保全； 业务和监管沟通明确； 恢复前重新验证； 事故形成新Gate。 -- | `NOT_RUN` |
| 743 `business-readiness-and-integration-acceptance` | M18-H | business readiness and integration acceptance | 技术上线不等于业务准备； 用户、支持和流程均需就绪； 条件验收有Owner和期限； Critical条件不能通过； 业务Owner正式签字； 收益和风险同时确认； 验收绑定具体Wave和版本。 -- | `NOT_RUN` |
| 744 `legacy-retirement-and-asset-cleanup` | M18-H | legacy retirement and asset cleanup | 旧系统不再承担业务责任； 数据和审计可恢复； 无隐藏调用方； 成本真正移除； 资产状态准确； TSA和合同正确结束。 -- | `NOT_RUN` |
| 745 `batch-18-group-integration-conformance-gate` | M18-H | 综合交易逻辑、Day 1、资产发现、应用去重、身份、数据、技术栈、TSA、协同收益和退役结果，判断集团整合是否达标。 | Day 1业务连续； 应用、数据和身份资产透明； 重复系统得到事实化处置； 目标技术和业务架构生效； 身份和数据安全合并； Wave迁移可复制； TSA按计划退出； 旧系统和成本真正退役； 协同收益得到财务确认； 集团治理和运营进入稳定状态。 -- | `NOT_RUN` |
