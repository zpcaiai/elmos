"use client";

import Link from "next/link";
import { useState } from "react";
import { Icon, type IconName } from "../components/Icon";
import { StatusChip } from "../components/StatusChip";

type Namespace = "migration" | "product";
type RangeItem = { range: string; title: string; count: number; source: string; status: string; icon: IconName; note: string };

const ranges: Record<Namespace, RangeItem[]> = {
  migration: [
    { range: "M1–M28", title: "基础迁移能力", count: 448, source: "Normalized recovery", status: "REVIEW", icon: "layers", note: "精确原始包不可用，保留来源不完整边界。" },
    { range: "M29–M33", title: "精确迁移认证包", count: 102, source: "Imported original", status: "READY", icon: "route", note: "语言、框架、数据库、客户端与 Cloud 契约。" },
    { range: "M34–M45", title: "规模与成熟产品包", count: 270, source: "Repository contracts", status: "READY", icon: "shield", note: "结构和本地门禁就绪，现场证据仍未运行。" },
  ],
  product: [
    { range: "B34–B39", title: "商业化核心控制", count: 236, source: "Complete source", status: "READY", icon: "shield", note: "租户、SCM、Runner、证据、授权与 Finance。" },
    { range: "B40A", title: "对话设计", count: 16, source: "Approved design", status: "READY", icon: "spark", note: "具有已批准的 conversation-design 来源。" },
    { range: "B40B–B55C", title: "企业领域规划版", count: 752, source: "Generated planning", status: "REVIEW", icon: "file", note: "需要领域负责人完善，不能宣称生产完成。" },
  ],
};

const provenance = [
  { count: 624, label: "默认可安装", note: "权威、仓库或已批准来源", tone: "green", status: "READY" },
  { count: 448, label: "规范化恢复", note: "M1–M28 来源不完整", tone: "amber", status: "REVIEW" },
  { count: 752, label: "生成式规划", note: "B40B–B55C 待领域完善", tone: "violet", status: "EXPERIMENTAL" },
];

export function SkillsWorkspace() {
  const [namespace, setNamespace] = useState<Namespace>("migration");
  const items = ranges[namespace];
  const total = items.reduce((sum, item) => sum + item.count, 0);

  return <div className="page-stack skills-page">
    <section className="page-header skills-header">
      <div><span className="overline">BATCH 1–55 · DUAL NAMESPACE</span><h1>Skills 与验证</h1><p>先看来源、版本和门禁，再决定一个 Skill 是否可以进入真实工作流。结构通过不会被包装成业务完成或生产认证。</p></div>
      <div className="header-actions"><Link className="button button-secondary" href="/migration"><Icon name="route" size={16} />迁移工坊</Link><Link className="button button-primary" href="/commercialization">商业化控制面<Icon name="arrow" size={15} /></Link></div>
    </section>

    <section className="metric-grid metric-grid-four" aria-label="Skills 资格摘要">
      <article className="metric-card metric-card-accent"><span>组合包契约</span><strong>1,824</strong><small>官方结构 1,824 / 1,824</small></article>
      <article className="metric-card"><span>Codex / Runtime</span><strong className="metric-pair">530 <i>/</i> 2,097</strong><small>均具有可调用界面</small></article>
      <article className="metric-card"><span>严格用例目录</span><strong>408</strong><small>Batch 1–37 · 八类变体</small></article>
      <article className="metric-card"><span>外部认证用例</span><strong className="warning-text">0 / 408</strong><small>全部保持 NOT_RUN</small></article>
    </section>

    <section className="skills-grid">
      <article className="surface-card namespace-explorer">
        <div className="card-heading"><div><span className="overline">NAMESPACE EXPLORER</span><h2>选择一个明确命名空间</h2></div><span className="quiet-label">数字标签不可互换</span></div>
        <div className="namespace-tabs" role="tablist" aria-label="Skill 命名空间">
          <button role="tab" aria-selected={namespace === "migration"} className={namespace === "migration" ? "active" : ""} onClick={() => setNamespace("migration")}><Icon name="route" size={17} /><span><strong>Migration Packs</strong><small>M1–M45</small></span><b>820</b></button>
          <button role="tab" aria-selected={namespace === "product"} className={namespace === "product" ? "active" : ""} onClick={() => setNamespace("product")}><Icon name="shield" size={17} /><span><strong>Product commercialization</strong><small>B34–B55</small></span><b>1,004</b></button>
        </div>
        <div className="namespace-range-list">
          {items.map((item) => <div className="namespace-range" key={item.range}>
            <span className="range-icon"><Icon name={item.icon} size={19} /></span>
            <div className="range-copy"><span><b>{item.range}</b><strong>{item.title}</strong></span><small>{item.note}</small><em>{item.source}</em></div>
            <strong className="range-count">{item.count}<small>Skills</small></strong>
            <StatusChip status={item.status} compact />
          </div>)}
        </div>
        <footer className="namespace-footer"><span>当前命名空间</span><strong>{namespace === "migration" ? "Migration M1–M45" : "Product B34–B55"}</strong><b>{total.toLocaleString("en-US")} Skills</b></footer>
      </article>

      <aside className="surface-card strict-gate-card">
        <span className="strict-icon"><Icon name="test" size={23} /></span><span className="overline">STRICT QUALIFICATION</span><h2>408 个用例，0 个被伪造通过</h2><p>目录、Schema 和工具链可以本地验证；认证结果必须绑定独立执行者、原始证据、授权和签名请求。</p>
        <div className="strict-meter" aria-label="严格用例执行进度 0 / 408"><span style={{width:"0%"}} /></div>
        <div className="strict-stats"><span><small>目录就绪</small><strong>408 / 408</strong></span><span><small>已执行</small><strong className="warning-text">0 / 408</strong></span></div>
        <div className="gate-command"><span>唯一严格认证门禁</span><code>scripts/test-suite/run_strict_test_gate.py</code></div>
        <div className="strict-boundary"><Icon name="lock" size={16} /><span><strong>当前结论：BLOCKED</strong><small>未运行、合成或未独立签署的证据永不通过。</small></span></div>
      </aside>
    </section>

    <section aria-labelledby="source-title">
      <div className="section-heading"><div><span className="overline">SOURCE QUALITY</span><h2 id="source-title">按来源可信度分层</h2></div><span className="quiet-label">总计 1,824</span></div>
      <div className="provenance-grid">
        {provenance.map((item) => <article className={`provenance-card tone-${item.tone}`} key={item.label}><div><span className="provenance-number">{item.count}</span><StatusChip status={item.status} compact /></div><h3>{item.label}</h3><p>{item.note}</p><div className="provenance-bar"><span style={{width:`${Math.round(item.count / 1824 * 100)}%`}} /></div></article>)}
      </div>
    </section>

    <section className="surface-card install-boundary">
      <div><span className="install-icon"><Icon name="command" size={20} /></span><span><strong>安全默认安装</strong><small>默认仅安装 624 个权威、仓库或已批准来源的 Skills；其余内容必须显式启用。</small></span></div>
      <code>make batch1-55-skills</code>
      <StatusChip status="NOT_RUN" />
    </section>
  </div>;
}
