// Top-level helpers and constants
try { const precisionIcons = ["route", "layers", "code", "workflow", "database", "test", "shield", "spark"]; } catch(e) {}
try { const precisionMaturityCounts = precisionMigrationSummary.maturityCounts; } catch(e) {}
try { const precisionExecutableCount = ["ADAPTER_DECLARED", "ADAPTER_CONTRACT_PASSED", "LOCAL_EXECUTED", "HOLDOUT_PASSED", "EXTERNAL_VERIFIED", "CERTIFIED"]
    .reduce((total, maturity) => total + (precisionMaturityCounts[maturity] ?? 0), 0); } catch(e) {}
try { const precisionRanges = precisionMigrationPhases.map((phase, index) => ({
    range: phase.batchRange.replace("-", "–"),
    title: phase.phase.replace(/^[A-L]\s+/, ""),
    count: phase.skillCount,
    source: `${phase.localExecutedCount} local executed / ${phase.skillCount} child Skills`,
    status: Number(phase.localExecutedCount) === Number(phase.skillCount) ? "LOCAL_EXECUTED" : Number(phase.installedOnlyCount) === 0 ? "ADAPTER_DECLARED" : "INSTALLED",
    icon: precisionIcons[index % precisionIcons.length],
    note: `${phase.localExecutedCount} 个条目已运行受控本地 handler；原生工具链广度、独立 holdout 与外部证据仍为 NOT_RUN。`,
})); } catch(e) {}
try { const foundryRanges = [
    { range: "Pack 00–04", title: "基础合同、知识摄取与语意代码图", count: 160, source: "Foundry v3.0.0", status: "READY", icon: "layers", note: "包含契约定义、多源摄取、符号索引、检索与短期/长期经验飞轮。" },
    { range: "Pack 05–08", title: "技能工坊、数据集、私有模型与RL", count: 135, source: "Foundry v3.0.0", status: "READY", icon: "spark", note: "支持 SFT/DPO/RLVR 训练、能力提取、蒸馏与执行沙箱。" },
    { range: "Pack 09–12", title: "E0–E5 证明、推理路由、安全与FinOps", count: 135, source: "Foundry v3.0.0", status: "READY", icon: "shield", note: "SMT 形式化验证、自适应缓存、越狱防范与用量成本核算。" },
    { range: "Pack 13–16", title: "商业多租户、人机协作、行业包与自演化", count: 125, source: "Foundry v3.0.0", status: "READY", icon: "workflow", note: "多租户隔离、合规操作审计、能力包沉淀与自我演化流水线。" },
    { range: "Pack 17–24", title: "企业级 Java/Spring/跨语言/数据库/前端", count: 260, source: "Foundry v3.0.0", status: "READY", icon: "code", note: "涵盖 Spring 翻新、30 方向跨语言转换、SQL 迁移与微前端改造。" },
    { range: "Pack 25–33", title: "湖仓大数据、DevOps、质量工厂与工控", count: 290, source: "Foundry v3.0.0", status: "READY", icon: "database", note: "涵盖 Dataflow、K8s 编排、变异测试、大型主机与工业边缘总线。" },
    { range: "Pack 34–40", title: "全语言/数据库/云平台适配器与受监管合规", count: 246, source: "Foundry v3.0.0", status: "READY", icon: "route", note: "涵盖所有主流语言/国产数据库/多云驱动与 ISO/IEC 行业合规标准。" },
]; } catch(e) {}
try { const polyglotRanges = [
    { range: "Batch A–E", title: "摄取、UIR 规范化、AST 适配器与核心/UI转换", count: 88, source: "Polyglot v3.0.0", status: "READY", icon: "code", note: "支持 28 种技术表面与多端 UI 组件语义映射。" },
    { range: "Batch F–I", title: "数据库/存储过程、遗留系统集成与交付编排", count: 80, source: "Polyglot v3.0.0", status: "READY", icon: "database", note: "DDL/DML 语义转换、COBOL/Mainframe 桥接与交付清单生成。" },
    { range: "Batch J–N", title: "语法保真、类型代数、CFG数据流与行为Oracle", count: 72, source: "Polyglot v3.0.0", status: "READY", icon: "test", note: "静态分析断言、类型保真性证明与确定性双向执行。" },
    { range: "Batch O–R", title: "语料库治理、原生实验室、SMT形式化证明与Fuzzing", count: 60, source: "Polyglot v3.0.0", status: "READY", icon: "shield", note: "Z3/CVC5 SMT 求解、形式化契约与变异引导差分 Fuzzing。" },
]; } catch(e) {}
try { const ranges = {
    foundry: foundryRanges,
    polyglot: polyglotRanges,
    migration: [
        { range: "M1–M28", title: "基础迁移能力", count: 448, source: "Normalized recovery", status: "REVIEW", icon: "layers", note: "精确原始包不可用，保留来源不完整边界。" },
        { range: "M29–M33", title: "精确迁移认证包", count: 102, source: "Imported original", status: "READY", icon: "route", note: "语言、框架、数据库、客户端与 Cloud 契约。" },
        { range: "M34–M45", title: "规模与成熟产品包", count: 270, source: "Repository contracts", status: "READY", icon: "shield", note: "结构和本地门禁就绪，现场证据仍未运行。" },
    ],
    precision: precisionRanges,
    product: [
        { range: "B34–B39", title: "商业化核心控制", count: 236, source: "Complete source", status: "READY", icon: "shield", note: "租户、SCM、Runner、证据、授权与 Finance。" },
        { range: "B40A", title: "对话设计", count: 16, source: "Approved design", status: "READY", icon: "spark", note: "具有已批准的 conversation-design 来源。" },
        { range: "B40B–B55C", title: "企业领域规划版", count: 752, source: "Generated planning", status: "REVIEW", icon: "file", note: "需要领域负责人完善，不能宣称生产完成。" },
    ],
}; } catch(e) {}
try { const provenance = [
    { count: 1351, label: "Foundry v3.0.0 官方底座", note: "41 Packs / 1,310 原子 / 41 Meta Skills", tone: "green", status: "READY" },
    { count: 300, label: "Polyglot 语义编译器", note: "18 Batches (A–R) 形式化保障", tone: "green", status: "READY" },
    { count: 624, label: "默认可安装标准包", note: "权威、仓库或已批准来源", tone: "green", status: "READY" },
    { count: 448, label: "规范化恢复能力", note: "M1–M28 来源不完整", tone: "amber", status: "REVIEW" },
    { count: 752, label: "生成式规划领域包", note: "B40B–B55C 待领域完善", tone: "violet", status: "EXPERIMENTAL" },
]; } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    namespace: "foundry",
    searchQuery: "",
    items: null,
  },
  lifetimes: {
    attached() {
      const setNamespace = (val) => { this.setData({ namespace: typeof val === "function" ? val(this.data.namespace) : val }); };
      const setSearchQuery = (val) => { this.setData({ searchQuery: typeof val === "function" ? val(this.data.searchQuery) : val }); };
    },
    detached() {
    },
  },
  methods: {
  },
});
