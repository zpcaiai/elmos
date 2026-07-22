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
          <h1>早上好，迁移负责人</h1>
          <p>
            两套新能力已经进入同一个操作界面。你可以先规划、检查与准备证据；任何执行、认证、合并或发布仍由对应的外部门禁和人工权限决定。
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
    </div>
  );
}
