"use client";

import Link from "next/link";
import { useUiPreferences } from "../components/UiPreferencesProvider";

const businessLines = [
  {
    href: "/generation",
    zh: "多语言项目生成",
    en: "Project generation",
    zhDescription: "从审阅后的需求或精确仓库 HEAD 生成可验证项目，并用持久租约执行。",
    enDescription: "Generate a verifiable project from reviewed requirements or an exact repository HEAD, then execute it under a durable lease.",
  },
  {
    href: "/translation",
    zh: "全库跨语言转换",
    en: "Language translation",
    zhDescription: "先发现、拆分并绑定方向路线；未知或未支持的语义必须显式阻断。",
    enDescription: "Discover, partition, and bind a directed route first; unknown or unsupported semantics stay explicitly blocked.",
  },
  {
    href: "/spring",
    zh: "Spring 老项目翻新",
    en: "Spring modernization",
    zhDescription: "对不可变仓库快照做指纹、计划、执行、验证和交付，不把本地成功当生产认证。",
    enDescription: "Fingerprint, plan, execute, verify, and deliver an immutable repository snapshot without treating local success as production certification.",
  },
] as const;

const deliverySteps = [
  ["1", "拉取精确提交", "Clone exact commit"],
  ["2", "只修改已批准路径", "Change approved paths only"],
  ["3", "本地提交并回读 HEAD", "Commit and re-read HEAD"],
  ["4", "非强制推送并校验远端 SHA", "Non-force push and verify remote SHA"],
  ["5", "幂等创建 PR", "Create an idempotent PR"],
] as const;

const readiness = [
  ["登录、租户与权限", "本地实现并有测试", "外部 IdP 全目录同步 NOT_RUN", "Identity, tenant, and permissions", "Locally implemented and tested", "External IdP directory sync NOT_RUN"],
  ["Git 仓库交付", "真实本地 Git 仓库通过", "GitHub / Gitee 现场执行 NOT_RUN", "Git delivery", "Real local Git fixture passed", "Live GitHub / Gitee execution NOT_RUN"],
  ["三业务线持久队列", "租约、TTL、容量与恢复通过", "多副本共享卷故障演练 NOT_RUN", "Durable queues", "Lease, TTL, capacity, and recovery passed", "Multi-replica shared-volume drill NOT_RUN"],
  ["管理端与审计", "租户范围日志、告警、用量、配置可见", "生产通知与部署证据 NOT_RUN", "Admin and audit", "Tenant-scoped logs, alerts, usage, and config visible", "Production notification and deployment evidence NOT_RUN"],
  ["客户端质量", "构建、浏览器、键盘与自动可访问性检查", "独立读屏、视觉基线审批与代表旅程 NOT_RUN", "Client quality", "Build, browser, keyboard, and automated accessibility checks", "Independent AT, visual approval, and representative journeys NOT_RUN"],
] as const;

export function HelpCenter() {
  const { locale } = useUiPreferences();
  const english = locale === "en";

  return (
    <div className="page-stack help-center">
      <header className="page-header">
        <div>
          <span className="overline">{english ? "Guidance · Evidence boundaries" : "操作指南 · 证据边界"}</span>
          <h1>{english ? "Help and readiness" : "帮助与就绪状态"}</h1>
          <p>
            {english
              ? "Use the three business lines and controlled repository workflow safely. Local engineering evidence is shown separately from external execution."
              : "安全使用三条业务线与受控仓库流程。本地工程证据与外部执行证据严格分开显示。"}
          </p>
        </div>
      </header>

      <section className="help-section" aria-labelledby="help-lines-title">
        <div className="section-heading">
          <div>
            <span className="overline">01</span>
            <h2 id="help-lines-title">{english ? "Choose a business line" : "选择业务线"}</h2>
          </div>
        </div>
        <div className="help-line-grid">
          {businessLines.map((line) => (
            <article key={line.href}>
              <h3>{english ? line.en : line.zh}</h3>
              <p>{english ? line.enDescription : line.zhDescription}</p>
              <Link className="text-link" href={line.href}>
                {english ? "Open workspace" : "打开工作区"} →
              </Link>
            </article>
          ))}
        </div>
      </section>

      <section className="help-section" aria-labelledby="help-delivery-title">
        <div className="section-heading">
          <div>
            <span className="overline">02</span>
            <h2 id="help-delivery-title">{english ? "Controlled repository delivery" : "受控仓库交付"}</h2>
          </div>
          <Link className="text-link" href="/repositories">
            {english ? "Open repository workspace" : "打开仓库工作区"}
          </Link>
        </div>
        <ol className="help-steps">
          {deliverySteps.map(([number, zh, en]) => (
            <li key={number}><span>{number}</span><strong>{english ? en : zh}</strong></li>
          ))}
        </ol>
        <p className="help-boundary">
          {english
            ? "Merge, deployment, infrastructure apply, and production database migration are not automatic effects of this workflow."
            : "合并、部署、基础设施应用和生产数据库迁移都不是该流程的自动副作用。"}
        </p>
      </section>

      <section className="help-section" aria-labelledby="help-readiness-title">
        <div className="section-heading">
          <div>
            <span className="overline">03</span>
            <h2 id="help-readiness-title">{english ? "Evidence and remaining external gates" : "证据与剩余外部门禁"}</h2>
          </div>
        </div>
        <div
          className="help-table-wrap"
          tabIndex={0}
          role="region"
          aria-label={english ? "Readiness evidence table" : "就绪证据表"}
        >
          <table className="help-readiness-table">
            <thead>
              <tr>
                <th scope="col">{english ? "Area" : "环节"}</th>
                <th scope="col">{english ? "Current local evidence" : "当前本地证据"}</th>
                <th scope="col">{english ? "External boundary" : "外部边界"}</th>
              </tr>
            </thead>
            <tbody>
              {readiness.map((row) => (
                <tr key={row[0]}>
                  <th scope="row">{english ? row[3] : row[0]}</th>
                  <td>{english ? row[4] : row[1]}</td>
                  <td><code>{english ? row[5] : row[2]}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="help-section help-admin" aria-labelledby="help-admin-title">
        <div>
          <span className="overline">04</span>
          <h2 id="help-admin-title">{english ? "Operate and diagnose" : "运营与诊断"}</h2>
          <p>
            {english
              ? "The admin console exposes tenant-scoped users/session context, tasks, repositories, audit, alerts, usage, and sanitized configuration."
              : "管理端按租户展示用户/会话上下文、任务、仓库、审计、告警、用量与脱敏配置。"}
          </p>
        </div>
        <Link className="button button-primary" href="/admin">{english ? "Open operations admin" : "打开运营管理端"}</Link>
      </section>
    </div>
  );
}
