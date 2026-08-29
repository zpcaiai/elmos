# v2.0.0 → v3.0.0 增量

## 数量变化

- Meta-Skill：17 → 41；
- Atomic Skill：458 → 1310；
- 新增：24 个深度业务线包、852 个原子 Skill；
- 所有旧 Skill 补充 Owner、Business Line、Trigger/Negative Trigger、Dependency、Invariant、Failure Mode、Execution、Compatibility、Maturity 和 Support 契约。

## 新业务线包

- `17-repository-execution-os`：把超大仓库准入、环境复现、并行 Agent、工作区所有权、补丁合并、长任务恢复和交付证据收敛为可靠执行底座。（34 Skills）
- `18-java-spring-enterprise-modernization`：把 Struts、Servlet、JSP、Java EE、应用服务器和旧 Spring 仓库语义正确、行为等价地迁移到现代 Spring Boot 目标栈。（48 Skills）
- `19-cross-language-semantic-conversion`：通过 Semantic IR、语言能力画像、差分运行和渐进切换保持整库转换的类型、控制、并发、数据、协议与运维语义。（52 Skills）
- `20-sql-database-modernization`：覆盖 SQL 方言、Routine、Schema、数据、事务、计划、CDC 与零停机切换的端到端数据库现代化。（50 Skills）
- `21-project-generation-product-engineering`：从需求和非功能约束生成可构建、可测试、可部署、可运营、可计费和可认证的多语言完整项目。（44 Skills）
- `22-frontend-mobile-miniapp-modernization`：在 Web、移动端、Flutter 与微信/支付宝/抖音/小红书小程序之间保持组件、状态、导航、平台能力、视觉和交互语义。（44 Skills）
- `23-repository-refactoring-technical-debt`：对多语言仓库执行行为保持、可审阅、可回滚的架构重构、技术债治理和模块化演进。（32 Skills）
- `24-api-event-integration-modernization`：现代化 REST、GraphQL、gRPC、SOAP、实时连接、事件流和批量集成，同时保持协议、交付和消费者兼容。（32 Skills）
- `25-data-engineering-lakehouse-analytics`：生成和现代化批流一体、CDC、湖仓、编排、数据质量、血缘、治理、特征与分析平台。（40 Skills）
- `26-cloud-native-devops-platform-engineering`：把应用容器化、Kubernetes、IaC、CI/CD、GitOps、多云、私有化、灾备和平台自服务能力纳入自动生成与现代化。（38 Skills）
- `27-test-quality-assurance-factory`：为生成、转换、重构和迁移任务自动建立测试、Oracle、差分、性能、安全、恢复和 E0-E5 认证闭环。（44 Skills）
- `28-security-compliance-supply-chain`：对代码、仓库、工具、模型、数据、部署和供应链执行零信任、隐私、攻击验证与可审计控制。（40 Skills）
- `29-performance-reliability-cost-engineering`：以真实工作负载和 SLO 为依据，联合优化应用、数据库、前端、数据平台、AI 推理的性能、可靠性和单位经济性。（32 Skills）
- `30-architecture-documentation-ide`：提供大型仓库在线阅读、语义导航、架构恢复、变换过程可视化、在线调试和可验证文档生成。（32 Skills）
- `31-ai-agent-rag-ml-engineering`：生成、迁移和认证 RAG、Agent、多 Agent、模型服务、私有训练和 AI 应用项目，保持供应商可替换与生产安全。（46 Skills）
- `32-legacy-mainframe-enterprise-modernization`：对 COBOL、JCL、CICS、IMS、RPG、ABAP、PowerBuilder、VB6、.NET Framework 等遗留系统实施可验证渐进现代化。（40 Skills）
- `33-industrial-iot-edge-robotics`：生成和现代化工业协议、设备、SCADA、ROS、数字孪生、边缘部署、实时与功能安全软件。（32 Skills）
- `34-language-runtime-adapters`：为 Elmos 支持的语言、编译器、包管理器和构建系统提供统一解析、生成、执行、调试和认证适配层。（36 Skills）
- `35-database-engine-adapters`：为关系型、分布式、仓库、文档、时序、图、搜索和缓存数据库提供可验证的语义与运维适配器。（24 Skills）
- `36-framework-runtime-adapters`：为主流后端、前端、移动端、数据、云和 AI 框架提供统一扫描、生成、转换、测试与版本兼容适配。（36 Skills）
- `37-cloud-platform-adapters`：为公有云、私有云、Kubernetes、Serverless、裸机与边缘目标生成可移植、可退出、可认证的部署适配层。（16 Skills）
- `38-golden-route-customer-delivery`：把售前评估、试点、范围、迁移波次、验收、证据、SLA、移交和 LTS 组织为可重复付费交付流程。（24 Skills）
- `39-product-commercialization-marketplace`：将 Elmos 能力包装为可授权、可计量、可定价、可结算、可市场化并具备单位经济性的商业产品。（16 Skills）
- `40-regulated-industry-assurance`：为金融、医疗、工业安全、公共部门等高要求场景建立验证、控制、电子记录、模型风险和安全案例证据。（20 Skills）

## 结构升级

- 新增业务线 Catalog、技术支持矩阵、Pack 依赖图；
- 新增 v3 Skill Schema、Repository Execution、Transformation、Adapter、Golden Route、Verification、Customer Acceptance Schema；
- 新增业务线 Admission、Transformation Risk、Golden Route、Adapter Compatibility、Evidence Invalidation 策略；
- 新增核心业务线端到端 Pipeline；
- 校验器升级为真实 JSON Schema、依赖、Meta、评测、Policy、Hash 和覆盖校验。
## 交付前硬化

- 为全部 1,310 项 Skill 统一补齐 31,440 条最低激活、负例、歧义与对抗测试夹具；
- 为全部 Skill 补齐 Conformance Manifest；
- 将核心 Bootstrap 能力依赖重构为 DAG，消除自依赖与循环依赖；
- 校验器增加依赖环、评测数量、空文件、Meta 激活用例和可选 SHA-256 验证。

