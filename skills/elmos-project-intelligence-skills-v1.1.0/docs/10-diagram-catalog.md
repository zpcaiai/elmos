# 图表与可视化目录

## 1. 统一要求

- 所有图先生成 `Diagram Spec`，再渲染；
- 每个节点/边有 stable ID、语义类型、revision、claim/evidence refs；
- 自动布局与语义分离；
- 支持 overview + drill-down；
- 支持搜索、过滤、折叠、下钻和深链；
- 支持人工重命名、分组、布局锁、语义锁、评论和审批；
- 支持 SVG/PNG/PDF 及至少一种可编辑源格式；
- 大图不强制塞入一页，提供交互视图和分页；
- 低置信度、未知、运行时观察和设计目标视觉区分。

## 2. 图表目录

| # | 图表 | 视角 | 用途 | 主要节点/关系 | 推荐输出 |
|---:|---|---|---|---|---|
| 1 | 系统上下文图 | C4 L1 | 用户、外部系统和系统边界 | Project/ExternalSystem/Actor | Structurizr/Mermaid/SVG |
| 2 | 容器图 | C4 L2 | 前端、后端、数据库、消息和外部依赖 | Service/Database/Queue | Structurizr/PlantUML/SVG |
| 3 | 组件图 | C4 L3 | 服务内部组件与接口 | Component/Symbol/API | Structurizr/PlantUML |
| 4 | 代码图 | C4 L4 | 类、接口、函数和关键依赖 | Type/Function | PlantUML/Graphviz |
| 5 | 模块依赖图 | Architecture | 模块及循环依赖 | Module/DEPENDS_ON | Graphviz/Cytoscape |
| 6 | 分层架构图 | Architecture | 层和越界调用 | Layer/Symbol | Mermaid/Graphviz |
| 7 | 六边形架构图 | Architecture | Port/Adapter 与核心 | Component/Port | Mermaid/Structurizr |
| 8 | 插件架构图 | Architecture | 核心、扩展点和插件 | Plugin/ExtensionPoint | Graphviz |
| 9 | 多仓库系统图 | Architecture | 仓库、服务和交付单元 | Repository/Service | Cytoscape/SVG |
| 10 | 当前—目标架构对比 | Architecture Diff | 当前、目标和迁移阶段 | ArchitectureModel | Custom/SVG |
| 11 | 功能思维导图 | Product | 业务域、能力、功能和代码映射 | Capability/Feature | Markmap/JSON |
| 12 | 业务能力地图 | Product | 能力与价值流 | Capability/Domain | Cytoscape/SVG |
| 13 | 用例图 | Product | Actor 与 Use Case | Actor/Feature | PlantUML |
| 14 | 用户旅程图 | Product | 用户阶段、动作和痛点 | Journey/Step | Custom/SVG |
| 15 | BPMN 业务流程图 | Flow | 角色、网关、事件和任务 | Flow/Step | BPMN XML |
| 16 | 泳道图 | Flow | 跨角色/系统协作 | Flow/Actor | Mermaid/Custom |
| 17 | 时序图 | Flow | 调用顺序和异步消息 | Step/API/Event | PlantUML/Mermaid |
| 18 | 状态机图 | Flow | 状态和转移条件 | State/Transition | PlantUML/Mermaid |
| 19 | 异常与补偿图 | Flow | 错误、重试、DLQ、Saga | Step/Error/Compensation | Mermaid |
| 20 | 决策树 | Flow | 业务规则和条件 | Decision/Branch | Graphviz |
| 21 | ER 图 | Data | 表、字段和关系 | Table/Column | PlantUML/Graphviz |
| 22 | 数据流图 DFD | Data/Security | 进程、存储、外部实体和信任边界 | Process/DataStore | Custom/SVG |
| 23 | 数据血缘图 | Data | 字段/资产来源、转换和去向 | DataAsset/Lineage | Cytoscape |
| 24 | CRUD 矩阵 | Data | 模块对数据的读写 | Module/DataAsset | HTML/CSV |
| 25 | 数据生命周期图 | Data | 创建、使用、归档和删除 | DataAsset/State | Mermaid |
| 26 | 缓存拓扑图 | Data | 缓存读写、更新和失效 | Cache/Service | Graphviz |
| 27 | ETL/ELT 流程图 | Data | 数据处理作业 | Job/DataAsset | BPMN/Mermaid |
| 28 | API 拓扑图 | Integration | API Provider/Consumer | API/Service | Cytoscape |
| 29 | 事件拓扑图 | Integration | Topic、Producer、Consumer、DLQ | Event/Topic | Cytoscape |
| 30 | Webhook 流程图 | Integration | 外部回调、验签和幂等 | API/ExternalSystem | Sequence |
| 31 | 版本兼容图 | Integration | API/Event 版本和消费者 | Contract/Consumer | Custom |
| 32 | 部署拓扑图 | Deployment | 实例、节点、区域和依赖 | DeploymentUnit/Node | Structurizr |
| 33 | Kubernetes 资源图 | Deployment | Deployment/Service/Ingress/Secret | K8sResource | Graphviz |
| 34 | 云资源架构图 | Deployment | VPC、计算、存储和托管服务 | CloudResource | Custom/SVG |
| 35 | 网络与信任边界图 | Security | 网关、子网、防火墙和区域 | Network/TrustBoundary | Custom |
| 36 | CI/CD 流程图 | Operations | Build/Test/Scan/Deploy/Rollback | Pipeline/Stage | Mermaid |
| 37 | 可观测性拓扑图 | Operations | 日志、指标、Trace 流 | TelemetryComponent | Graphviz |
| 38 | 故障传播图 | Reliability | 依赖故障与影响半径 | Service/Failure | Cytoscape |
| 39 | 容灾架构图 | Reliability | 主备、双活、备份和恢复 | Region/Replica | Structurizr |
| 40 | 认证授权流程图 | Security | OIDC/Token/RBAC | Identity/Permission | Sequence |
| 41 | RBAC 权限图 | Security | 角色、资源和动作 | Role/Policy | Graphviz |
| 42 | 威胁模型图 | Security | 资产、威胁、控制和残余风险 | Threat/Control | Custom |
| 43 | 攻击路径图 | Security | 入口到敏感资产的可达路径 | AttackStep | Cytoscape |
| 44 | 敏感数据流图 | Security | 敏感字段经过的组件和边界 | SensitiveData/DFD | Custom |
| 45 | 代码热点图 | Quality | 变更频率、复杂度和缺陷 | File/Metric | Heatmap |
| 46 | 技术债热力图 | Quality | 模块风险分布 | Module/Risk | Heatmap |
| 47 | 测试覆盖图 | Quality | 功能/代码/流程覆盖 | Test/Coverage | Custom |
| 48 | 源—IR—目标映射图 | Elmos Conversion | 语言转换路径 | Source/IR/Target | Custom |
| 49 | 规则命中图 | Elmos Conversion | 规则、代码和结果 | Rule/Mapping | Cytoscape |
| 50 | 转换置信度热图 | Elmos Conversion | 低置信度区域 | Module/Confidence | Heatmap |
| 51 | 编译失败分布图 | Elmos Conversion | 错误类型与模块 | Diagnostic/Module | Charts |
| 52 | 自动修复过程图 | Elmos Conversion | 失败、补丁、重测迭代 | RepairAttempt | Flow |
| 53 | 行为等价证据图 | Elmos Conversion | 源目标输入输出/副作用差异 | Evidence/Diff | Custom |
| 54 | 迁移进度图 | Elmos Conversion | 模块、路径和认证状态 | Module/Status | Dashboard |
| 55 | Strangler 替换图 | Elmos Conversion | 流量和模块渐进切换 | Old/New/Route | Structurizr |
| 56 | E1–E5 认证矩阵 | Certification | 门禁、证据和状态 | Gate/Evidence | Matrix |

## 3. Diagram Spec 最小结构

```yaml
schema_version: 1
diagram_id:
type: c4-container
project_id:
revision_id:
view:
  filters: []
  grouping: []
nodes:
  - id:
    kind:
    label:
    semantic:
    evidence_refs: []
    confidence:
    lock:
      semantic: false
      layout: false
edges:
  - id:
    source:
    target:
    kind:
    label:
    evidence_refs: []
layout:
  engine: elk
  positions: {}
```

## 4. 图表质量门禁

- 无悬空证据引用；
- 无重复 stable ID；
- 语义边符合图 profile；
- 文本不溢出；
- SVG 已消毒；
- 无任意 include/网络访问；
- 图例包含可信度和边类型；
- 关键节点可回代码；
- 视觉快照和结构快照通过；
- 人工锁定再生成后保留。
