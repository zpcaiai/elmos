"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Icon, type IconName } from "./Icon";

const navigation: Array<{ href: string; label: string; hint: string; icon: IconName }> = [
  { href: "/", label: "总览", hint: "Overview", icon: "home" },
  { href: "/migration", label: "迁移工坊", hint: "Migration", icon: "route" },
  { href: "/commercialization", label: "商业化控制面", hint: "Control plane", icon: "shield" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const current = navigation.find((item) => item.href === "/" ? pathname === "/" : pathname.startsWith(item.href)) ?? navigation[0];

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`} aria-label="主导航">
        <div className="brand-row">
          <Link className="brand-mark" href="/" onClick={() => setMobileOpen(false)}>E</Link>
          <div><strong>ELMOS</strong><span>控制中心</span></div>
          <button className="icon-button sidebar-close" aria-label="关闭导航" onClick={() => setMobileOpen(false)}><Icon name="close" /></button>
        </div>
        <nav className="primary-nav">
          <span className="nav-label">工作空间</span>
          {navigation.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link className={`nav-item ${active ? "active" : ""}`} href={item.href} key={item.href} onClick={() => setMobileOpen(false)} aria-current={active ? "page" : undefined}>
                <Icon name={item.icon} size={19} />
                <span><strong>{item.label}</strong><small>{item.hint}</small></span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-spacer" />
        <div className="guardrail-card">
          <span className="guardrail-icon"><Icon name="lock" size={17} /></span>
          <div><strong>Fail closed</strong><small>未运行不等于通过</small></div>
        </div>
        <nav className="secondary-nav" aria-label="辅助导航">
          <a className="secondary-link" href="/api/capabilities/migration" target="_blank" rel="noreferrer"><Icon name="box" size={18} />能力 API</a>
          <span className="secondary-link muted"><Icon name="help" size={18} />帮助与文档</span>
        </nav>
        <div className="profile-row">
          <span className="avatar">迁</span>
          <div><strong>迁移负责人</strong><small>本地工作区</small></div>
          <Icon name="chevron" size={16} />
        </div>
      </aside>
      {mobileOpen && <button className="sidebar-scrim" aria-label="关闭导航遮罩" onClick={() => setMobileOpen(false)} />}
      <div className="content-shell">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="打开导航" onClick={() => setMobileOpen(true)}><Icon name="menu" /></button>
          <div className="breadcrumb"><span>ELMOS</span><Icon name="chevron" size={13} /><strong>{current.label}</strong></div>
          <div className="topbar-actions">
            <span className="environment-pill"><i /> 本地契约环境</span>
            <span className="topbar-divider" />
            <button className="icon-button" aria-label="刷新页面" onClick={() => location.reload()}><Icon name="refresh" size={18} /></button>
            <span className="top-avatar">迁</span>
          </div>
        </header>
        <main id="main-content" className="main-content" tabIndex={-1}>{children}</main>
      </div>
    </div>
  );
}
