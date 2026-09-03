"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import styles from "./AppShell.module.css";
import { useAccountSession } from "./AccountSessionProvider";
import { Icon, type IconName } from "./Icon";
import { useUiPreferences } from "./UiPreferencesProvider";

type SurfaceGroup = "user" | "operations";

const navigation: Array<{
  href: string;
  label: string;
  enLabel: string;
  hint: string;
  icon: IconName;
  group: SurfaceGroup;
}> = [
  { href: "/", label: "总览", enLabel: "Overview", hint: "Overview", icon: "home", group: "user" },
  { href: "/spring", label: "Spring 老项目翻新", enLabel: "Spring modernization", hint: "Legacy modernization", icon: "workflow", group: "user" },
  { href: "/translation", label: "全库跨语言转换", enLabel: "Language translation", hint: "Directed routes", icon: "code", group: "user" },
  { href: "/intake", label: "多模态输入", enLabel: "Multimodal intake", hint: "Files / media / packages", icon: "file", group: "user" },
  { href: "/generation", label: "多语言项目生成", enLabel: "Project generation", hint: "Project synthesis", icon: "spark", group: "user" },
  { href: "/frontend", label: "前端转换工厂", enLabel: "Frontend transformation", hint: "Vue / React / 小程序 / ArkUI / Flutter", icon: "route", group: "user" },
  { href: "/repositories", label: "代码仓库工作区", enLabel: "Repository workspace", hint: "GitHub / Gitee / Git", icon: "box", group: "user" },
  { href: "/orchestration", label: "任务编排与模型路由", enLabel: "Task orchestration", hint: "DAG / cost routing", icon: "workflow", group: "user" },
  { href: "/migration", label: "迁移工坊", enLabel: "Migration studio", hint: "Migration", icon: "route", group: "user" },
  { href: "/capabilities", label: "功能能力中心", enLabel: "Capability center", hint: "平台能做什么", icon: "test", group: "user" },
  { href: "/pricing", label: "套餐与用量", enLabel: "Plans and usage", hint: "Plans / credits", icon: "layers", group: "user" },
  { href: "/admin", label: "运营管理端", enLabel: "Operations admin", hint: "Operations", icon: "settings", group: "operations" },
  { href: "/observability", label: "全链路观测与存证", enLabel: "Observability & SLSA", hint: "OTLP & SLSA", icon: "shield", group: "operations" },
  { href: "/governance", label: "契约治理与变异", enLabel: "Governance & Mutation", hint: "API diff & Mutate", icon: "route", group: "operations" },
  { href: "/commercialization", label: "商业化控制面", enLabel: "Commercial control plane", hint: "Tenant / Runner / Evidence", icon: "shield", group: "operations" },
  { href: "/proof-loop", label: "现代化证据闭环", enLabel: "Modernization proof loop", hint: "Evidence loop", icon: "shield", group: "operations" },
  { href: "/playground", label: "转换验证沙箱", enLabel: "Transformation sandbox", hint: "Sandbox", icon: "spark", group: "operations" },
  { href: "/smoke", label: "一键冒烟运行", enLabel: "Smoke run", hint: "Smoke", icon: "test", group: "operations" },
];

const operationsSurfaces = new Set(
  navigation.filter((item) => item.group === "operations").map((item) => item.href),
);

const mobileNavigation = navigation.filter((item) =>
  ["/", "/spring", "/translation", "/intake", "/generation", "/frontend", "/capabilities"].includes(item.href),
);

const commands = [
  ...navigation.map((item) => ({ ...item, group: "页面", keywords: `${item.label} ${item.hint}` })),
  { href: "/spring", label: "评估 Spring 老项目", hint: "XML / Java 8 / Jakarta / Boot 3.5.3", icon: "workflow" as IconName, group: "业务线", keywords: "Spring 老项目 翻新 XML Java 8 Jakarta Security JPA" },
  { href: "/translation", label: "选择跨语言方向路线", hint: "13 语言活动矩阵 · 156 条路线", icon: "code" as IconName, group: "业务线", keywords: "跨语言 转换 156 routes Java C# Go Rust Python TypeScript C++ Objective-C Swift PHP Kotlin React Flutter" },
  { href: "/intake", label: "接入多模态项目资料", hint: "Audio / Image / PDF / Word / Folder / Archive", icon: "file" as IconName, group: "业务线", keywords: "多模态 输入 音频 图片 PDF Word 文件夹 压缩包 OCR ASR" },
  { href: "/migration/sql", label: "运行国产数据库 SQL 预检", hint: "DM8 / KingbaseES / openGauss / TiDB / OceanBase / GaussDB", icon: "database" as IconName, group: "业务线", keywords: "ChinaDB 国产数据库 SQL 预检 转换 DM8 人大金仓 openGauss TiDB GBase 瀚高 OceanBase GaussDB GoldenDB" },
  { href: "/migration", label: "查看 M36 开发者工作流", hint: "IDE / CLI / PR Bot", icon: "spark" as IconName, group: "能力", keywords: "M36 开发者 IDE CLI PR Bot" },
  { href: "/migration", label: "查看扩展市场与签名策略", hint: "SDK / Signing / Revocation", icon: "box" as IconName, group: "能力", keywords: "Marketplace 扩展 市场 SDK 签名 撤销" },
  { href: "/proof-loop", label: "运行现代化证据闭环", hint: "Golden route / Preview / Live validation / Certificate", icon: "shield" as IconName, group: "平台运营", keywords: "现代化 预览 验证 证书 证据闭环" },
  { href: "/commercialization", label: "查看商业化可信链", hint: "Tenant / Runner / Evidence / Policy", icon: "shield" as IconName, group: "平台运营", keywords: "租户 runner 证据 授权 商业化 控制面" },
  { href: "/pricing", label: "比较人民币套餐", hint: "免费体验 / 月付 / 年付", icon: "layers" as IconName, group: "商业", keywords: "套餐 价格 人民币 token credit 免费 月付 年付" },
  { href: "/generation", label: "创建多语言项目草稿", hint: "8 种语言 · 多实体 PostgreSQL", icon: "spark" as IconName, group: "能力", keywords: "生成 项目 synthesis Java Python C# TypeScript Go Kotlin PHP Rust 多实体" },
  { href: "/frontend", label: "规划前端技术栈转换", hint: "472 项前端转换功能 / 30 条路线", icon: "route" as IconName, group: "能力", keywords: "前端 Vue React 小程序 ArkUI Flutter 迁移 转换" },
  { href: "/repositories", label: "拉取并修改代码仓库", hint: "GitHub / Gitee / 通用 Git", icon: "box" as IconName, group: "能力", keywords: "仓库 repository GitHub Gitee clone 配置 部署 修改" },
  { href: "/capabilities", label: "查看平台已实现的功能", hint: "按业务域列出实现范围与验证状态", icon: "test" as IconName, group: "功能", keywords: "功能 能力 中心 业务域 实现 验证 覆盖范围" },
  { href: "/admin", label: "查看操作日志与性能", hint: "用户操作 / API / 错误 / P95", icon: "settings" as IconName, group: "平台运营", keywords: "管理端 操作日志 性能 错误 P95 observability" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const account = useAccountSession();
  const preferences = useUiPreferences();
  const english = preferences.locale === "en";
  const [mobileOpen, setMobileOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState("");
  const [commandActive, setCommandActive] = useState(0);
  const [showBackToTop, setShowBackToTop] = useState(false);
  const [telemetryEnabled, setTelemetryEnabled] = useState(true);
  const [profileOpen, setProfileOpen] = useState(false);
  const commandPanel = useRef<HTMLElement>(null);
  const commandInput = useRef<HTMLInputElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const accountPermissions = new Set(account.principal?.permissions ?? []);
  const hasAdminAccess = account.status === "authenticated"
    && account.principal?.isPlatformAdmin === true
    && accountPermissions.has("admin:read");
  const userNavigation = navigation.filter((item) => item.group === "user");
  const operationsNavigation = hasAdminAccess
    ? navigation.filter((item) => item.group === "operations")
    : [];
  const adminSurface = pathname.startsWith("/admin");
  const current = navigation.find((item) => item.href === "/" ? pathname === "/" : pathname.startsWith(item.href)) ?? navigation[0];
  const navLabel = (item: (typeof navigation)[number]) =>
    english ? item.enLabel : item.label;
  // Routes outside the primary navigation fell through to navigation[0], so
  // /login used to breadcrumb as "总览" and /admin/login as "运营管理端".
  const standaloneLabels: Array<[string, string, string]> = [
    ["/admin/login", "管理员登录", "Administrator sign in"],
    ["/login", "用户登录", "User sign in"],
    ["/register", "注册账户", "Create account"],
    ["/help", "帮助与就绪状态", "Help and readiness"],
    ["/account", "账户与组织", "Account and organizations"],
  ];
  const standalone = standaloneLabels.find(([href]) => pathname.startsWith(href));
  const currentLabel = standalone
    ? (english ? standalone[2] : standalone[1])
    : navLabel(current);
  const visibleCommands = useMemo(() => {
    const needle = commandQuery.trim().toLocaleLowerCase("zh-CN");
    return commands
      .filter((item) => !operationsSurfaces.has(item.href) || hasAdminAccess)
      .filter((item) => !needle || `${item.label} ${item.hint} ${item.keywords}`.toLocaleLowerCase("zh-CN").includes(needle));
  }, [commandQuery, hasAdminAccess]);

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

  useEffect(() => {
    function updateBackToTop() {
      setShowBackToTop(window.scrollY > 640);
    }
    updateBackToTop();
    window.addEventListener("scroll", updateBackToTop, { passive: true });
    return () => window.removeEventListener("scroll", updateBackToTop);
  }, []);

  useEffect(() => {
    try {
      setTelemetryEnabled(localStorage.getItem("elmos:telemetry-enabled:v1") !== "off");
    } catch {
      setTelemetryEnabled(true);
    }
  }, []);

  function openCommand(trigger?: HTMLElement) {
    returnFocus.current = trigger
      ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
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
      if (visibleCommands.length === 0) return;
      setCommandActive((index) => Math.min(index + 1, visibleCommands.length - 1));
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (visibleCommands.length === 0) return;
      setCommandActive((index) => Math.max(index - 1, 0));
    }
    if (event.key === "Enter" && visibleCommands[commandActive]) {
      event.preventDefault();
      const target = visibleCommands[commandActive].href;
      closeCommand();
      router.push(target);
    }
  }

  function containDialogFocus(event: React.KeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab" || !commandPanel.current) return;
    const focusable = Array.from(commandPanel.current.querySelectorAll<HTMLElement>(
      "a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex='-1'])",
    )).filter((element) => element.getClientRects().length > 0);
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function reloadPage() {
    if (window.confirm("重新载入会清除本页尚未保存的输入。是否继续？")) {
      window.location.reload();
    }
  }

  function scrollToTop() {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
  }

  function toggleTelemetry() {
    const enabled = !telemetryEnabled;
    setTelemetryEnabled(enabled);
    window.dispatchEvent(new CustomEvent("elmos:telemetry-preference", { detail: { enabled } }));
  }

  function closeSidebar() {
    setMobileOpen(false);
    setProfileOpen(false);
  }

  function toggleTopProfileMenu() {
    const nextOpen = !profileOpen;
    setProfileOpen(nextOpen);
    if (nextOpen && window.matchMedia("(max-width: 900px)").matches) {
      setMobileOpen(true);
    }
  }

  async function logout() {
    await account.logout();
    closeSidebar();
  }

  return (
    <div className={`app-shell ${adminSurface ? "admin-shell" : ""}`}>
      <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`} aria-label={english ? "Primary navigation" : "主导航"}>
        <div className="brand-row">
          <Link className="brand-mark" href="/" onClick={() => setMobileOpen(false)}>E</Link>
          <div>
            <strong>ELMOS</strong>
            <span>{adminSurface
              ? (english ? "Administrator center" : "管理员中心")
              : (english ? "Control center" : "控制中心")}</span>
          </div>
          <button className="icon-button sidebar-close" aria-label={english ? "Close navigation" : "关闭导航"} onClick={closeSidebar}><Icon name="close" /></button>
        </div>
        <nav className="primary-nav">
          <span className="nav-label">{english ? "Product features · user access" : "产品功能 · 用户端"}</span>
          {userNavigation.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link className={`nav-item ${active ? "active" : ""}`} href={item.href} key={item.href} onClick={closeSidebar} aria-current={active ? "page" : undefined}>
                <Icon name={item.icon} size={19} />
                <span><strong>{navLabel(item)}</strong><small>{item.hint}</small></span>
              </Link>
            );
          })}
          {operationsNavigation.length > 0 && (
            <>
              <span className="nav-label nav-label-operations">
                {english ? "Platform operations · administrator" : "平台运营 · 管理员端"}
              </span>
              {operationsNavigation.map((item) => {
                const active = pathname.startsWith(item.href);
                return (
                  <Link className={`nav-item admin-nav-item ${active ? "active" : ""}`} href={item.href} key={item.href} onClick={closeSidebar} aria-current={active ? "page" : undefined}>
                    <Icon name={item.icon} size={19} />
                    <span><strong>{navLabel(item)}</strong><small>{item.hint}</small></span>
                  </Link>
                );
              })}
            </>
          )}
        </nav>
        <div className="sidebar-spacer" />
        <div className="guardrail-card">
          <span className="guardrail-icon"><Icon name="lock" size={17} /></span>
          <div><strong>Fail closed</strong><small>{english ? "Not run is not passed" : "未运行不等于通过"}</small></div>
        </div>
        <nav className="secondary-nav" aria-label={english ? "Utility navigation" : "辅助导航"}>
          <a className={`secondary-link ${styles.readableSecondary}`} href="/api/capabilities/migration" target="_blank" rel="noreferrer"><Icon name="box" size={18} />{english ? "Capability API" : "能力 API"}</a>
          <button className={`secondary-link ${styles.readableSecondary}`} type="button" onClick={toggleTelemetry} data-telemetry-ignore="true">
            <Icon name={telemetryEnabled ? "check" : "close"} size={18} />
            {english
              ? `Anonymous performance log: ${telemetryEnabled ? "on" : "off"}`
              : `匿名性能日志：${telemetryEnabled ? "开" : "关"}`}
          </button>
          <Link className={`secondary-link ${styles.readableSecondary}`} href="/help"><Icon name="help" size={18} />{english ? "Help and readiness" : "帮助与就绪状态"}</Link>
        </nav>
        <div className="profile-area">
          <button
            className="profile-row"
            type="button"
            aria-expanded={profileOpen}
            aria-controls="account-profile-menu"
            onClick={() => setProfileOpen((open) => !open)}
          >
            <span className={`avatar ${hasAdminAccess ? "admin-avatar" : ""}`}>{account.principal?.displayName.slice(0, 1) ?? "访"}</span>
            <div>
              <strong>{account.principal?.displayName ?? (account.status === "not-configured" ? (english ? "Local development" : "本地开发模式") : (english ? "Signed out" : "未登录"))}</strong>
              <small>{account.principal
                ? `${hasAdminAccess ? (english ? "Administrator" : "管理员") + " · " : ""}${account.principal.organizationId}`
                : (english ? "No enterprise session" : "无企业会话")}</small>
            </div>
            <Icon name="chevron" size={16} />
          </button>
          {profileOpen && (
            <div className="profile-menu" id="account-profile-menu">
              {account.status === "authenticated" && account.principal ? (
                <>
                  <div className="profile-menu-summary">
                    <strong>{account.principal.displayName}</strong>
                    <small>{account.principal.roles.join(" · ") || "无业务角色"}</small>
                    {hasAdminAccess && <span className="admin-session-badge">管理员会话</span>}
                  </div>
                  <Link href="/account" onClick={closeSidebar}>
                    {english ? "Account and organizations" : "账户与组织"}
                  </Link>
                  {account.principal.memberships.length > 1 && (
                    <label>
                      <span>{english ? "Current tenant" : "当前租户"}</span>
                      <select
                        value={account.principal.organizationId}
                        onChange={(event) => void account.switchTenant(event.target.value)}
                      >
                        {account.principal.memberships.map((membership) => (
                          <option value={membership.organizationId} key={membership.organizationId}>
                            {membership.organizationId}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <button type="button" onClick={() => void logout()}>{english ? "Sign out securely" : "安全退出"}</button>
                </>
              ) : (
                <>
                  <Link href={`/login?${new URLSearchParams({ returnTo: pathname })}`} onClick={closeSidebar}>
                    {english ? "User sign in" : "用户登录"}
                  </Link>
                  <Link className="profile-admin-login-link" href="/admin/login" onClick={closeSidebar}>
                    {english ? "Administrator entry" : "管理员入口"}
                  </Link>
                </>
              )}
            </div>
          )}
        </div>
      </aside>
      {mobileOpen && <button className="sidebar-scrim" aria-label={english ? "Close navigation overlay" : "关闭导航遮罩"} onClick={closeSidebar} />}
      <div className="content-shell">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label={english ? "Open navigation" : "打开导航"} onClick={() => setMobileOpen(true)}><Icon name="menu" /></button>
          <div className="breadcrumb"><span>ELMOS</span><Icon name="chevron" size={13} /><strong>{currentLabel}</strong></div>
          <button className="command-trigger" onClick={(event) => openCommand(event.currentTarget)} aria-label={english ? "Open global search" : "打开全局搜索"}>
            <Icon name="search" size={16} /><span>{english ? "Search pages and capabilities" : "搜索页面或功能"}</span><kbd>⌘ K</kbd>
          </button>
          <div className="topbar-actions">
            <span className="environment-pill"><i /> {english ? "Local contract environment" : "本地契约环境"}</span>
            <span className="topbar-divider" />
            <button
              className="preference-button"
              type="button"
              aria-label={english ? "Switch navigation and help to Chinese" : "将导航和帮助切换为英文"}
              onClick={() => preferences.setLocale(english ? "zh-CN" : "en")}
            >
              {english ? "中" : "EN"}
            </button>
            <button
              className="preference-button"
              type="button"
              aria-label={preferences.theme === "light" ? (english ? "Use dark theme" : "使用深色主题") : (english ? "Use light theme" : "使用浅色主题")}
              onClick={() => preferences.setTheme(preferences.theme === "light" ? "dark" : "light")}
            >
              {preferences.theme === "light" ? "☾" : "☀"}
            </button>
            <button className="icon-button" aria-label="重新载入当前页面（会清除未保存输入）" onClick={reloadPage}><Icon name="refresh" size={18} /></button>
            {account.status === "authenticated" ? (
              <button
                className={`top-avatar ${hasAdminAccess ? "admin-avatar" : ""}`}
                type="button"
                aria-label="打开账户菜单"
                onClick={toggleTopProfileMenu}
              >
                {account.principal?.displayName.slice(0, 1) ?? "企"}
              </button>
            ) : (
              <div className="anonymous-login-actions">
                <Link className="top-login-link" href={`/login?${new URLSearchParams({ returnTo: pathname })}`}>
                  {english ? "User sign in" : "用户登录"}
                </Link>
                <Link className="top-login-link top-admin-login-link" href="/admin/login">
                  {english ? "Admin" : "管理员入口"}
                </Link>
              </div>
            )}
          </div>
        </header>
        <main id="main-content" className="main-content" tabIndex={-1}>{children}</main>
      </div>
      <nav className="mobile-bottom-nav" aria-label={english ? "Mobile primary navigation" : "移动端主导航"}>
        {mobileNavigation.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const label = navLabel(item);
          return <Link href={item.href} className={active ? "active" : ""} aria-current={active ? "page" : undefined} key={item.href}><Icon name={item.icon} size={19} /><span>{english ? label : label.replace("Spring 老项目翻新", "Spring").replace("全库跨语言转换", "转换").replace("多语言项目生成", "生成").replace("前端转换工厂", "前端").replace("功能能力中心", "功能")}</span></Link>;
        })}
      </nav>
      {showBackToTop && <button className="back-to-top" type="button" onClick={scrollToTop} aria-label="返回页面顶部">
        <Icon name="arrow" size={15} /><span>返回顶部</span>
      </button>}
      {commandOpen && <div className="command-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeCommand(); }}>
        <section ref={commandPanel} className="command-panel" role="dialog" aria-modal="true" aria-labelledby="command-title" onKeyDown={containDialogFocus}>
          <h2 id="command-title" className="sr-only">全局搜索</h2>
          <div className="command-search"><Icon name="search" size={20} /><input ref={commandInput} value={commandQuery} onChange={(event) => { setCommandQuery(event.target.value); setCommandActive(0); }} onKeyDown={handleCommandKey} placeholder="搜索页面或功能…" aria-label="搜索页面或功能" role="combobox" aria-expanded="true" aria-autocomplete="list" aria-controls="command-results" aria-activedescendant={visibleCommands.length ? `command-result-${commandActive}` : undefined} /><button className="icon-button command-close" type="button" aria-label="关闭全局搜索" onClick={closeCommand}><Icon name="close" size={17} /></button><kbd>ESC</kbd></div>
          <div className="command-results" id="command-results" role="listbox" aria-label="搜索结果">
            {visibleCommands.map((item, index) => <Link href={item.href} role="option" aria-selected={index === commandActive} id={`command-result-${index}`} onClick={closeCommand} onMouseEnter={() => setCommandActive(index)} className={`command-result ${index === commandActive ? "active" : ""}`} key={`${item.group}-${item.label}`}>
              <span className="command-icon"><Icon name={item.icon} size={18} /></span>
              <span><strong>{item.label}</strong><small>{item.hint}</small></span>
              <em>{item.group}</em><Icon name="arrow" size={15} />
            </Link>)}
            {visibleCommands.length === 0 && <div className="command-empty"><Icon name="search" size={22} /><strong>没有匹配结果</strong><span>换个关键词，或直接输入页面名称。</span></div>}
          </div>
          <footer className="command-footer"><span><kbd>↑</kbd><kbd>↓</kbd> 浏览</span><span><kbd>↵</kbd> 打开</span><span>仅导航，不执行外部操作</span></footer>
        </section>
      </div>}
    </div>
  );
}
