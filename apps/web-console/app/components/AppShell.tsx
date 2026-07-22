"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { Icon, type IconName } from "./Icon";

const navigation: Array<{ href: string; label: string; hint: string; icon: IconName }> = [
  { href: "/", label: "总览", hint: "Overview", icon: "home" },
  { href: "/migration", label: "迁移工坊", hint: "Migration", icon: "route" },
  { href: "/commercialization", label: "商业化控制面", hint: "Control plane", icon: "shield" },
  { href: "/generation", label: "多语言项目生成", hint: "Project synthesis", icon: "spark" },
  { href: "/skills", label: "Skills 与验证", hint: "Qualification", icon: "test" },
];

const commands = [
  ...navigation.map((item) => ({ ...item, group: "页面", keywords: `${item.label} ${item.hint}` })),
  { href: "/migration", label: "查看 M36 开发者工作流", hint: "IDE / CLI / PR Bot", icon: "spark" as IconName, group: "能力", keywords: "M36 开发者 IDE CLI PR Bot" },
  { href: "/migration", label: "查看 M37 扩展 Marketplace", hint: "SDK / Signing / Revocation", icon: "box" as IconName, group: "能力", keywords: "M37 Marketplace SDK 签名 撤销" },
  { href: "/commercialization", label: "查看 B34–B38 可信链", hint: "Tenant / Runner / Evidence / Policy", icon: "shield" as IconName, group: "能力", keywords: "B34 B35 B36 B37 B38 租户 runner 证据 授权" },
  { href: "/generation", label: "创建多语言项目草稿", hint: "Java / Python / C#", icon: "spark" as IconName, group: "能力", keywords: "生成 项目 synthesis Java Spring Python FastAPI C# ASP.NET" },
  { href: "/skills", label: "查看 Batch 1–55 双命名空间", hint: "1,824 Skills / 408 cases", icon: "test" as IconName, group: "验证", keywords: "Batch 1 55 1824 408 strict cases" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState("");
  const [commandActive, setCommandActive] = useState(0);
  const commandInput = useRef<HTMLInputElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const current = navigation.find((item) => item.href === "/" ? pathname === "/" : pathname.startsWith(item.href)) ?? navigation[0];
  const visibleCommands = useMemo(() => {
    const needle = commandQuery.trim().toLocaleLowerCase("zh-CN");
    return commands.filter((item) => !needle || `${item.label} ${item.hint} ${item.keywords}`.toLocaleLowerCase("zh-CN").includes(needle));
  }, [commandQuery]);

  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLocaleLowerCase() === "k") {
        event.preventDefault();
        if (commandOpen) closeCommand();
        else openCommand();
      }
      if (event.key === "Escape" && commandOpen) closeCommand();
    }
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [commandOpen]);

  useEffect(() => {
    if (!commandOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => commandInput.current?.focus());
    return () => { document.body.style.overflow = previousOverflow; };
  }, [commandOpen]);

  function openCommand() {
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setCommandActive(0);
    setCommandOpen(true);
  }

  function closeCommand() {
    setCommandOpen(false);
    setCommandQuery("");
    setCommandActive(0);
    requestAnimationFrame(() => returnFocus.current?.focus());
  }

  function handleCommandKey(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setCommandActive((index) => Math.min(index + 1, visibleCommands.length - 1));
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setCommandActive((index) => Math.max(index - 1, 0));
    }
    if (event.key === "Enter" && visibleCommands[commandActive]) {
      event.preventDefault();
      const target = visibleCommands[commandActive].href;
      closeCommand();
      router.push(target);
    }
  }

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
          <button className="command-trigger" onClick={openCommand} aria-label="打开全局搜索">
            <Icon name="search" size={16} /><span>搜索页面、能力或批次</span><kbd>⌘ K</kbd>
          </button>
          <div className="topbar-actions">
            <span className="environment-pill"><i /> 本地契约环境</span>
            <span className="topbar-divider" />
            <button className="icon-button" aria-label="刷新页面" onClick={() => location.reload()}><Icon name="refresh" size={18} /></button>
            <span className="top-avatar">迁</span>
          </div>
        </header>
        <main id="main-content" className="main-content" tabIndex={-1}>{children}</main>
      </div>
      <nav className="mobile-bottom-nav" aria-label="移动端主导航">
        {navigation.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return <Link href={item.href} className={active ? "active" : ""} aria-current={active ? "page" : undefined} key={item.href}><Icon name={item.icon} size={19} /><span>{item.label.replace("商业化控制面", "控制面").replace("多语言项目生成", "生成").replace("Skills 与验证", "验证")}</span></Link>;
        })}
      </nav>
      {commandOpen && <div className="command-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeCommand(); }}>
        <section className="command-panel" role="dialog" aria-modal="true" aria-labelledby="command-title">
          <h2 id="command-title" className="sr-only">全局搜索</h2>
          <div className="command-search"><Icon name="search" size={20} /><input ref={commandInput} value={commandQuery} onChange={(event) => { setCommandQuery(event.target.value); setCommandActive(0); }} onKeyDown={handleCommandKey} placeholder="搜索页面、能力、Batch…" aria-label="搜索页面、能力或批次" aria-controls="command-results" aria-activedescendant={visibleCommands.length ? `command-result-${commandActive}` : undefined} /><kbd>ESC</kbd></div>
          <div className="command-results" id="command-results">
            {visibleCommands.map((item, index) => <Link href={item.href} id={`command-result-${index}`} onClick={closeCommand} onMouseEnter={() => setCommandActive(index)} className={`command-result ${index === commandActive ? "active" : ""}`} key={`${item.group}-${item.label}`}>
              <span className="command-icon"><Icon name={item.icon} size={18} /></span>
              <span><strong>{item.label}</strong><small>{item.hint}</small></span>
              <em>{item.group}</em><Icon name="arrow" size={15} />
            </Link>)}
            {visibleCommands.length === 0 && <div className="command-empty"><Icon name="search" size={22} /><strong>没有匹配结果</strong><span>尝试输入 Batch、能力或页面名称。</span></div>}
          </div>
          <footer className="command-footer"><span><kbd>↑</kbd><kbd>↓</kbd> 浏览</span><span><kbd>↵</kbd> 打开</span><span>仅导航，不执行外部操作</span></footer>
        </section>
      </div>}
    </div>
  );
}
