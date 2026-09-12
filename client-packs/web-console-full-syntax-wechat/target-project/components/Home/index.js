// Top-level helpers and constants
try { var workspaces = [
    {
        eyebrow: "BATCH 30 · SPRING",
        title: "Spring 老项目翻新",
        description: "识别经典 Spring、XML 与旧 Boot，显式处理 Java、Jakarta、Security、JPA、配置和真实启动证据。",
        href: "/spring",
        icon: "workflow",
        accent: "blue",
        meta: "3 种源形态 · 1 个精确实验 Pack",
    },
    {
        eyebrow: "BATCH 29 · DIRECTED ROUTES",
        title: "全库跨语言转换",
        description: "在 15 种语言组成的显式活动矩阵中选择精确方向，查看语义风险、阻断项和受控执行状态；210 条路线、本地 Profile 与外部证据全部保持 NOT_RUN。",
        href: "/translation",
        icon: "code",
        accent: "cyan",
        meta: "15 种语言 · 210 条路线 · 本地通过 0 · 全部 NOT_RUN",
    },
    {
        eyebrow: "PROJECT SYNTHESIS · B46–B80",
        title: "多语言项目生成",
        description: "从审阅后的需求生成 8 种语言的可验证工程；全部 PostgreSQL 生产 Profile 支持多实体。",
        href: "/generation",
        icon: "spark",
        accent: "violet",
        meta: "8 种语言 · 多实体生产 Profile",
    },
    {
        eyebrow: "BATCH 31 · CHINADB SQL",
        title: "国产数据库 SQL 转换",
        description: "在 13 个国产数据库目标上做 typed SQL 预评估，并在显式兼容模式下生成本地目标 SQL；实库执行与认证保持 NOT_RUN。",
        href: "/migration/sql",
        icon: "database",
        accent: "amber",
        meta: "13 个兼容模式目标 · 外部证据 NOT_RUN",
    },
    {
        eyebrow: "GOVERNANCE · M29–M37",
        title: "迁移能力与验证",
        description: "检查迁移能力包、开发者工作流、外部控制面和严格门禁；结构就绪不自动升级为运行或认证结论。",
        href: "/migration",
        icon: "shield",
        accent: "green",
        meta: "Fail closed · External evidence NOT_RUN",
    },
]; } catch(e) {}
try { var attention = [
    ["转换路线独立验证", "15 语言 / 210 路线已接入；本地通过 Profile 为 0，客户仓库与独立验证全部未运行", "NOT_RUN"],
    ["Spring 外部 Runner 证据", "实验 Pack 已闭环，真实客户仓库、holdout 与独立执行未运行", "NOT_RUN"],
    ["多语言生成外部工具链", "浏览器只准备受控交接，不执行生成", "NOT_RUN"],
    ["ChinaDB 实库执行", "13 个目标仅提供有限兼容模式发射，并非厂商原生适配；实库执行与认证仍未运行", "NOT_RUN"],
]; } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
  },
  lifetimes: {
    attached() {
    },
    detached() {
    },
  },
  methods: {
  },
});
