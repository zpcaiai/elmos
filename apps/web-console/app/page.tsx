import Link from "next/link";
import { Icon } from "./components/Icon";
import { StatusChip } from "./components/StatusChip";

const workspaces = [
  {
    eyebrow: "M29–M37",
    title: "迁移工坊",
    description: "从语言路由、框架和数据库，到开发者工作流与扩展市场，统一查看精确契约和外部门禁。",
    href: "/migration",
    icon: "route" as const,
    accent: "cyan",
    meta: "200 Skills · 9 个能力包",
  },
  {
    eyebrow: "PRODUCT B34–B38",
    title: "商业化控制面",
    description: "在同一条可信链路里审阅租户、SCM、Runner、证据与持续授权，所有缺失信息默认阻断。",
    href: "/commercialization",
    icon: "shield" as const,
    accent: "violet",
    meta: "5 个控制域 · Fail closed",
  },
  {
    eyebrow: "PROJECT SYNTHESIS · B46–B60",
    title: "多语言项目生成",
    description: "用一个清晰的本地草稿规划 Java、Python 与 C# 项目骨架，预览工程资产和验证阶段，不直接执行生成。",
    href: "/generation",
    icon: "spark" as const,
    accent: "blue",
    meta: "170 Skills · 3 个精确目标栈",
  },
  {
    eyebrow: "BATCH 1–55",
    title: "Skills 与验证",
    description: "检查 Migration 与 Product 双命名空间、来源完整性、严格测试和认证阻断状态。",
    href: "/skills",
    icon: "test" as const,
    accent: "green",
    meta: "1,824 contracts · 408 strict cases",
  },
];

const attention = [
  ["外部 Runner 与 Sandbox", "尚未绑定真实执行环境", "NOT_RUN"],
  ["独立 Holdout 证据", "本地构建不能替代独立验证", "NOT_RUN"],
  ["签名与发布授权", "需要外部信任根和人工批准", "BLOCKED"],
];

export default function Home() {
  return (
    <div className="page-stack">
      <section className="welcome-card">
        <div className="welcome-copy">
          <span className="overline">ELMOS CONTROL CENTER</span>
          <h1>把复杂迁移，变成可解释的决策。</h1>
          <p>
            从迁移路线、多语言项目生成、商业化控制到 Skills 资格验证，所有本地能力、未知项和外部门禁都在同一处清晰呈现。任何执行、认证、合并或发布仍由对应门禁和人工权限决定。
          </p>
          <div className="welcome-actions">
            <Link className="button button-primary" href="/migration">
              进入迁移工坊 <Icon name="arrow" size={16} />
            </Link>
            <Link className="button button-secondary" href="/commercialization">
              查看控制面
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
        <article><span className="metric-icon tone-cyan"><Icon name="spark" size={18} /></span><div><small>组合 Skill 契约</small><strong>1,824</strong><em>结构就绪</em></div></article>
        <article><span className="metric-icon tone-violet"><Icon name="layers" size={18} /></span><div><small>双命名空间</small><strong>820 <i>/</i> 1,004</strong><em>Migration / Product</em></div></article>
        <article><span className="metric-icon tone-amber"><Icon name="test" size={18} /></span><div><small>严格认证用例</small><strong>408</strong><em>全部保持 NOT_RUN</em></div></article>
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
