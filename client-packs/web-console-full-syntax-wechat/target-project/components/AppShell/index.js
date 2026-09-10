// Top-level helpers and constants
try { const navigation = [
    { href: "/", label: "总览", enLabel: "Overview", hint: "Overview", icon: "home", group: "user" },
    { href: "/spring", label: "Spring 老项目翻新", enLabel: "Spring modernization", hint: "Legacy modernization", icon: "workflow", group: "user" },
    { href: "/translation", label: "全库跨语言转换", enLabel: "Language translation", hint: "Directed routes", icon: "code", group: "user" },
    { href: "/generation", label: "多语言项目生成", enLabel: "Project generation", hint: "Project synthesis", icon: "spark", group: "user" },
    { href: "/migration", label: "国产数据库 SQL 转换", enLabel: "ChinaDB SQL conversion", hint: "Migration / ChinaDB SQL", icon: "route", group: "user" },
    { href: "/intake", label: "多模态输入", enLabel: "Multimodal intake", hint: "Files / media / packages", icon: "file", group: "operations" },
    { href: "/frontend", label: "前端转换工厂", enLabel: "Frontend transformation", hint: "Vue / React / 小程序 / ArkUI / Flutter", icon: "route", group: "operations" },
    { href: "/repositories", label: "代码仓库工作区", enLabel: "Repository workspace", hint: "GitHub / Gitee / Git", icon: "box", group: "operations" },
    { href: "/orchestration", label: "任务编排与模型路由", enLabel: "Task orchestration", hint: "DAG / cost routing", icon: "workflow", group: "operations" },
    { href: "/capabilities", label: "功能能力中心", enLabel: "Capability center", hint: "平台能做什么", icon: "test", group: "operations" },
    { href: "/pricing", label: "套餐与用量", enLabel: "Plans and usage", hint: "Plans / credits", icon: "layers", group: "operations" },
    { href: "/workbench", label: "实时工作台", enLabel: "Live Workbench", hint: "Read / run / debug / learn", icon: "code", group: "operations" },
    { href: "/admin", label: "运营管理端", enLabel: "Operations admin", hint: "Operations", icon: "settings", group: "operations" },
    { href: "/observability", label: "全链路观测与存证", enLabel: "Observability & SLSA", hint: "OTLP & SLSA", icon: "shield", group: "operations" },
    { href: "/governance", label: "契约治理与变异", enLabel: "Governance & Mutation", hint: "API diff & Mutate", icon: "route", group: "operations" },
    { href: "/commercialization", label: "商业化控制面", enLabel: "Commercial control plane", hint: "Tenant / Runner / Evidence", icon: "shield", group: "operations" },
    { href: "/proof-loop", label: "现代化证据闭环", enLabel: "Modernization proof loop", hint: "Evidence loop", icon: "shield", group: "operations" },
    { href: "/playground", label: "转换验证沙箱", enLabel: "Transformation sandbox", hint: "Sandbox", icon: "spark", group: "operations" },
    { href: "/smoke", label: "一键冒烟运行", enLabel: "Smoke run", hint: "Smoke", icon: "test", group: "operations" },
]; } catch(e) {}
try { const operationsSurfaces = new Set(navigation.filter((item) => item.group === "operations").map((item) => item.href)); } catch(e) {}
try { const mobileNavigation = navigation.filter((item) => ["/", "/spring", "/translation", "/generation", "/migration"].includes(item.href)); } catch(e) {}
try { const commands = [
    ...navigation.map((item) => ({ ...item, group: "页面", keywords: `${item.label} ${item.hint}` })),
    { href: "/spring", label: "评估 Spring 老项目", hint: "XML / Java 8 / Jakarta / Boot 3.5.3", icon: "workflow", group: "业务线", keywords: "Spring 老项目 翻新 XML Java 8 Jakarta Security JPA" },
    { href: "/translation", label: "选择跨语言方向路线", hint: "15 语言 · 210 路线 · 本地通过 0 · 全部 NOT_RUN", icon: "code", group: "业务线", keywords: "跨语言 转换 210 routes 15 languages Java C# Go Rust Python TypeScript C++ Objective-C Swift PHP Kotlin React Flutter VB6 VC++6 NOT_RUN" },
    { href: "/intake", label: "接入多模态项目资料", hint: "Audio / Image / PDF / Word / Folder / Archive", icon: "file", group: "能力", keywords: "多模态 输入 音频 图片 PDF Word 文件夹 压缩包 OCR ASR" },
    { href: "/migration/sql", label: "运行国产数据库 SQL 预检", hint: "DM8 / KingbaseES / openGauss / TiDB / OceanBase / GaussDB", icon: "database", group: "业务线", keywords: "ChinaDB 国产数据库 SQL 预检 转换 DM8 人大金仓 openGauss TiDB GBase 瀚高 OceanBase GaussDB GoldenDB" },
    { href: "/migration", label: "查看 M36 开发者工作流", hint: "IDE / CLI / PR Bot", icon: "spark", group: "能力", keywords: "M36 开发者 IDE CLI PR Bot" },
    { href: "/migration", label: "查看扩展市场与签名策略", hint: "SDK / Signing / Revocation", icon: "box", group: "能力", keywords: "Marketplace 扩展 市场 SDK 签名 撤销" },
    { href: "/proof-loop", label: "运行现代化证据闭环", hint: "Golden route / Preview / Live validation / Certificate", icon: "shield", group: "平台运营", keywords: "现代化 预览 验证 证书 证据闭环" },
    { href: "/commercialization", label: "查看商业化可信链", hint: "Tenant / Runner / Evidence / Policy", icon: "shield", group: "平台运营", keywords: "租户 runner 证据 授权 商业化 控制面" },
    { href: "/pricing", label: "比较人民币套餐", hint: "免费体验 / 月付 / 年付", icon: "layers", group: "商业", keywords: "套餐 价格 人民币 token credit 免费 月付 年付" },
    { href: "/generation", label: "创建多语言项目草稿", hint: "8 种语言 · 多实体 PostgreSQL", icon: "spark", group: "能力", keywords: "生成 项目 synthesis Java Python C# TypeScript Go Kotlin PHP Rust 多实体" },
    { href: "/workbench", label: "打开实时工作台", hint: "固定 10 分钟隔离运行与调试", icon: "code", group: "能力", keywords: "workbench 实时 阅读 运行 调试 学习 隔离 sandbox" },
    { href: "/frontend", label: "规划前端技术栈转换", hint: "472 项前端转换功能 / 30 条路线", icon: "route", group: "能力", keywords: "前端 Vue React 小程序 ArkUI Flutter 迁移 转换" },
    { href: "/repositories", label: "拉取并修改代码仓库", hint: "GitHub / Gitee / 通用 Git", icon: "box", group: "能力", keywords: "仓库 repository GitHub Gitee clone 配置 部署 修改" },
    { href: "/capabilities", label: "查看平台已实现的功能", hint: "按业务域列出实现范围与验证状态", icon: "test", group: "功能", keywords: "功能 能力 中心 业务域 实现 验证 覆盖范围" },
    { href: "/admin", label: "查看操作日志与性能", hint: "用户操作 / API / 错误 / P95", icon: "settings", group: "平台运营", keywords: "管理端 操作日志 性能 错误 P95 observability" },
]; } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    children: {
      type: null,
      value: null,
    },
  },
  data: {
    mobileOpen: false,
    commandOpen: false,
    commandQuery: "",
    commandActive: 0,
    showBackToTop: false,
    telemetryEnabled: true,
    profileOpen: false,
    commandPanel: {"current":null},
    commandInput: {"current":null},
    returnFocus: {"current":null},
    visibleCommands: [],
  },
  lifetimes: {
    attached() {
      const setMobileOpen = (val) => { this.setData({ mobileOpen: typeof val === "function" ? val(this.data.mobileOpen) : val }); };
      const setCommandOpen = (val) => { this.setData({ commandOpen: typeof val === "function" ? val(this.data.commandOpen) : val }); };
      const setCommandQuery = (val) => { this.setData({ commandQuery: typeof val === "function" ? val(this.data.commandQuery) : val }); };
      const setCommandActive = (val) => { this.setData({ commandActive: typeof val === "function" ? val(this.data.commandActive) : val }); };
      const setShowBackToTop = (val) => { this.setData({ showBackToTop: typeof val === "function" ? val(this.data.showBackToTop) : val }); };
      const setTelemetryEnabled = (val) => { this.setData({ telemetryEnabled: typeof val === "function" ? val(this.data.telemetryEnabled) : val }); };
      const setProfileOpen = (val) => { this.setData({ profileOpen: typeof val === "function" ? val(this.data.profileOpen) : val }); };
      const commandPanel = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const commandInput = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const returnFocus = { current: { focus: () => {}, scrollIntoView: () => {} } };
      // Lifecycle effect effect_0
      (async () => {
        try {
          const skipLink = document.querySelector(".skip-link");
    if (skipLink) {
        skipLink.textContent = english ? "Skip to main content" : "跳到主要内容";
    }
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_1
      (async () => {
        try {
          function handleShortcut(event) {
        if ((event.metaKey || event.ctrlKey) && event.key.toLocaleLowerCase() === "k") {
            event.preventDefault();
            if (commandOpen)
                closeCommand();
            else
                openCommand();
        }
        if (event.key === "Escape" && commandOpen)
            closeCommand();
    }
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_2
      (async () => {
        try {
          if (!commandOpen)
        return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => commandInput.current?.focus());
    return () => { document.body.style.overflow = previousOverflow; };
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_3
      (async () => {
        try {
          function updateBackToTop() {
        setShowBackToTop(window.scrollY > 640);
    }
    updateBackToTop();
    window.addEventListener("scroll", updateBackToTop, { passive: true });
    return () => window.removeEventListener("scroll", updateBackToTop);
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_4
      (async () => {
        try {
          try {
        setTelemetryEnabled(localStorage.getItem("elmos:telemetry-enabled:v1") !== "off");
    }
    catch {
        setTelemetryEnabled(true);
    }
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
    },
    detached() {
    },
  },
  methods: {
    openCommand(trigger) {
      const commandPanel = this.data.commandPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const commandInput = this.data.commandInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const returnFocus = this.data.returnFocus || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        returnFocus.current = trigger
        ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    setCommandActive(0);
    setCommandOpen(true);
      } catch (err) {
        console.warn("openCommand execution warning:", err);
      }
    },
    closeCommand() {
      const commandPanel = this.data.commandPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const commandInput = this.data.commandInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const returnFocus = this.data.returnFocus || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        setCommandOpen(false);
    setCommandQuery("");
    setCommandActive(0);
    requestAnimationFrame(() => returnFocus.current?.focus());
      } catch (err) {
        console.warn("closeCommand execution warning:", err);
      }
    },
    handleCommandKey(event) {
      const commandPanel = this.data.commandPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const commandInput = this.data.commandInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const returnFocus = this.data.returnFocus || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (event.key === "ArrowDown") {
        event.preventDefault();
        if (visibleCommands.length === 0)
            return;
        setCommandActive((index) => Math.min(index + 1, visibleCommands.length - 1));
    }
    if (event.key === "ArrowUp") {
        event.preventDefault();
        if (visibleCommands.length === 0)
            return;
        setCommandActive((index) => Math.max(index - 1, 0));
    }
    if (event.key === "Enter" && visibleCommands[commandActive]) {
        event.preventDefault();
        const target = visibleCommands[commandActive].href;
        closeCommand();
        router.push(target);
    }
      } catch (err) {
        console.warn("handleCommandKey execution warning:", err);
      }
    },
    containDialogFocus(event) {
      const commandPanel = this.data.commandPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const commandInput = this.data.commandInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const returnFocus = this.data.returnFocus || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (event.key !== "Tab" || !commandPanel.current)
        return;
    const focusable = Array.from(commandPanel.current.querySelectorAll("a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex='-1'])")).filter((element) => element.getClientRects().length > 0);
    if (focusable.length === 0)
        return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
    }
    else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
    }
      } catch (err) {
        console.warn("containDialogFocus execution warning:", err);
      }
    },
    reloadPage() {
      const commandPanel = this.data.commandPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const commandInput = this.data.commandInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const returnFocus = this.data.returnFocus || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (window.confirm("重新载入会清除本页尚未保存的输入。是否继续？")) {
        window.location.reload();
    }
      } catch (err) {
        console.warn("reloadPage execution warning:", err);
      }
    },
    scrollToTop() {
      const commandPanel = this.data.commandPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const commandInput = this.data.commandInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const returnFocus = this.data.returnFocus || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
      } catch (err) {
        console.warn("scrollToTop execution warning:", err);
      }
    },
    toggleTelemetry() {
      const commandPanel = this.data.commandPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const commandInput = this.data.commandInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const returnFocus = this.data.returnFocus || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const enabled = !telemetryEnabled;
    setTelemetryEnabled(enabled);
    window.dispatchEvent(new CustomEvent("elmos:telemetry-preference", { detail: { enabled } }));
      } catch (err) {
        console.warn("toggleTelemetry execution warning:", err);
      }
    },
    closeSidebar() {
      const commandPanel = this.data.commandPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const commandInput = this.data.commandInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const returnFocus = this.data.returnFocus || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        setMobileOpen(false);
    setProfileOpen(false);
      } catch (err) {
        console.warn("closeSidebar execution warning:", err);
      }
    },
    toggleTopProfileMenu() {
      const commandPanel = this.data.commandPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const commandInput = this.data.commandInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const returnFocus = this.data.returnFocus || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const nextOpen = !profileOpen;
    setProfileOpen(nextOpen);
    if (nextOpen && window.matchMedia("(max-width: 900px)").matches) {
        setMobileOpen(true);
    }
      } catch (err) {
        console.warn("toggleTopProfileMenu execution warning:", err);
      }
    },
    async logout() {
      const commandPanel = this.data.commandPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const commandInput = this.data.commandInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const returnFocus = this.data.returnFocus || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        await account.logout();
    closeSidebar();
      } catch (err) {
        console.warn("logout execution warning:", err);
      }
    },
  },
});
