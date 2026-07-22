# Batch 14 growth and ecosystem acceptance checklist

This checklist maps the complete authoritative Skill 401–460 set to its field acceptance contract. Repository implementation, local tests, generated artifacts, plans, forecasts and simulations do not close these rows. Each row remains NOT_RUN until the named external system of record returns tenant-, region-, version-, consent- and time-bound evidence.

| Skill | Gate | Capability question | Authoritative acceptance criteria | Field status |
| --- | --- | --- | --- | --- |
| 401 `growth-system-orchestrator` | G14-A | 统一编排产品增长、内容、开发者、社区、Marketplace和区域复制。 | 增长域使用统一计划；渠道和产品动作相互衔接；增长结果可按Segment和Region分析；成功策略可重复；低质量增长可及时停止。 | NOT_RUN |
| 402 `north-star-and-growth-metric-designer` | G14-A | 定义North Star、输入指标、结果指标和增长防护指标。 | North Star可自动计算；Driver Tree完整；Guardrail可实时查询；指标口径一致；管理层和产品使用同一指标；指标与续费和收入有相关证据。 | NOT_RUN |
| 403 `user-journey-and-growth-funnel-modeler` | G14-A | 建模开发者、架构师、企业管理员、伙伴和Marketplace发布者的不同旅程。 | 主要Persona有Journey；每个阶段有事件；流失点可分析；Sales和Product漏斗可以关联；Journey可以驱动个性化引导。 | NOT_RUN |
| 404 `acquisition-channel-architecture-manager` | G14-A | 设计、评估和治理Organic、Paid、Community、Partner和Product渠道。 | 每个渠道有目标Persona；渠道质量可比较；CAC和转化可查询；渠道归因不重复；低效渠道及时优化；渠道可与销售和产品数据关联。 | NOT_RUN |
| 405 `product-led-growth-strategy-manager` | G14-A | 设计无需重度销售参与即可让用户体验价值、邀请团队并升级的产品路径。 | 用户可自助完成首次价值；Trial成本受控；Upgrade路径清晰；Product-qualified Lead可识别；PLG不会降低企业安全；免费到付费转化可衡量。 | NOT_RUN |
| 406 `self-service-signup-and-workspace-provisioner` | G14-A | 提供低摩擦但安全的自助注册、团队创建和Workspace Provisioning。 | 注册流程顺畅；Workspace自动创建；OAuth权限最小；滥用受控；匿名和登录Journey可关联；Trial成本可管理。 | NOT_RUN |
| 407 `first-assessment-activation-orchestrator` | G14-A | 帮助新用户以最少步骤完成第一次可信Repository Assessment。 | 用户可在短时间获得Assessment；失败路径有修复指引；推荐符合仓库事实；用户理解下一步；Activation Rate可衡量；Time to Assessment持续下降。 | NOT_RUN |
| 408 `time-to-value-optimizer` | G14-A | 系统减少从注册到Assessment、Build Green和团队采用的时间。 | 主要TTV指标可查询；最大摩擦点有Owner；新用户完成率提高；首次失败恢复速度提高；安全Guardrail不退化；TTV与付费转化关联。 | NOT_RUN |
| 409 `trial-freemium-and-developer-plan-manager` | G14-A | 设计Trial、Free和Developer Plan的功能、配额、期限和升级策略。 | Trial能够展示真实价值；成本可控；滥用率低；到期和升级平滑；Trial-to-paid可衡量；不同Trial类型用途清晰。 | NOT_RUN |
| 410 `lifecycle-messaging-and-in-product-guidance` | G14-A | 根据用户Journey提供邮件、通知、Checklist、Tooltip和产品内指导。 | 用户获得适时指导；消息点击能转化为行动；退订和偏好生效；消息不会泄露项目；Stalled用户恢复率提高；通知疲劳受控。 | NOT_RUN |
| 411 `referral-invitation-and-team-expansion-manager` | G14-A | 通过邀请、分享报告、内部推荐和客户推荐推动团队扩散。 | 团队邀请流程顺畅；权限安全；Invite-to-active可衡量；Share带来协作；滥用和垃圾推荐受控；企业Workspace自然扩散。 | NOT_RUN |
| 412 `growth-experiment-and-feature-test-platform` | G14-A | 建立产品、内容、定价、Onboarding和渠道实验平台。 | 实验可稳定分组；Guardrail生效；决策可审计；无显著结果也被记录；实验可安全停止；成功实验可产品化。 | NOT_RUN |
| 413 `experiment-statistics-and-decision-controller` | G14-A | 对实验结果进行统计判断、业务判断和长期影响判断。 | 实验决策有证据；Effect Size清晰；Guardrail风险可见；Segment决策可执行；负面实验避免重复；决策进入知识库。 | NOT_RUN |
| 414 `growth-event-and-semantic-analytics-layer` | G14-A | 定义统一产品、内容、社区、Marketplace和渠道事件。 | Growth事件覆盖主要漏斗；Identity可安全解析；指标可复现；数据质量可监控；Region Consent生效；事件可服务实验和归因。 | NOT_RUN |
| 415 `channel-attribution-and-incrementality-manager` | G14-A | 估计内容、广告、伙伴、社区和产品渠道对Pipeline及Revenue的真实贡献。 | 主要渠道可比较；内容可关联Account和Pipeline；Partner贡献可识别；渠道CAC和Revenue可计算；归因不重复；投资决策有依据。 | NOT_RUN |
| 416 `content-strategy-and-topic-architecture` | G14-B | 建立围绕客户问题、技术栈、行业和迁移阶段的内容体系。 | 主题覆盖主要客户问题；内容与漏斗关联；每个Pillar有权威资产；内容Gap可识别；内容可以复用为销售和社区资产；旧内容可定期更新。 | NOT_RUN |
| 417 `technical-content-production-pipeline` | G14-B | 将工程知识、Recipe、项目经验和研究转化为高质量技术内容。 | 内容技术准确；示例可重现；发布周期可预测；内容来源可追踪；内容能产生目标用户行为；高价值内容持续更新。 | NOT_RUN |
| 418 `seo-topic-cluster-and-search-demand-manager` | G14-B | 通过技术搜索需求、主题集群和内部链接获得长期Organic流量。 | 核心主题形成Cluster；Organic Qualified Traffic增长；内容带来Assessment和Signup；多语言索引正确；重复内容受控；搜索排名与商业价值关联。 | NOT_RUN |
| 419 `comparison-migration-guide-and-solution-page-factory` | G14-B | 生产语言、框架、工具、架构和迁移方案比较页面。 | 用户可理解方案差异；内容能支持选型；技术结论准确；产生高质量商机；销售可以复用；页面及时更新。 | NOT_RUN |
| 420 `customer-case-study-and-proof-content-manager` | G14-B | 将POC、生产迁移和价值实现转化为案例、数据和证据内容。 | 案例真实可信；可支持不同Persona；数据有证据；客户授权完整；案例推动Pipeline；技术经验回馈内容和产品。 | NOT_RUN |
| 421 `webinar-workshop-and-technical-event-manager` | G14-B | 规划线上线下Webinar、Workshop、Demo Day和技术活动。 | 活动产生目标用户行动；Attendance和Conversion可查询；内容可复用；社区和伙伴参与；线索质量可衡量；活动成本有回报。 | NOT_RUN |
| 422 `research-industry-report-and-thought-leadership-manager` | G14-B | 通过市场研究、基准测试、迁移指数和行业报告建立权威。 | 报告具有可信方法；获得行业引用；产生高质量Pipeline；支持分析师和媒体；数据可衍生内容；研究结论促进产品Roadmap。 | NOT_RUN |
| 423 `developer-portal-builder` | G14-B | 提供统一开发者入口，包括文档、API、SDK、CLI、示例、状态和社区。 | 开发者可快速找到入口；Portal支持自助学习；文档、社区和Marketplace关联；版本和权限正确；搜索质量可衡量；Portal推动Activation。 | NOT_RUN |
| 424 `documentation-as-product-manager` | G14-B | 把文档作为具有Owner、指标、版本和质量门禁的正式产品。 | 核心流程文档完整；示例持续可运行；搜索和反馈可用；文档更新及时；多语言版本同步；文档减少支持工单。 | NOT_RUN |
| 425 `api-cli-and-sdk-developer-experience-manager` | G14-B | 优化API、CLI和SDK的可发现性、一致性、错误处理和示例。 | 开发者可通过API或CLI完成核心流程；SDK类型准确；错误可操作；示例可运行；Time to First API Call较短；API和SDK采用率可衡量。 | NOT_RUN |
| 426 `starter-kit-sample-repository-and-reference-app-manager` | G14-B | 提供代表性、多语言、多框架示例项目和迁移Starter Kit。 | 用户可快速体验真实流程；Starter Kit构建稳定；示例覆盖核心能力；社区可Fork和贡献；Demo可用于销售和活动；版本更新自动验证。 | NOT_RUN |
| 427 `interactive-demo-sandbox-and-playground` | G14-B | 提供无需接入真实源码即可体验Assessment、迁移、Diff和Marketplace的交互环境。 | 用户无需销售即可体验；Demo展示真实价值；Sandbox安全；Demo-to-signup可衡量；示例可复现；成本可控。 | NOT_RUN |
| 428 `developer-relations-program-manager` | G14-B | 建立工程团队与开发者、社区、开源和技术伙伴之间的长期关系。 | 开发者获得持续支持；产品反馈进入Roadmap；API和SDK采用提高；社区贡献增加；DevRel推动高质量使用；技术品牌可信度提高。 | NOT_RUN |
| 429 `champion-ambassador-and-expert-program` | G14-B | 培养企业内部Champion、社区专家、MVP和区域Ambassador。 | 专家和Champion可识别；社区回答质量提高；客户内部采用加速；区域活动有本地领导者；贡献与认可透明；Program可持续运营。 | NOT_RUN |
| 430 `community-platform-and-identity-integrator` | G14-C | 建立论坛、问答、讨论、活动和贡献平台，并与产品身份关联。 | 用户可以统一身份参与；私有和公共空间隔离；Community行为可关联产品采用；权限和隐私正确；搜索和通知可用；社区成为知识入口。 | NOT_RUN |
| 431 `community-content-question-and-knowledge-architecture` | G14-C | 组织问题、讨论、教程、Recipe、案例和最佳实践，使社区内容可发现和复用。 | 问题可快速找到；高质量答案可识别；内容按版本管理；社区知识可进入文档候选；重复工单减少；技术错误可及时纠正。 | NOT_RUN |
| 432 `community-moderation-trust-and-safety-manager` | G14-C | 治理垃圾信息、骚扰、恶意代码、敏感数据和供应链攻击。 | 举报处理及时；恶意内容无法扩散；误判可申诉；社区信任度维持；安全事件响应完整；Moderation可审计。 | NOT_RUN |
| 433 `community-contribution-and-reputation-system` | G14-C | 通过贡献、回答、验证、Recipe和活动建立可信声誉。 | 高质量贡献者可发现；声誉与实际质量相关；作弊受控；Badge支持用户选人和选资产；贡献者Retention提高；权限和声誉保持分离。 | NOT_RUN |
| 434 `community-event-hackathon-and-challenge-manager` | G14-C | 组织Recipe挑战、迁移Hackathon、社区Sprint和区域活动。 | 活动产生可复用资产；新贡献者增加；Submission安全；评审透明；Marketplace和文档获得内容；参与者转化为长期社区成员。 | NOT_RUN |
| 435 `support-community-and-documentation-knowledge-loop` | G14-C | 将支持工单、社区问题和文档反馈转为统一知识和产品改进。 | 重复问题减少；Support解决方案可复用；社区回答更准确；文档Gap可自动发现；产品缺陷有证据；用户获得闭环通知。 | NOT_RUN |
| 436 `marketplace-growth-orchestrator` | G14-D | 统一管理Marketplace发布者、资产、发现、交易、安装、使用和生态增长。 | 供给和需求漏斗可查询；高质量资产容易被发现；安装到成功使用可追踪；发布者获得反馈和收入；Marketplace安全可控；生态覆盖持续增加。 | NOT_RUN |
| 437 `marketplace-publisher-onboarding-manager` | G14-D | 帮助Vendor、Partner、客户和社区开发者成为Marketplace发布者。 | 发布者身份可信；财务和License信息完整；能使用Sandbox测试；发布权限符合级别；支持和更新责任明确；Onboarding转化可衡量。 | NOT_RUN |
| 438 `marketplace-asset-certification-and-quality-gate` | G14-D | 对Recipe、Adapter、Compatibility Runtime、模板和插件执行技术、安全和质量认证。 | 资产质量透明；企业用户可选择认证级别；恶意或低质量资产被阻止；更新兼容性可验证；认证状态可审计；质量门禁支持规模增长。 | NOT_RUN |
| 439 `marketplace-search-discovery-and-recommendation-engine` | G14-D | 根据语言、框架、版本、场景、质量和用户上下文推荐资产。 | Search成功率高；用户能找到兼容资产；推荐提高成功安装；高质量资产排名靠前；广告与自然结果区分；推荐原因可解释。 | NOT_RUN |
| 440 `marketplace-install-version-and-dependency-manager` | G14-D | 安全安装、升级、回滚和卸载Marketplace资产。 | 安装可预测；依赖闭包完整；升级和回滚成功；权限透明；Workspace不被破坏；资产使用可追踪。 | NOT_RUN |
| 441 `marketplace-pricing-promotion-and-revenue-share` | G14-D | 管理免费、付费、订阅、按使用和企业License资产。 | 买方可清楚理解费用；Publisher可预测收入；账单准确；退款和促销正确；Marketplace毛利可分析；地区价格可管理。 | NOT_RUN |
| 442 `marketplace-review-trust-and-abuse-manager` | G14-D | 管理评分、评价、举报、虚假交易、恶意资产和Publisher行为。 | 评价与真实使用关联；虚假评分受控；安全举报响应及时；用户能理解资产风险；Publisher可回复但不能操控；Marketplace信任提升。 | NOT_RUN |
| 443 `marketplace-supply-demand-network-effect-manager` | G14-D | 识别和增强Marketplace供给、覆盖、成功率和需求之间的网络效应。 | 高需求Gap持续减少；资产覆盖提高；Publisher获得明确需求；安装成功率提高；Marketplace使用推动产品采用；生态价值持续增强。 | NOT_RUN |
| 444 `internationalization-platform-architect` | G14-E | 建立语言、Locale、时区、文本方向和可扩展国际化架构。 | 产品界面可切换Locale；Plural和格式正确；RTL支持按计划；翻译缺失可检测；CLI和报告可本地化；I18n不会改变技术契约。 | NOT_RUN |
| 445 `localization-content-workflow-manager` | G14-E | 管理产品、文档、网站、Marketplace和支持内容的翻译、Review和发布。 | 核心内容翻译完整；Source和Translation版本关联；技术术语准确；UI无截断和错位；地区用户可理解；更新延迟可监控。 | NOT_RUN |
| 446 `terminology-glossary-translation-memory-and-style-guide` | G14-E | 统一产品、迁移、语言、框架、安全和商业术语。 | 关键术语一致；翻译效率提高；技术误解减少；多供应商输出一致；术语变更可追踪；地区语言习惯得到支持。 | NOT_RUN |
| 447 `locale-format-and-regional-user-experience-manager` | G14-E | 适配日期、时间、数字、货币、姓名、地址、电话和区域工作方式。 | 格式符合地区习惯；数据存储和显示分离；多币种显示正确；表单支持本地地址和姓名；时区错误为0；本地用户完成率提高。 | NOT_RUN |
| 448 `regional-legal-privacy-and-product-compliance-manager` | G14-E | 识别并落实不同地区的隐私、合同、数据驻留、营销和软件交付要求。 | 上线地区有合规清单；Mandatory要求落实；数据流和合同匹配；Consent和删除流程有效；区域风险有Owner；合规证据可导出。 | NOT_RUN |
| 449 `multi-currency-tax-and-regional-pricing-manager` | G14-E | 支持区域价格、币种、税务、发票和购买力差异。 | 客户可用本地币种购买；税额正确；发票符合地区要求；地区价格可审计；Partner报价一致；区域毛利可计算。 | NOT_RUN |
| 450 `regional-market-entry-assessor` | G14-F | 评估某地区是否值得进入，以及最适合的进入模式。 | 进入决策有数据；产品和合规Gap明确；进入模式合理；预算和阶段清晰；试点市场可选择；高风险地区可暂缓。 | NOT_RUN |
| 451 `regional-launch-playbook-manager` | G14-F | 将区域进入评估转化为90天、180天和一年Launch计划。 | Launch有阶段和Owner；Design Partner就绪；产品和内容本地化；支持和Partner可运行；Launch指标可追踪；经验可复制到下一地区。 | NOT_RUN |
| 452 `local-content-community-and-developer-program` | G14-F | 在目标地区建立本地语言内容、社区、活动和Developer Relations。 | 本地Organic和Community增长；地区开发者参与；内容产生Assessment；本地问题进入产品反馈；Ambassador和Partner协作；品牌在地区建立可信度。 | NOT_RUN |
| 453 `regional-channel-and-partner-replication-manager` | G14-F | 复制伙伴招募、认证、联合销售和交付模型到不同地区。 | 地区伙伴可标准入驻；认证和交付质量一致；商机登记和分成有效；本地客户覆盖提升；Partner-sourced Pipeline增长；模型可复制到更多地区。 | NOT_RUN |
| 454 `cloud-marketplace-and-technology-alliance-manager` | G14-F | 通过云市场、Git平台、模型Provider和技术厂商扩大分发。 | 客户可通过熟悉渠道购买；云账单准确；联合销售产生Pipeline；技术集成稳定；地区扩张得到渠道支持；Alliance经济性可衡量。 | NOT_RUN |
| 455 `regional-support-sla-and-operating-model` | G14-F | 建立本地时区、语言、严重度、升级和伙伴协同支持能力。 | 地区客户获得合同支持；语言和时区覆盖；Partner升级有效；数据边界遵守；SLA可衡量；支持成本可分析。 | NOT_RUN |
| 456 `regional-growth-dashboard-and-comparison-engine` | G14-F | 比较不同地区的流量、产品采用、Pipeline、伙伴、收入、留存和经济性。 | 地区表现可比较；高潜市场可识别；渠道差异可分析；资源投入可调整；区域增长风险可见；成功Playbook可复制。 | NOT_RUN |
| 457 `growth-cost-ltv-and-channel-economics-manager` | G14-F | 计算CAC、LTV、Payback、内容效率、Marketplace效率和区域扩张经济性。 | 渠道经济性可查询；CAC和Payback可信；低效增长动作可停止；Marketplace和区域投资可比较；LTV模型可回测；增长不破坏毛利。 | NOT_RUN |
| 458 `brand-trust-and-growth-risk-governance` | G14-F | 治理品牌主张、技术承诺、增长滥用、声誉、安全和地区风险。 | 品牌主张有证据；增长策略符合信任原则；滥用及时处理；Partner和地区团队行为受控；客户投诉可追踪；品牌风险进入管理层视图。 | NOT_RUN |
| 459 `growth-playbook-and-learning-repository` | G14-F | 沉淀实验、内容、渠道、社区、Marketplace和区域扩张的成功与失败经验。 | 团队不重复相同错误；成功增长策略可复制；地区Launch速度提高；新员工和伙伴可使用；Playbook有版本和Owner；Growth知识持续积累。 | NOT_RUN |
| 460 `batch-14-growth-and-ecosystem-conformance-gate` | G14-G | 综合产品增长、内容、开发者、社区、Marketplace和国际扩张结果，判断平台是否具备可持续规模化增长能力。 | 产品能自助产生首个价值；内容持续带来高质量用户；开发者可通过API、CLI和SDK构建；社区能够产生可信知识和贡献；Marketplace形成供需网络效应；产品可在多语言和多地区可靠使用；区域伙伴模型可复制；增长可持续且经济性可衡量。 | NOT_RUN |

## Final rule

No row may be closed by another domain's success. Skill 460 may return scalable-growth-ready only after G14-A through G14-F all pass, channel CAC and contribution margin are visible, all six supported motions are evidenced, the evidence pack is complete, and critical open growth risks equal zero.

