"use client";

import { useCallback, useEffect, useState, type KeyboardEvent } from "react";
import { Icon } from "../components/Icon";
import { StatusChip } from "../components/StatusChip";
import { productStages as fallbackStages } from "../lib/catalog";
import type { ProductCapabilityResponse, ProductStage } from "../lib/contracts";

const reviewQueue = [
  { id: "EVD-1042", title: "SCM Workspace admission", subject: "order-platform / commit a4f2…91c", stage: "B35", status: "NOT_RUN", owner: "Source owner" },
  { id: "EVD-1041", title: "Runner capability attestation", subject: "macos-arm64-private-01", stage: "B36", status: "BLOCKED", owner: "Platform security" },
  { id: "EVD-1038", title: "Evidence pack assurance", subject: "migration-run / pack 018", stage: "B37", status: "REVIEW", owner: "Independent judge" },
  { id: "EVD-1045", title: "Foundry v3.0.0 Model Foundry Pack", subject: "qwen2.5-coder-32b-distill", stage: "Foundry-07", status: "READY", owner: "Model Foundry" },
  { id: "EVD-1046", title: "Polyglot SMT Formal Verification", subject: "java-to-csharp-golden-route", stage: "Batch-Q", status: "READY", owner: "Formal Assurance" },
];

const commercialKernels = [
  { id: "K1", name: "功能运行时", skills: 10, status: "READY", desc: "Sandbox execution, context budgeting, durable events" },
  { id: "K2", name: "Repository Intelligence", skills: 10, status: "READY", desc: "Semantic AST indexing, symbol resolution, call graph" },
  { id: "K3", name: "Transformation", skills: 10, status: "READY", desc: "Rule DSL, bidirectional lowering, AST rewrites" },
  { id: "K4", name: "Build & Execution", skills: 9, status: "READY", desc: "Hermetic container toolchains, compiler diagnostic mapping" },
  { id: "K5", name: "Verification", skills: 14, status: "READY", desc: "SMT solver obligations, differential fuzzing, metamorphic tests" },
  { id: "K6", name: "Security & Governance", skills: 10, status: "READY", desc: "Zero-trust policies, secret egress, SLSA provenance" },
  { id: "K7", name: "Database & Data", skills: 10, status: "READY", desc: "DDL/DML transpilation, routine CFG, CDC reconciliation" },
  { id: "K8", name: "Observability & Evolution", skills: 12, status: "READY", desc: "OTel traces, cost telemetry, self-evolving recipes" },
];

const foundryHighlights = [
  { pack: "00–04", name: "Foundation & Knowledge", skills: 98, desc: "Contracts, ingestion, semantic intelligence, memory" },
  { pack: "05–08", name: "能力底座与强化训练", skills: 121, desc: "功能运行时、数据集工坊、私有模型工坊与强化学习" },
  { pack: "09–12", name: "Assurance & Governance", skills: 128, desc: "E0–E5 certification, serving gateway, security, finops" },
  { pack: "13–16", name: "Platform & Self-Evolution", skills: 111, desc: "Multi-tenant control plane, operations, self-evolution" },
  { pack: "17–33", name: "Enterprise Route Specialization", skills: 676, desc: "Spring, Cross-language, Database, Mainframe, IoT" },
  { pack: "34–40", name: "Adapters & Industrial Assurance", skills: 217, desc: "Language/DB/Cloud adapters, regulated compliance" },
];

export function CommercializationConsole() {
  const [payload, setPayload] = useState<ProductCapabilityResponse>({
    source: "REPOSITORY_CONTRACT",
    fetchedAt: new Date(0).toISOString(),
    namespace: "Product Batch B34-B38",
    decisionCeiling: "READY_FOR_EXTERNAL_GATE_OR_HUMAN_DECISION",
    externalExecutionEvidence: "NOT_RUN",
    stages: fallbackStages,
    note: "正在读取控制面能力…",
  });
  const [selected, setSelected] = useState("B37");
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(() => {
    setRefreshing(true);
    fetch("/api/capabilities/product")
      .then((response) => response.ok ? response.json() as Promise<ProductCapabilityResponse> : Promise.reject())
      .then(setPayload)
      .catch(() => setPayload((current) => ({ ...current, note: "能力 API 不可用；继续显示仓库契约。" })))
      .finally(() => setRefreshing(false));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const selectedStage = payload.stages.find((stage) => stage.batch === selected) ?? payload.stages[0];
  const enforcedCount = payload.stages.flatMap((stage) => stage.checks).filter((check) => check.status === "READY" || check.status === "ENFORCED").length;
  const unresolvedCount = payload.stages.flatMap((stage) => stage.checks).filter((check) => check.status === "BLOCKED" || check.status === "NOT_RUN" || check.status === "NOT_CONFIGURED").length;
  const fetchedAt = payload.fetchedAt === new Date(0).toISOString()
    ? "等待首次刷新"
    : new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date(payload.fetchedAt));

  function moveStage(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const last = payload.stages.length - 1;
    const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? last : event.key === "ArrowRight" ? (index + 1) % payload.stages.length : (index - 1 + payload.stages.length) % payload.stages.length;
    const nextStage = payload.stages[nextIndex];
    setSelected(nextStage.batch);
    requestAnimationFrame(() => document.getElementById(`trust-tab-${nextStage.batch}`)?.focus());
  }

  return (
    <div className="page-stack control-page">
      <section className="page-header control-header">
        <div>
          <span className="overline">ENTERPRISE COMMERCIAL CONTROL PLANE · v3.0.0</span>
          <h1>商业化控制面与能力内核</h1>
          <p>整合 8 大商业内核 (K1–K8)、工程翻新底座（41 个能力域、1,351 项功能）与 18 批次多语言编译器控制链。</p>
        </div>
        <div className="header-actions">
          <span className="environment-selector"><i />环境：本地工程契约</span>
          <button className="button button-secondary" onClick={refresh} disabled={refreshing}>
            <Icon name="refresh" size={16} className={refreshing ? "spinning" : undefined} />刷新能力
          </button>
        </div>
      </section>

      <section className="metric-grid metric-grid-four" aria-label="控制面摘要">
        <article className="metric-card"><span>商业能力内核</span><strong>8 (K1–K8)</strong><small>85 项商业扩展功能</small></article>
        <article className="metric-card"><span>工程翻新底座</span><strong>1,351 项功能</strong><small>41 个能力域 (v3.0.0)</small></article>
        <article className="metric-card"><span>多语言语义编译</span><strong>784 Routes</strong><small>18 个 Batches (A–R)</small></article>
        <article className="metric-card"><span>决策上限</span><strong className="metric-word">Gate / Human</strong><small>不批准、不执行</small></article>
      </section>

      <section className="source-notice" role="status">
        <Icon name={payload.source === "LIVE_API" ? "check" : "clock"} size={16} />
        <span>{payload.note}</span>
        <small className="source-freshness">最近刷新 {fetchedAt}</small>
        <StatusChip status={payload.source} compact />
      </section>

      {/* Commercial Kernels Matrix */}
      <section className="surface-card" aria-labelledby="kernels-title">
        <div className="section-heading compact-heading">
          <div><span className="overline">COMMERCIAL CAPABILITY KERNELS (K1–K8)</span><h2 id="kernels-title">八大商业能力内核</h2></div>
          <StatusChip status="READY" compact />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 mt-3">
          {commercialKernels.map((k) => (
            <div key={k.id} className="p-3 rounded-lg border border-border bg-card/60 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <strong className="text-sm font-semibold text-primary">{k.id} · {k.name}</strong>
                  <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary font-mono">{k.skills} skills</span>
                </div>
                <p className="text-xs text-muted-foreground">{k.desc}</p>
              </div>
              <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                <span>状态: {k.status}</span>
                <Icon name="check" size={13} className="text-emerald-500" />
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Foundry v3.0.0 Highlights */}
      <section className="surface-card" aria-labelledby="foundry-title">
        <div className="section-heading compact-heading">
          <div><span className="overline">工程翻新底座 v3.0.0</span><h2 id="foundry-title">知识 · 能力 · 模型底座（41 个能力域）</h2></div>
          <span className="text-xs px-2 py-0.5 rounded bg-violet-500/10 text-violet-400 font-mono">合计 1,351 项功能</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mt-3">
          {foundryHighlights.map((f) => (
            <div key={f.pack} className="p-3 rounded-lg border border-border bg-card/40">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-mono text-muted-foreground">Pack {f.pack}</span>
                <strong className="text-xs text-emerald-400">{f.skills} 项功能</strong>
              </div>
              <strong className="text-sm font-medium block">{f.name}</strong>
              <p className="text-xs text-muted-foreground mt-1">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="trust-chain" aria-labelledby="trust-chain-title">
        <div className="section-heading compact-heading"><div><span className="overline">TRUST CHAIN</span><h2 id="trust-chain-title">从身份到执行回执</h2></div><span className="quiet-label">点击任一阶段查看检查项</span></div>
        <div className="trust-steps" role="tablist" aria-label="商业化可信链阶段">
          {payload.stages.map((stage, index) => (
            <div className="trust-step-wrap" key={stage.batch}>
              <button id={`trust-tab-${stage.batch}`} className={`trust-step ${selected === stage.batch ? "selected" : ""}`} role="tab" aria-selected={selected === stage.batch} aria-controls="trust-stage-panel" tabIndex={selected === stage.batch ? 0 : -1} onClick={() => setSelected(stage.batch)} onKeyDown={(event) => moveStage(event, index)}>
                <span className="trust-step-icon"><Icon name={stage.icon} size={20} /></span>
                <span><small>{stage.batch}</small><strong>{stage.shortTitle}</strong></span>
                <StatusChip status={stage.status} compact />
              </button>
              {index < payload.stages.length - 1 && <span className="step-connector"><Icon name="arrow" size={15} /></span>}
            </div>
          ))}
        </div>
      </section>

      <section className="control-grid">
        <div className="surface-card stage-detail" id="trust-stage-panel" role="tabpanel" aria-labelledby={`trust-tab-${selectedStage.batch}`} tabIndex={0}>
          <div className="stage-detail-heading">
            <span className="large-stage-icon"><Icon name={selectedStage.icon} size={23} /></span>
            <div><span className="overline">{selectedStage.batch} · {selectedStage.subtitle}</span><h2>{selectedStage.title}</h2></div>
            <StatusChip status={selectedStage.status} />
          </div>
          <div className="check-list">
            {selectedStage.checks.map((check) => <div className="check-row" key={check.label}>
              <span className={`check-dot dot-${check.status.toLowerCase().replaceAll("_", "-")}`}><Icon name={check.status === "READY" || check.status === "ENFORCED" ? "check" : check.status === "BLOCKED" ? "lock" : "clock"} size={14} /></span>
              <div><strong>{check.label}</strong><small>{check.detail}</small></div>
              <StatusChip status={check.status} compact />
            </div>)}
          </div>
          <div className="restriction-block"><span className="overline">NON-NEGOTIABLE</span>{selectedStage.restrictions.map((restriction) => <p key={restriction}><Icon name="shield" size={15} />{restriction}</p>)}</div>
        </div>

        <aside className="surface-card decision-card">
          <div className="decision-card-top"><span className="decision-symbol"><Icon name="lock" size={20} /></span><StatusChip status="BLOCKED" compact /></div>
          <span className="overline">CURRENT DECISION</span><h2>拒绝执行副作用</h2>
          <p>当前只有结构与本地契约证据。没有外部 Runner、独立 Judge 或 PEP 回执，因此不能展示为可发布。</p>
          <dl className="decision-facts"><div><dt>控制面输出</dt><dd>READY / BLOCKED</dd></div><div><dt>外部执行</dt><dd className="warning-text">NOT_RUN</dd></div><div><dt>认证 / 批准</dt><dd>FALSE</dd></div></dl>
          <div className="decision-footer"><Icon name="shield" size={16} /><span>缺少上下文、错误或不支持的义务都会安全降级为 DENY。</span></div>
        </aside>
      </section>

      <section className="surface-card queue-card">
        <div className="card-heading"><div><span className="overline">ASSURANCE QUEUE</span><h2>证据审阅队列</h2></div><span className="quiet-label">合成演示数据 · 不含客户内容</span></div>
        <div className="queue-table" role="table" aria-label="证据审阅队列">
          <div className="queue-head" role="row"><span role="columnheader">事项</span><span role="columnheader">对象</span><span role="columnheader">阶段</span><span role="columnheader">负责人</span><span role="columnheader">状态</span></div>
          {reviewQueue.map((item) => <div className="queue-row" role="row" key={item.id}><span role="cell" data-label="事项"><small>{item.id}</small><strong>{item.title}</strong></span><span role="cell" data-label="对象">{item.subject}</span><span role="cell" data-label="阶段"><b className="batch-pill">{item.stage}</b></span><span role="cell" data-label="负责人">{item.owner}</span><span role="cell" data-label="状态"><StatusChip status={item.status} compact /></span></div>)}
        </div>
      </section>

      <section className="boundary-strip"><div><span className="boundary-strip-icon"><Icon name="shield" size={21} /></span><span><strong>职责分离保持生效</strong><small>Scheduler ≠ Runner · Producer ≠ Verifier · PDP ≠ PEP · 控制台 ≠ 认证机构</small></span></div><a href="/api/capabilities/product" target="_blank" rel="noreferrer" className="text-link">查看能力响应 <Icon name="external" size={14} /></a></section>
    </div>
  );
}
