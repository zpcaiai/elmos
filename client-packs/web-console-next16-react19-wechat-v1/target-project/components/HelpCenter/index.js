// Top-level helpers and constants
try { var businessLines = [
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
    {
        href: "/migration/sql",
        zh: "国产数据库 SQL 转换",
        en: "ChinaDB SQL conversion",
        zhDescription: "在显式兼容模式下生成本地目标 SQL；实库执行与认证保持 NOT_RUN。",
        enDescription: "Emit local target SQL under an explicit compatibility mode; live execution and certification stay NOT_RUN.",
    },
]; } catch(e) {}
try { var deliverySteps = [
    ["1", "拉取精确提交", "Clone exact commit"],
    ["2", "只修改已批准路径", "Change approved paths only"],
    ["3", "本地提交并回读 HEAD", "Commit and re-read HEAD"],
    ["4", "非强制推送并校验远端 SHA", "Non-force push and verify remote SHA"],
    ["5", "幂等创建 PR", "Create an idempotent PR"],
]; } catch(e) {}
try { var readiness = [
    ["登录、租户与权限", "本地实现并有测试", "外部 IdP 全目录同步 NOT_RUN", "Identity, tenant, and permissions", "Locally implemented and tested", "External IdP directory sync NOT_RUN"],
    ["Git 仓库交付", "真实本地 Git 仓库通过", "GitHub / Gitee 现场执行 NOT_RUN", "Git delivery", "Real local Git fixture passed", "Live GitHub / Gitee execution NOT_RUN"],
    ["四条业务线持久队列", "租约、TTL、容量与恢复通过", "多副本共享卷故障演练 NOT_RUN", "Durable queues", "Lease, TTL, capacity, and recovery passed", "Multi-replica shared-volume drill NOT_RUN"],
    ["管理端与审计", "租户范围日志、告警、用量、配置可见", "生产通知与部署证据 NOT_RUN", "Admin and audit", "Tenant-scoped logs, alerts, usage, and config visible", "Production notification and deployment evidence NOT_RUN"],
    ["客户端质量", "构建、浏览器、键盘与自动可访问性检查", "独立读屏、视觉基线审批与代表旅程 NOT_RUN", "Client quality", "Build, browser, keyboard, and automated accessibility checks", "Independent AT, visual approval, and representative journeys NOT_RUN"],
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
