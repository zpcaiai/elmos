// Top-level helpers and constants
try { const reviewQueue = [
    { id: "EVD-1042", title: "SCM Workspace admission", subject: "order-platform / commit a4f2…91c", stage: "B35", status: "NOT_RUN", owner: "Source owner" },
    { id: "EVD-1041", title: "Runner capability attestation", subject: "macos-arm64-private-01", stage: "B36", status: "BLOCKED", owner: "Platform security" },
    { id: "EVD-1038", title: "Evidence pack assurance", subject: "migration-run / pack 018", stage: "B37", status: "REVIEW", owner: "Independent judge" },
    { id: "EVD-1045", title: "Foundry v3.0.0 Model Foundry Pack", subject: "qwen2.5-coder-32b-distill", stage: "Foundry-07", status: "READY", owner: "Model Foundry" },
    { id: "EVD-1046", title: "Polyglot SMT Formal Verification", subject: "java-to-csharp-golden-route", stage: "Batch-Q", status: "READY", owner: "Formal Assurance" },
]; } catch(e) {}
try { const commercialKernels = [
    { id: "K1", name: "功能运行时", skills: 10, status: "READY", desc: "Sandbox execution, context budgeting, durable events" },
    { id: "K2", name: "Repository Intelligence", skills: 10, status: "READY", desc: "Semantic AST indexing, symbol resolution, call graph" },
    { id: "K3", name: "Transformation", skills: 10, status: "READY", desc: "Rule DSL, bidirectional lowering, AST rewrites" },
    { id: "K4", name: "Build & Execution", skills: 9, status: "READY", desc: "Hermetic container toolchains, compiler diagnostic mapping" },
    { id: "K5", name: "Verification", skills: 14, status: "READY", desc: "SMT solver obligations, differential fuzzing, metamorphic tests" },
    { id: "K6", name: "Security & Governance", skills: 10, status: "READY", desc: "Zero-trust policies, secret egress, SLSA provenance" },
    { id: "K7", name: "Database & Data", skills: 10, status: "READY", desc: "DDL/DML transpilation, routine CFG, CDC reconciliation" },
    { id: "K8", name: "Observability & Evolution", skills: 12, status: "READY", desc: "OTel traces, cost telemetry, self-evolving recipes" },
]; } catch(e) {}
try { const foundryHighlights = [
    { pack: "00–04", name: "Foundation & Knowledge", skills: 98, desc: "Contracts, ingestion, semantic intelligence, memory" },
    { pack: "05–08", name: "能力底座与强化训练", skills: 121, desc: "功能运行时、数据集工坊、私有模型工坊与强化学习" },
    { pack: "09–12", name: "Assurance & Governance", skills: 128, desc: "E0–E5 certification, serving gateway, security, finops" },
    { pack: "13–16", name: "Platform & Self-Evolution", skills: 111, desc: "Multi-tenant control plane, operations, self-evolution" },
    { pack: "17–33", name: "Enterprise Route Specialization", skills: 676, desc: "Spring, Cross-language, Database, Mainframe, IoT" },
    { pack: "34–40", name: "Adapters & Industrial Assurance", skills: 217, desc: "Language/DB/Cloud adapters, regulated compliance" },
]; } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    payload: "{\n    source: \"REPOSITORY_CONTRACT\",\n    fetchedAt: new Date(0).toISOString(),\n    namespace: \"Product Batch B34-B38\",\n    decisionCeiling: \"READY_FOR_EXTERNAL_GATE_OR_HUMAN_DECISION\",\n    externalExecutionEvidence: \"NOT_RUN\",\n    stages: fallbackStages,\n    note: \"正在读取控制面能力…\",\n  }",
    selected: "B37",
    refreshing: false,
  },
  lifetimes: {
    attached() {
      const setPayload = (val) => { this.setData({ payload: typeof val === "function" ? val(this.data.payload) : val }); };
      const setSelected = (val) => { this.setData({ selected: typeof val === "function" ? val(this.data.selected) : val }); };
      const setRefreshing = (val) => { this.setData({ refreshing: typeof val === "function" ? val(this.data.refreshing) : val }); };
      // Lifecycle effect effect_0
      (async () => {
        try {
          refresh();
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
    },
    detached() {
    },
  },
  methods: {
    moveStage(event, index) {
      try {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
        return;
    event.preventDefault();
    const last = payload.stages.length - 1;
    const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? last : event.key === "ArrowRight" ? (index + 1) % payload.stages.length : (index - 1 + payload.stages.length) % payload.stages.length;
    const nextStage = payload.stages[nextIndex];
    setSelected(nextStage.batch);
    requestAnimationFrame(() => document.getElementById(`trust-tab-${nextStage.batch}`)?.focus());
      } catch (err) {
        console.warn("moveStage execution warning:", err);
      }
    },
  },
});
