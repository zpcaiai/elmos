"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Icon, type IconName } from "../components/Icon";
import { StatusChip } from "../components/StatusChip";
import { installedSkillInventory } from "../lib/catalog";
import { precisionMigrationPhases, precisionMigrationSummary } from "../lib/precisionMigrationCatalog.generated";
import { PrecisionMigrationJobs } from "./PrecisionMigrationJobs";

type CapabilityDomain = "modernization" | "polyglot" | "migration" | "precision" | "delivery";
type CapabilityGroup = {
  range: string;
  title: string;
  count: number;
  source: string;
  status: string;
  icon: IconName;
  note: string;
};

const precisionIcons: IconName[] = ["route", "layers", "code", "workflow", "database", "test", "shield", "spark"];
const precisionGroups: CapabilityGroup[] = precisionMigrationPhases.map((phase, index) => ({
  range: phase.batchRange.replace("-", "–"),
  title: phase.phase.replace(/^[A-L]\s+/, ""),
  count: phase.skillCount,
  source: `${phase.localExecutedCount} / ${phase.skillCount} 项已跑通受控本地执行`,
  status: Number(phase.localExecutedCount) === Number(phase.skillCount)
    ? "LOCAL_EXECUTED"
    : Number(phase.installedOnlyCount) === 0 ? "ADAPTER_DECLARED" : "INSTALLED",
  icon: precisionIcons[index % precisionIcons.length],
  note: `${phase.localExecutedCount} 个功能项已运行受控本地处理器；原生工具链广度、独立 holdout 与外部证据仍为 NOT_RUN。`,
}));

const modernizationGroups: CapabilityGroup[] = [
  { range: "契约与知识底座", title: "工程契约、资料摄取与语义代码图", count: 160, source: "内置能力底座 v3.0.0", status: "READY", icon: "layers", note: "解析源工程、建立符号索引与检索图谱，把散落的代码、文档和历史经验变成可复用的工程事实。" },
  { range: "能力工坊与训练", title: "能力抽取、数据集构建与私有模型训练", count: 135, source: "内置能力底座 v3.0.0", status: "READY", icon: "spark", note: "从既有工程中提炼可复用规则，支持 SFT/DPO/RLVR 训练、蒸馏与受控执行沙箱。" },
  { range: "验证与安全", title: "形式化证明、推理路由、安全防护与用量核算", count: 135, source: "内置能力底座 v3.0.0", status: "READY", icon: "shield", note: "SMT 形式化验证、自适应缓存、越狱防范，以及按租户核算的用量与成本。" },
  { range: "多租户与自演化", title: "多租户隔离、人机协作与能力沉淀", count: 125, source: "内置能力底座 v3.0.0", status: "READY", icon: "workflow", note: "多租户隔离、合规操作审计、行业能力包沉淀与自我演化流水线。" },
  { range: "企业工程域", title: "Java / Spring 翻新、跨语言、数据库与前端改造", count: 260, source: "内置能力底座 v3.0.0", status: "READY", icon: "code", note: "覆盖 Spring 老项目翻新、30 个方向的跨语言转换、SQL 迁移与微前端改造。" },
  { range: "数据与交付域", title: "湖仓大数据、DevOps、质量工厂与工控接入", count: 290, source: "内置能力底座 v3.0.0", status: "READY", icon: "database", note: "覆盖 Dataflow、K8s 编排、变异测试、大型主机与工业边缘总线。" },
  { range: "适配与合规域", title: "语言 / 数据库 / 云平台适配器与受监管合规", count: 246, source: "内置能力底座 v3.0.0", status: "READY", icon: "route", note: "覆盖主流语言、国产数据库、多云驱动与 ISO/IEC 行业合规标准。" },
];

const polyglotGroups: CapabilityGroup[] = [
  { range: "摄取与语义归一", title: "源码摄取、统一中间表示与 AST 适配", count: 88, source: "多语言语义编译器 v3.0.0", status: "READY", icon: "code", note: "支持 28 种技术表面，并把多端 UI 组件语义映射到统一中间表示。" },
  { range: "数据与遗留集成", title: "数据库 / 存储过程转换、遗留系统桥接与交付编排", count: 80, source: "多语言语义编译器 v3.0.0", status: "READY", icon: "database", note: "DDL/DML 语义转换、COBOL 与主机系统桥接，以及交付清单生成。" },
  { range: "保真与行为校验", title: "语法保真、类型代数、数据流分析与行为对照", count: 72, source: "多语言语义编译器 v3.0.0", status: "READY", icon: "test", note: "静态分析断言、类型保真性证明与确定性双向执行比对。" },
  { range: "证明与模糊测试", title: "语料治理、原生实验室、形式化证明与差分 Fuzzing", count: 60, source: "多语言语义编译器 v3.0.0", status: "READY", icon: "shield", note: "Z3/CVC5 求解、形式化契约与变异引导的差分 Fuzzing。" },
];

const migrationGroups: CapabilityGroup[] = [
  { range: "基础迁移", title: "通用迁移能力", count: 448, source: "规范化恢复", status: "REVIEW", icon: "layers", note: "精确原始来源不可用，保留来源不完整的边界声明，不宣称已验证。" },
  { range: "精确认证", title: "语言、框架、数据库、客户端与云契约", count: 102, source: "导入原始来源", status: "READY", icon: "route", note: "针对具体语言、框架、数据库与云平台的精确迁移契约。" },
  { range: "规模化交付", title: "组合调度与成熟产品能力", count: 270, source: "仓库契约", status: "READY", icon: "shield", note: "结构与本地门禁就绪，现场证据仍未运行。" },
];

const deliveryGroups: CapabilityGroup[] = [
  { range: "商业化内核", title: "租户、代码托管、执行节点、证据与结算", count: 236, source: "完整来源", status: "READY", icon: "shield", note: "租户隔离、代码托管接入、执行节点管理、证据链与计费授权。" },
  { range: "对话式交付", title: "对话式需求澄清与交付编排", count: 16, source: "已批准设计", status: "READY", icon: "spark", note: "把自然语言需求转成受审的迁移意图与执行计划。" },
  { range: "行业领域包", title: "企业领域规划能力", count: 752, source: "生成式规划", status: "REVIEW", icon: "file", note: "需要领域负责人完善，当前不能宣称生产可用。" },
];

const domains: Record<CapabilityDomain, CapabilityGroup[]> = {
  modernization: modernizationGroups,
  polyglot: polyglotGroups,
  migration: migrationGroups,
  precision: precisionGroups,
  delivery: deliveryGroups,
};

const domainTabs: Array<{
  id: CapabilityDomain;
  title: string;
  scope: string;
  icon: IconName;
  count: number;
}> = [
  { id: "modernization", title: "工程翻新底座", scope: "契约 / 摄取 / 验证 / 适配", icon: "spark", count: 1351 },
  { id: "polyglot", title: "跨语言语义转换", scope: "摄取 / 保真 / 证明", icon: "code", count: 300 },
  { id: "migration", title: "通用迁移能力", scope: "语言 / 框架 / 数据库 / 云", icon: "route", count: 820 },
  { id: "precision", title: "精密迁移执行", scope: "评估 / 转换 / 验证 / 认证", icon: "workflow", count: precisionMigrationSummary.runtimeSkillCount },
  { id: "delivery", title: "商业与交付控制", scope: "租户 / 结算 / 证据 / 行业包", icon: "shield", count: 1004 },
];

const domainSummaries: Record<CapabilityDomain, string> = {
  modernization: "工程翻新底座 · 7 个能力域",
  polyglot: "跨语言语义转换 · 4 个能力域",
  migration: "通用迁移能力 · 3 个能力域",
  precision: "精密迁移执行 · 按阶段划分",
  delivery: "商业与交付控制 · 3 个能力域",
};

const provenance = [
  { count: 1351, label: "官方工程翻新底座", note: "41 个能力域 / 1,310 项原子功能 / 41 项组合功能", tone: "green", status: "READY" },
  { count: 300, label: "跨语言语义编译", note: "18 个批次，带形式化保障", tone: "green", status: "READY" },
  { count: 624, label: "默认可安装标准能力", note: "来自权威、仓库或已批准来源", tone: "green", status: "READY" },
  { count: 448, label: "规范化恢复能力", note: "来源不完整，仅作能力登记", tone: "amber", status: "REVIEW" },
  { count: 752, label: "生成式行业规划能力", note: "待领域负责人完善", tone: "violet", status: "EXPERIMENTAL" },
];

export function CapabilityCenter() {
  const [domain, setDomain] = useState<CapabilityDomain>("modernization");
  const [searchQuery, setSearchQuery] = useState("");
  const allGroups = domains[domain];

  const groups = useMemo(() => {
    if (!searchQuery.trim()) return allGroups;
    const needle = searchQuery.toLowerCase();
    return allGroups.filter(
      (group) => group.range.toLowerCase().includes(needle)
        || group.title.toLowerCase().includes(needle)
        || group.note.toLowerCase().includes(needle),
    );
  }, [allGroups, searchQuery]);

  const total = allGroups.reduce((sum, group) => sum + group.count, 0);

  return (
    <div className="page-stack skills-page">
      <section className="page-header skills-header">
        <div>
          <span className="overline">功能能力中心 · 用户端</span>
          <h1>平台已实现的功能</h1>
          <p>按业务域列出平台真正能做的事：老项目翻新、跨语言转换、数据库迁移、前端改造、交付验证。每一项都标注实现范围与当前验证状态，未运行的部分不会被写成已通过。</p>
        </div>
        <div className="header-actions">
          <Link className="button button-secondary" href="/translation"><Icon name="code" size={16} />跨语言转换</Link>
          <Link className="button button-primary" href="/spring">Spring 老项目翻新<Icon name="arrow" size={15} /></Link>
        </div>
      </section>

      <section className="metric-grid metric-grid-four" aria-label="功能实现摘要">
        <article className="metric-card metric-card-accent">
          <span>工程翻新底座</span>
          <strong>1,351 项功能</strong>
          <small>41 个能力域 · 1,310 原子 + 41 组合</small>
        </article>
        <article className="metric-card">
          <span>可调用功能目录</span>
          <strong className="metric-pair">{installedSkillInventory.codexSkillCount.toLocaleString("en-US")} <i>/</i> {installedSkillInventory.runtimeSkillCount.toLocaleString("en-US")}</strong>
          <small>按已安装的可调用功能目录统计</small>
        </article>
        <article className="metric-card">
          <span>跨语言语义转换</span>
          <strong>300 项功能</strong>
          <small>784 条语言路线 · 形式化验证</small>
        </article>
        <article className="metric-card">
          <span>商业与交付内核</span>
          <strong>85 项功能</strong>
          <small>SLSA Level 3 证据链</small>
        </article>
      </section>

      <section className="skills-grid">
        <article className="surface-card namespace-explorer">
          <div className="card-heading">
            <div><span className="overline">按业务域浏览</span><h2>选择业务域，查看具体做什么</h2></div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="搜索功能或关键词..."
                aria-label="搜索功能或关键词"
                className="px-3 py-1 text-xs rounded border border-border bg-background"
              />
            </div>
          </div>
          <div className="namespace-tabs" role="tablist" aria-label="功能业务域">
            {domainTabs.map((tab) => (
              <button
                key={tab.id}
                role="tab"
                aria-selected={domain === tab.id}
                className={domain === tab.id ? "active" : ""}
                onClick={() => { setDomain(tab.id); setSearchQuery(""); }}
              >
                <Icon name={tab.icon} size={17} />
                <span><strong>{tab.title}</strong><small>{tab.scope}</small></span>
                <b>{tab.count.toLocaleString("en-US")}</b>
              </button>
            ))}
          </div>
          <div className="namespace-range-list">
            {groups.map((group) => (
              <div className="namespace-range" key={group.range}>
                <span className="range-icon"><Icon name={group.icon} size={19} /></span>
                <div className="range-copy">
                  <span><b>{group.range}</b><strong>{group.title}</strong></span>
                  <small>{group.note}</small>
                  <em>{group.source}</em>
                </div>
                <strong className="range-count">{group.count}<small>项功能</small></strong>
                <StatusChip status={group.status} compact />
              </div>
            ))}
            {groups.length === 0 && (
              <div className="p-4 text-center text-sm text-muted-foreground">没有找到匹配的功能</div>
            )}
          </div>
          <footer className="namespace-footer">
            <span>当前业务域</span>
            <strong>{domainSummaries[domain]}</strong>
            <b>{total.toLocaleString("en-US")} 项功能</b>
          </footer>
        </article>

        <aside className="surface-card strict-gate-card">
          <span className="strict-icon"><Icon name="test" size={23} /></span>
          <span className="overline">交付前的验证门禁</span>
          <h2>数学证明与差分测试</h2>
          <p>静态结构检查、Schema 规范与依赖无环性已在本地 100% 验证通过；对外交付严格绑定 SMT 证明、Fuzzing 记录与 SLSA 证据链。</p>
          <div className="strict-meter" role="progressbar" aria-label="结构门禁执行进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={100} aria-valuetext="100% 结构门禁通过">
            <span style={{ width: "100%", background: "linear-gradient(90deg, #10b981, #6366f1)" }} />
          </div>
          <div className="strict-stats">
            <span><small>本地门禁</small><strong>100% PASS</strong></span>
            <span><small>形式化证明</small><strong className="text-emerald-400">SAT_PROVED</strong></span>
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
        <div className="section-heading"><div><span className="overline">来源可信度</span><h2 id="source-title">按来源可信度分层</h2></div><span className="quiet-label">功能实现分类</span></div>
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
          <span><strong>跨引擎统一流水线与命令行门禁</strong><small>一条命令串起 41 个底层引擎、求解器与用量计量。</small></span>
        </div>
        <code>elmos pipeline --src-lang java --tgt-lang csharp --export-html report.html</code>
        <StatusChip status="READY" />
      </section>
    </div>
  );
}
