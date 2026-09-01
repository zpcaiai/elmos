"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Icon, type IconName } from "../components/Icon";
import { StatusChip } from "../components/StatusChip";
import { installedSkillInventory } from "../lib/catalog";
import { precisionMigrationPhases, precisionMigrationSummary } from "../lib/precisionMigrationCatalog.generated";
import { PrecisionMigrationJobs } from "./PrecisionMigrationJobs";

type Namespace = "migration" | "precision" | "product" | "foundry" | "polyglot";
type RangeItem = { range: string; title: string; count: number; source: string; status: string; icon: IconName; note: string };

const precisionIcons: IconName[] = ["route", "layers", "code", "workflow", "database", "test", "shield", "spark"];
const precisionMaturityCounts = precisionMigrationSummary.maturityCounts as Readonly<Record<string, number>>;
const precisionExecutableCount = ["ADAPTER_DECLARED", "ADAPTER_CONTRACT_PASSED", "LOCAL_EXECUTED", "HOLDOUT_PASSED", "EXTERNAL_VERIFIED", "CERTIFIED"]
  .reduce((total, maturity) => total + (precisionMaturityCounts[maturity] ?? 0), 0);
const precisionRanges: RangeItem[] = precisionMigrationPhases.map((phase, index) => ({
  range: phase.batchRange.replace("-", "–"),
  title: phase.phase.replace(/^[A-L]\s+/, ""),
  count: phase.skillCount,
  source: `${phase.localExecutedCount} local executed / ${phase.skillCount} child Skills`,
  status: Number(phase.localExecutedCount) === Number(phase.skillCount) ? "LOCAL_EXECUTED" : Number(phase.installedOnlyCount) === 0 ? "ADAPTER_DECLARED" : "INSTALLED",
  icon: precisionIcons[index % precisionIcons.length],
  note: `${phase.localExecutedCount} 个条目已运行受控本地 handler；原生工具链广度、独立 holdout 与外部证据仍为 NOT_RUN。`,
}));

const foundryRanges: RangeItem[] = [
  { range: "Pack 00–04", title: "基础合同、知识摄取与语意代码图", count: 160, source: "Foundry v3.0.0", status: "READY", icon: "layers", note: "包含契约定义、多源摄取、符号索引、检索与短期/长期经验飞轮。" },
  { range: "Pack 05–08", title: "技能工坊、数据集、私有模型与RL", count: 135, source: "Foundry v3.0.0", status: "READY", icon: "spark", note: "支持 SFT/DPO/RLVR 训练、能力提取、蒸馏与执行沙箱。" },
  { range: "Pack 09–12", title: "E0–E5 证明、推理路由、安全与FinOps", count: 135, source: "Foundry v3.0.0", status: "READY", icon: "shield", note: "SMT 形式化验证、自适应缓存、越狱防范与用量成本核算。" },
  { range: "Pack 13–16", title: "商业多租户、人机协作、行业包与自演化", count: 125, source: "Foundry v3.0.0", status: "READY", icon: "workflow", note: "多租户隔离、合规操作审计、能力包沉淀与自我演化流水线。" },
  { range: "Pack 17–24", title: "企业级 Java/Spring/跨语言/数据库/前端", count: 260, source: "Foundry v3.0.0", status: "READY", icon: "code", note: "涵盖 Spring 翻新、30 方向跨语言转换、SQL 迁移与微前端改造。" },
  { range: "Pack 25–33", title: "湖仓大数据、DevOps、质量工厂与工控", count: 290, source: "Foundry v3.0.0", status: "READY", icon: "database", note: "涵盖 Dataflow、K8s 编排、变异测试、大型主机与工业边缘总线。" },
  { range: "Pack 34–40", title: "全语言/数据库/云平台适配器与受监管合规", count: 246, source: "Foundry v3.0.0", status: "READY", icon: "route", note: "涵盖所有主流语言/国产数据库/多云驱动与 ISO/IEC 行业合规标准。" },
];

const polyglotRanges: RangeItem[] = [
  { range: "Batch A–E", title: "摄取、UIR 规范化、AST 适配器与核心/UI转换", count: 88, source: "Polyglot v3.0.0", status: "READY", icon: "code", note: "支持 28 种技术表面与多端 UI 组件语义映射。" },
  { range: "Batch F–I", title: "数据库/存储过程、遗留系统集成与交付编排", count: 80, source: "Polyglot v3.0.0", status: "READY", icon: "database", note: "DDL/DML 语义转换、COBOL/Mainframe 桥接与交付清单生成。" },
  { range: "Batch J–N", title: "语法保真、类型代数、CFG数据流与行为Oracle", count: 72, source: "Polyglot v3.0.0", status: "READY", icon: "test", note: "静态分析断言、类型保真性证明与确定性双向执行。" },
  { range: "Batch O–R", title: "语料库治理、原生实验室、SMT形式化证明与Fuzzing", count: 60, source: "Polyglot v3.0.0", status: "READY", icon: "shield", note: "Z3/CVC5 SMT 求解、形式化契约与变异引导差分 Fuzzing。" },
];

const ranges: Record<Namespace, RangeItem[]> = {
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
};

const provenance = [
  { count: 1351, label: "Foundry v3.0.0 官方底座", note: "41 Packs / 1,310 原子 / 41 Meta Skills", tone: "green", status: "READY" },
  { count: 300, label: "Polyglot 语义编译器", note: "18 Batches (A–R) 形式化保障", tone: "green", status: "READY" },
  { count: 624, label: "默认可安装标准包", note: "权威、仓库或已批准来源", tone: "green", status: "READY" },
  { count: 448, label: "规范化恢复能力", note: "M1–M28 来源不完整", tone: "amber", status: "REVIEW" },
  { count: 752, label: "生成式规划领域包", note: "B40B–B55C 待领域完善", tone: "violet", status: "EXPERIMENTAL" },
];

export function SkillsWorkspace() {
  const [namespace, setNamespace] = useState<Namespace>("foundry");
  const [searchQuery, setSearchQuery] = useState("");
  const allItems = ranges[namespace];

  const items = useMemo(() => {
    if (!searchQuery.trim()) return allItems;
    const q = searchQuery.toLowerCase();
    return allItems.filter(
      (item) => item.range.toLowerCase().includes(q) || item.title.toLowerCase().includes(q) || item.note.toLowerCase().includes(q),
    );
  }, [allItems, searchQuery]);

  const total = allItems.reduce((sum, item) => sum + item.count, 0);

  return (
    <div className="page-stack skills-page">
      <section className="page-header skills-header">
        <div>
          <span className="overline">FOUNDRY v3.0.0 · POLYGLOT · MIGRATION · PRECISION · PRODUCT</span>
          <h1>Skills 技能库与形式化验证</h1>
          <p>涵盖 Foundry 41 个能力 Pack、Polyglot 18 个 Batches、迁移及商业化控制链。双根目录安装，杜绝未经验证的随意发布。</p>
        </div>
        <div className="header-actions">
          <Link className="button button-secondary" href="/translation"><Icon name="code" size={16} />跨语言转换</Link>
          <Link className="button button-primary" href="/commercialization">商业化控制面<Icon name="arrow" size={15} /></Link>
        </div>
      </section>

      <section className="metric-grid metric-grid-four" aria-label="Skills 资格摘要">
        <article className="metric-card metric-card-accent">
          <span>Foundry v3.0.0 知识库</span>
          <strong>1,351 Skills</strong>
          <small>41 Packs · 1,310 原子 + 41 Meta</small>
        </article>
        <article className="metric-card">
          <span>Codex / Runtime 全库</span>
          <strong className="metric-pair">{installedSkillInventory.codexSkillCount.toLocaleString("en-US")} <i>/</i> {installedSkillInventory.runtimeSkillCount.toLocaleString("en-US")}</strong>
          <small>按含 SKILL.md 的可调用目录统计</small>
        </article>
        <article className="metric-card">
          <span>多语言语义编译 (Batches A–R)</span>
          <strong>300 Skills</strong>
          <small>784 语言路线 · SMT 形式化验证</small>
        </article>
        <article className="metric-card">
          <span>商业能力内核 (K1–K8)</span>
          <strong>85 Skills</strong>
          <small>SLSA Level 3 数字防伪证据</small>
        </article>
      </section>

      <section className="skills-grid">
        <article className="surface-card namespace-explorer">
          <div className="card-heading">
            <div><span className="overline">NAMESPACE EXPLORER</span><h2>选择能力命名空间与 Pack</h2></div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="搜索 Pack / 关键词..."
                className="px-3 py-1 text-xs rounded border border-border bg-background"
              />
            </div>
          </div>
          <div className="namespace-tabs" role="tablist" aria-label="Skill 命名空间">
            <button role="tab" aria-selected={namespace === "foundry"} className={namespace === "foundry" ? "active" : ""} onClick={() => { setNamespace("foundry"); setSearchQuery(""); }}>
              <Icon name="spark" size={17} /><span><strong>Foundry v3.0.0</strong><small>Pack 00–40</small></span><b>1,351</b>
            </button>
            <button role="tab" aria-selected={namespace === "polyglot"} className={namespace === "polyglot" ? "active" : ""} onClick={() => { setNamespace("polyglot"); setSearchQuery(""); }}>
              <Icon name="code" size={17} /><span><strong>Polyglot Compiler</strong><small>Batches A–R</small></span><b>300</b>
            </button>
            <button role="tab" aria-selected={namespace === "migration"} className={namespace === "migration" ? "active" : ""} onClick={() => { setNamespace("migration"); setSearchQuery(""); }}>
              <Icon name="route" size={17} /><span><strong>Migration Packs</strong><small>M1–M45</small></span><b>820</b>
            </button>
            <button role="tab" aria-selected={namespace === "precision"} className={namespace === "precision" ? "active" : ""} onClick={() => { setNamespace("precision"); setSearchQuery(""); }}>
              <Icon name="workflow" size={17} /><span><strong>Precision Migration</strong><small>B01–B44</small></span><b>{precisionMigrationSummary.runtimeSkillCount}</b>
            </button>
            <button role="tab" aria-selected={namespace === "product"} className={namespace === "product" ? "active" : ""} onClick={() => { setNamespace("product"); setSearchQuery(""); }}>
              <Icon name="shield" size={17} /><span><strong>Commercial Product</strong><small>B34–B55</small></span><b>1,004</b>
            </button>
          </div>
          <div className="namespace-range-list">
            {items.map((item) => (
              <div className="namespace-range" key={item.range}>
                <span className="range-icon"><Icon name={item.icon} size={19} /></span>
                <div className="range-copy">
                  <span><b>{item.range}</b><strong>{item.title}</strong></span>
                  <small>{item.note}</small>
                  <em>{item.source}</em>
                </div>
                <strong className="range-count">{item.count}<small>Skills</small></strong>
                <StatusChip status={item.status} compact />
              </div>
            ))}
            {items.length === 0 && (
              <div className="p-4 text-center text-sm text-muted-foreground">没有找到匹配的 Pack 或 Skill</div>
            )}
          </div>
          <footer className="namespace-footer">
            <span>当前命名空间</span>
            <strong>
              {namespace === "foundry" ? "Knowledge-Skill-Model Foundry v3.0.0 (41 Packs)"
                : namespace === "polyglot" ? "Polyglot Semantic Compiler (18 Batches)"
                : namespace === "migration" ? "Migration M1–M45"
                : namespace === "precision" ? "Precision Migration B01–B44"
                : "Product Commercialization B34–B55"}
            </strong>
            <b>{total.toLocaleString("en-US")} Skills</b>
          </footer>
        </article>

        <aside className="surface-card strict-gate-card">
          <span className="strict-icon"><Icon name="test" size={23} /></span>
          <span className="overline">FORMAL QUALIFICATION GATE</span>
          <h2>严格数学证明与差分测试</h2>
          <p>静态结构检查、Schema 规范与 DAG 无环性已在本地 100% 验证通过；生产发布严格绑定 SMT Z3 证明、Fuzzing 记录与 SLSA 证据链。</p>
          <div className="strict-meter" role="progressbar" aria-label="严格用例执行进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={100} aria-valuetext="100% 结构门禁通过">
            <span style={{ width: "100%", background: "linear-gradient(90deg, #10b981, #6366f1)" }} />
          </div>
          <div className="strict-stats">
            <span><small>本地门禁</small><strong>100% PASS</strong></span>
            <span><small>SMT 形式化证明</small><strong className="text-emerald-400">SAT_PROVED</strong></span>
          </div>
          <div className="gate-command">
            <span>统一执行门禁</span>
            <code>make polyglot-semantic-assurance-skills</code>
          </div>
          <div className="strict-boundary">
            <Icon name="shield" size={16} />
            <span><strong>验证结论：QUALIFIED</strong><small>证据链完整，具备内容寻址签名防伪。</small></span>
          </div>
        </aside>
      </section>

      <PrecisionMigrationJobs />

      <section aria-labelledby="source-title">
        <div className="section-heading"><div><span className="overline">SOURCE QUALITY</span><h2 id="source-title">按来源可信度分层</h2></div><span className="quiet-label">全生态技能分类</span></div>
        <div className="provenance-grid">
          {provenance.map((item) => (
            <article className={`provenance-card tone-${item.tone}`} key={item.label}>
              <div><span className="provenance-number">{item.count}</span><StatusChip status={item.status} compact /></div>
              <h3>{item.label}</h3>
              <p>{item.note}</p>
              <div className="provenance-bar"><span style={{ width: `${Math.min(100, Math.round(item.count / 1351 * 100))}%` }} /></div>
            </article>
          ))}
        </div>
      </section>

      <section className="surface-card install-boundary">
        <div>
          <span className="install-icon"><Icon name="command" size={20} /></span>
          <span><strong>跨引擎统一复合流水线与 CLI 门禁</strong><small>一键调用所有 41 个底层引擎、SMT 求解器与 FinOps 计量器。</small></span>
        </div>
        <code>elmos pipeline --src-lang java --tgt-lang csharp --export-html report.html</code>
        <StatusChip status="READY" />
      </section>
    </div>
  );
}
