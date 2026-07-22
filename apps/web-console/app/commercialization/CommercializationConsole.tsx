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
          <span className="overline">PRODUCT CONTROL PLANE · B34–B38</span>
          <h1>商业化控制面</h1>
          <p>在执行前回答五个问题：谁、哪份源码、在哪里运行、证据是否可信、现在是否仍被授权。</p>
        </div>
        <div className="header-actions"><span className="environment-selector"><i />环境：本地契约</span><button className="button button-secondary" onClick={refresh} disabled={refreshing}><Icon name="refresh" size={16} className={refreshing ? "spinning" : undefined} />刷新能力</button></div>
      </section>

      <section className="metric-grid metric-grid-four" aria-label="控制面摘要">
        <article className="metric-card"><span>控制域</span><strong>5</strong><small>B34–B38 可信链</small></article>
        <article className="metric-card"><span>本地契约检查</span><strong>{enforcedCount}</strong><small>已定义或强制</small></article>
        <article className="metric-card"><span>待补外部项</span><strong className="warning-text">{unresolvedCount}</strong><small>不隐藏阻断状态</small></article>
        <article className="metric-card"><span>决策上限</span><strong className="metric-word">Gate / Human</strong><small>不批准、不执行</small></article>
      </section>

      <section className="source-notice" role="status"><Icon name={payload.source === "LIVE_API" ? "check" : "clock"} size={16} /><span>{payload.note}</span><small className="source-freshness">最近刷新 {fetchedAt}</small><StatusChip status={payload.source} compact /></section>

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
        <article className="surface-card stage-detail" id="trust-stage-panel" role="tabpanel" aria-labelledby={`trust-tab-${selectedStage.batch}`} tabIndex={0}>
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
        </article>

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
