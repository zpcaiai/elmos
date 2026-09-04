import Link from "next/link";
import { Icon } from "./components/Icon";
import { StatusChip } from "./components/StatusChip";

const workspaces = [
  {
    eyebrow: "BATCH 30 · SPRING",
    title: "Spring 老项目翻新",
    description: "识别经典 Spring、XML 与旧 Boot，显式处理 Java、Jakarta、Security、JPA、配置和真实启动证据。",
    href: "/spring",
    icon: "workflow" as const,
    accent: "blue",
    meta: "3 种源形态 · 1 个精确实验 Pack",
  },
  {
    eyebrow: "BATCH 29 · DIRECTED ROUTES",
    title: "全库跨语言转换",
    description: "在 Java、C#、Python、TypeScript 的 12 条方向路线中选择精确路径，查看语义风险、阻断项和交接命令。",
    href: "/translation",
    icon: "code" as const,
    accent: "cyan",
    meta: "4 种语言 · 12 个本地实验 Profile",
  },
  {
    eyebrow: "PROJECT SYNTHESIS · B46–B80",
    title: "多语言项目生成",
    description: "用同一份受审项目意图规划多目标工程、资产图和构建图，区分内置生成器与专用 Runtime Skill 路由。",
    href: "/generation",
    icon: "spark" as const,
    accent: "violet",
    meta: "草稿 → 批准 → 生成 → 验证",
  },
  {
    eyebrow: "BATCH 31 · CHINADB SQL",
    title: "国产数据库 SQL 转换",
    description: "在 13 个国产数据库目标和 78 条规划路线中做 typed SQL 预评估；缺少精确版本、能力快照或目标适配器时明确阻断。",
    href: "/migration",
    icon: "database" as const,
    accent: "amber",
    meta: "47 Skills · SPEC_ONLY · 外部证据 NOT_RUN",
  },
  {
    eyebrow: "GOVERNANCE · M29–M37",
    title: "迁移能力与验证",
    description: "检查迁移能力包、开发者工作流、外部控制面和严格门禁；结构就绪不自动升级为运行或认证结论。",
    href: "/migration",
    icon: "shield" as const,
    accent: "green",
    meta: "Fail closed · External evidence NOT_RUN",
  },
];

const attention = [
  ["12 条路线独立验证", "本地三类语料已通过，客户仓库与独立验证仍未运行", "NOT_RUN"],
  ["Spring 外部 Runner 证据", "实验 Pack 已闭环，真实客户仓库、holdout 与独立执行未运行", "NOT_RUN"],
  ["多语言生成外部工具链", "浏览器只准备受控交接，不执行生成", "NOT_RUN"],
];

export default function Home() {
  return (
    <div className="page-stack">
      <section className="welcome-card">
        <div className="welcome-copy">
          <span className="overline">ELMOS CONTROL CENTER</span>
          <h1>四类核心工作空间，一套可验证的交付闭环。</h1>
          <p>
            Spring 老项目翻新、全库跨语言转换、多语言项目生成与国产数据库 SQL 转换分别拥有清晰入口、精确状态、阻断原因和恢复动作。任何执行、认证、合并或发布仍由对应门禁和人工权限决定。
          </p>
          <div className="welcome-actions">
            <Link className="button button-primary" href="/spring">
              评估 Spring 老项目 <Icon name="arrow" size={16} />
            </Link>
            <Link className="button button-secondary" href="/translation">
              选择跨语言路线
            </Link>
          </div>
        </div>
        <div className="trust-visual" aria-label="证据链状态：控制面就绪，外部执行未运行">
          <div className="trust-orbit trust-orbit-one" />
          <div className="trust-orbit trust-orbit-two" />
          <div className="trust-core"><Icon name="check" size={24} /></div>
          <span className="trust-node node-a">IR</span>
          <span className="trust-node node-b">Gate</span>
          <span className="trust-node node-c">Evidence</span>
        </div>
      </section>

      <section className="overview-metrics" aria-label="平台结构摘要">
        <article><span className="metric-icon tone-cyan"><Icon name="workflow" size={18} /></span><div><small>Spring 实验 Pack</small><strong>1</strong><em>外部证据 NOT_RUN</em></div></article>
        <article><span className="metric-icon tone-violet"><Icon name="route" size={18} /></span><div><small>跨语言方向</small><strong>12</strong><em>本地 Profile 已通过</em></div></article>
        <article><span className="metric-icon tone-amber"><Icon name="spark" size={18} /></span><div><small>项目生成目标</small><strong>8</strong><em>逐目标验证</em></div></article>
        <article><span className="metric-icon tone-violet"><Icon name="database" size={18} /></span><div><small>国产数据库目标</small><strong>13</strong><em>78 条路线 SPEC_ONLY</em></div></article>
        <article><span className="metric-icon tone-green"><Icon name="shield" size={18} /></span><div><small>外部认证</small><strong>0</strong><em>Fail closed</em></div></article>
      </section>

      <section aria-labelledby="workspace-title">
        <div className="section-heading">
          <div>
            <span className="overline">WORKSPACES</span>
            <h2 id="workspace-title">选择工作空间</h2>
          </div>
          <span className="quiet-label">能力状态来自仓库契约</span>
        </div>
        <div className="workspace-grid">
          {workspaces.map((workspace) => (
            <Link className={`workspace-card accent-${workspace.accent}`} href={workspace.href} key={workspace.title}>
              <div className="workspace-icon"><Icon name={workspace.icon} size={22} /></div>
              <div className="workspace-card-copy">
                <span className="overline">{workspace.eyebrow}</span>
                <h3>{workspace.title}</h3>
                <p>{workspace.description}</p>
                <span className="workspace-meta">{workspace.meta}</span>
              </div>
              <span className="round-arrow"><Icon name="arrow" size={16} /></span>
            </Link>
          ))}
        </div>
      </section>

      <section className="overview-grid">
        <article className="surface-card attention-card">
          <div className="card-heading">
            <div><span className="overline">ATTENTION</span><h2>需要补齐的外部证据</h2></div>
            <span className="count-badge">3</span>
          </div>
          <div className="attention-list">
            {attention.map(([title, description, status]) => (
              <div className="attention-row" key={title}>
                <span className="attention-icon"><Icon name="clock" size={16} /></span>
                <div><strong>{title}</strong><small>{description}</small></div>
                <StatusChip status={status} compact />
              </div>
            ))}
          </div>
        </article>

        <article className="surface-card boundary-card">
          <span className="overline">AUTHORITY BOUNDARY</span>
          <h2>控制面只准备决策</h2>
          <p>当前页面不会执行客户代码、写入生产系统、签发认证或代替人工批准。</p>
          <div className="boundary-rule"><Icon name="lock" size={17} /><span>未知、过期、冲突与未运行状态一律不通过</span></div>
          <Link className="text-link" href="/commercialization">查看职责分离 <Icon name="arrow" size={14} /></Link>
        </article>
      </section>

      <section className="overview-grid qualification-overview">
        <article className="surface-card namespace-card">
          <div className="card-heading"><div><span className="overline">NAMESPACE COVERAGE</span><h2>双命名空间，边界不混用</h2></div><Link className="text-link" href="/skills">查看全部 <Icon name="arrow" size={14} /></Link></div>
          <div className="namespace-summary">
            <div className="namespace-item"><div><span className="namespace-dot migration-dot" /><strong>Migration Packs</strong><small>M1–M45 · 820 Skills</small></div><b>45%</b></div>
            <div className="namespace-track"><span className="namespace-fill migration-fill" style={{width:"45%"}} /></div>
            <div className="namespace-item"><div><span className="namespace-dot product-dot" /><strong>Product commercialization</strong><small>B34–B55 · 1,004 Skills</small></div><b>55%</b></div>
            <div className="namespace-track"><span className="namespace-fill product-fill" style={{width:"55%"}} /></div>
          </div>
        </article>
        <article className="surface-card qualification-card">
          <span className="overline">QUALIFICATION LADDER</span><h2>工程通过，不等于外部认证</h2>
          <div className="qualification-steps"><div className="complete"><i><Icon name="check" size={13} /></i><span><strong>Skill 结构</strong><small>1,824 / 1,824</small></span></div><div className="complete"><i><Icon name="check" size={13} /></i><span><strong>用例目录</strong><small>408 / 408</small></span></div><div><i>3</i><span><strong>独立执行</strong><small>0 / 408 · NOT_RUN</small></span></div><div><i><Icon name="lock" size={12} /></i><span><strong>严格认证</strong><small>BLOCKED</small></span></div></div>
        </article>
      </section>
    </div>
  );
}
