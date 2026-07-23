"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Icon, type IconName } from "../components/Icon";
import { StatusChip } from "../components/StatusChip";
import { migrationCapabilities as fallbackCapabilities } from "../lib/catalog";
import type { CapabilityResponse, MigrationCapability } from "../lib/contracts";

type StudioView = "routes" | "marketplace";
type Draft = {
  id: string;
  name: string;
  source: string;
  target: string;
  scope: string;
  capabilityId: string | null;
  createdAt: string;
};

const DRAFT_STORAGE_KEY = "elmos.migration-assessment-drafts.v1";

function isStoredDraft(value: unknown): value is Draft {
  if (!value || typeof value !== "object") return false;
  const draft = value as Partial<Draft>;
  return typeof draft.id === "string"
    && typeof draft.name === "string"
    && typeof draft.source === "string"
    && typeof draft.target === "string"
    && typeof draft.scope === "string"
    && (draft.capabilityId === null || typeof draft.capabilityId === "string")
    && typeof draft.createdAt === "string";
}

const extensions: Array<{
  name: string;
  publisher: string;
  type: string;
  description: string;
  version: string;
  compatibility: string;
  status: "DRAFT" | "REVIEW" | "EXPERIMENTAL";
  icon: IconName;
}> = [
  { name: "Language Adapter SDK", publisher: "ELMOS First-party", type: "语言适配器", description: "对接解析器、PSP、类型语义和发射器，并保留未知语义。", version: "0.1.0", compatibility: "Platform 0.1", status: "EXPERIMENTAL", icon: "code" },
  { name: "Evidence Collector SDK", publisher: "ELMOS First-party", type: "证据采集器", description: "采集原生证据并与归一化记录分离，保留首个失败。", version: "0.1.0", compatibility: "Platform 0.1", status: "REVIEW", icon: "file" },
  { name: "Runner Job SDK", publisher: "ELMOS First-party", type: "Runner 扩展", description: "声明最小能力、网络和文件权限；默认拒绝宿主访问。", version: "0.1.0", compatibility: "Platform 0.1", status: "DRAFT", icon: "server" },
  { name: "Policy Extension SDK", publisher: "ELMOS First-party", type: "策略扩展", description: "扩展类型化策略判断，不能绕过核心授权或自行批准。", version: "0.1.0", compatibility: "Platform 0.1", status: "DRAFT", icon: "shield" },
];

export function MigrationStudio() {
  const [view, setView] = useState<StudioView>("routes");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [selected, setSelected] = useState("M36");
  const [capabilities, setCapabilities] = useState(fallbackCapabilities);
  const [source, setSource] = useState<CapabilityResponse<MigrationCapability>["source"]>("REPOSITORY_CONTRACT");
  const [note, setNote] = useState("正在读取能力契约…");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [draftsReady, setDraftsReady] = useState(false);
  const [draftCapability, setDraftCapability] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");
  const dialogReturnFocus = useRef<HTMLElement | null>(null);
  const dialogPanel = useRef<HTMLElement>(null);
  const draftNameInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch("/api/capabilities/migration")
      .then((response) => response.ok ? response.json() as Promise<CapabilityResponse<MigrationCapability>> : Promise.reject())
      .then((payload) => {
        setCapabilities(payload.capabilities);
        setSource(payload.source);
        setNote(payload.note ?? "能力契约已载入。");
      })
      .catch(() => setNote("能力 API 不可用；继续显示仓库契约，外部执行保持 NOT_RUN。"));
  }, []);

  useEffect(() => {
    try {
      const stored = JSON.parse(window.localStorage.getItem(DRAFT_STORAGE_KEY) ?? "[]") as unknown;
      if (Array.isArray(stored)) setDrafts(stored.filter(isStoredDraft).slice(0, 50));
    } catch {
      try { window.localStorage.removeItem(DRAFT_STORAGE_KEY); } catch { /* Storage may be disabled by policy. */ }
      setFeedback("本地草稿存储不可用；迁移能力目录仍可浏览，但刷新后不会恢复草稿。");
    } finally {
      setDraftsReady(true);
    }
  }, []);

  useEffect(() => {
    if (!draftsReady) return;
    try {
      window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(drafts));
    } catch {
      setFeedback("浏览器未允许保存本地草稿；请勿依赖当前草稿跨刷新恢复。");
    }
  }, [drafts, draftsReady]);

  useEffect(() => {
    if (!dialogOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => draftNameInput.current?.focus());
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") closeDialog();
      if (event.key !== "Tab") return;
      const focusable = Array.from(dialogPanel.current?.querySelectorAll<HTMLElement>("button, input, select, [href], [tabindex]:not([tabindex='-1'])") ?? []).filter((element) => !element.hasAttribute("disabled"));
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
    window.addEventListener("keydown", handleEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleEscape);
    };
  }, [dialogOpen]);

  useEffect(() => {
    if (!feedback) return;
    const timer = window.setTimeout(() => setFeedback(""), 4200);
    return () => window.clearTimeout(timer);
  }, [feedback]);

  const visibleCapabilities = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("zh-CN");
    return capabilities.filter((capability) => {
      const matchesText = !needle || `${capability.id} ${capability.title} ${capability.domain}`.toLocaleLowerCase("zh-CN").includes(needle);
      const matchesStatus = statusFilter === "ALL" || capability.status === statusFilter;
      return matchesText && matchesStatus;
    });
  }, [capabilities, query, statusFilter]);

  const selectedCapability = capabilities.find((capability) => capability.id === selected) ?? capabilities[0];
  const filtersActive = query.trim().length > 0 || statusFilter !== "ALL";

  function openDialog(capabilityId?: string) {
    dialogReturnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setDraftCapability(capabilityId ?? null);
    setDialogOpen(true);
  }

  function closeDialog() {
    setDialogOpen(false);
    requestAnimationFrame(() => dialogReturnFocus.current?.focus());
  }

  function clearFilters() {
    setQuery("");
    setStatusFilter("ALL");
  }

  function createDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "").trim() || "未命名评估";
    setDrafts((current) => [{
      id: crypto.randomUUID(),
      name,
      source: String(form.get("source") ?? "Unknown"),
      target: String(form.get("target") ?? "Unknown"),
      scope: String(form.get("scope") ?? "单仓评估"),
      capabilityId: draftCapability,
      createdAt: new Date().toISOString(),
    }, ...current]);
    setFeedback(`“${name}”已持久保存到此浏览器，不会触发外部执行。`);
    closeDialog();
    event.currentTarget.reset();
  }

  function removeDraft(id: string) {
    const removed = drafts.find((draft) => draft.id === id);
    setDrafts((current) => current.filter((draft) => draft.id !== id));
    if (removed) setFeedback(`“${removed.name}”已从此浏览器删除。`);
  }

  return (
    <div className="page-stack studio-page">
      <section className="page-header">
        <div>
          <span className="overline">MIGRATION PLATFORM · M29–M37</span>
          <h1>迁移工坊</h1>
          <p>把路线选择、开发者预览、证据门禁与扩展生态放在同一个清晰工作流里。</p>
        </div>
        <button className="button button-primary" onClick={() => openDialog()}><Icon name="plus" size={17} />新建评估</button>
      </section>

      <section className="metric-grid metric-grid-four" aria-label="迁移能力摘要">
        <article className="metric-card"><span>能力包</span><strong>{capabilities.length}</strong><small>M29–M37 精确分域</small></article>
        <article className="metric-card"><span>可调用 Skills</span><strong>{capabilities.reduce((sum, item) => sum + item.skillCount, 0)}</strong><small>仓库内结构化能力</small></article>
        <article className="metric-card"><span>认证上限</span><strong className="metric-word">Gate ready</strong><small>控制台不签发认证</small></article>
        <article className="metric-card"><span>外部执行</span><strong className="metric-word warning-text">NOT_RUN</strong><small>未连接客户环境</small></article>
      </section>

      <section className="source-notice" role="status">
        <Icon name={source === "LIVE_API" ? "check" : "clock"} size={16} />
        <span>{note}</span>
        <StatusChip status={source} compact />
      </section>

      <div className="segmented-tabs" role="tablist" aria-label="迁移工坊视图">
        <button role="tab" aria-selected={view === "routes"} className={view === "routes" ? "active" : ""} onClick={() => setView("routes")}><Icon name="route" size={17} />迁移路线</button>
        <button role="tab" aria-selected={view === "marketplace"} className={view === "marketplace" ? "active" : ""} onClick={() => setView("marketplace")}><Icon name="box" size={17} />扩展 Marketplace</button>
        {drafts.length > 0 && <span className="draft-count">{drafts.length} 个本地草稿</span>}
      </div>

      {view === "routes" ? (
        <section className="studio-layout" aria-label="迁移路线目录">
          <div className="catalog-panel">
            <div className="catalog-toolbar">
              <label className="search-field"><Icon name="search" size={17} /><span className="sr-only">搜索能力</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索能力、Batch 或领域" /></label>
              <label className="select-field"><Icon name="filter" size={16} /><span className="sr-only">状态筛选</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="ALL">全部状态</option><option value="READY">契约就绪</option><option value="EXPERIMENTAL">实验性</option></select></label>
            </div>
            <div className="catalog-summary-bar" aria-live="polite"><span>显示 <strong>{visibleCapabilities.length}</strong> / {capabilities.length} 个能力</span>{filtersActive && <button type="button" onClick={clearFilters}>清除筛选</button>}</div>
            {drafts.length > 0 && <div className="draft-list">{drafts.map((draft) => <div className="draft-row" key={draft.id}><span className="capability-icon accent-cyan"><Icon name="spark" size={18} /></span><div><strong>{draft.name}</strong><small>{draft.source} → {draft.target} · {draft.scope}{draft.capabilityId ? ` · ${draft.capabilityId}` : ""}</small></div><StatusChip status="DRAFT" compact /><button type="button" className="icon-button" aria-label={`删除草稿 ${draft.name}`} onClick={() => removeDraft(draft.id)}><Icon name="close" size={13} /></button></div>)}</div>}
            <div className="capability-list">
              {visibleCapabilities.map((capability) => (
                <button className={`capability-row ${selected === capability.id ? "selected" : ""}`} key={capability.id} onClick={() => setSelected(capability.id)} aria-pressed={selected === capability.id}>
                  <span className={`capability-icon accent-${capability.accent}`}><Icon name={capability.icon} size={20} /></span>
                  <span className="capability-copy"><span><b>{capability.id}</b>{capability.title}</span><small>{capability.domain} · {capability.skillCount} Skills</small></span>
                  <StatusChip status={capability.status} compact />
                  <Icon name="chevron" size={16} />
                </button>
              ))}
              {visibleCapabilities.length === 0 && <div className="empty-state"><Icon name="search" /><strong>没有匹配的能力</strong><span>调整关键词或恢复全部状态。</span><button type="button" className="button button-secondary" onClick={clearFilters}>清除筛选</button></div>}
            </div>
          </div>

          {selectedCapability && <aside className="detail-panel">
            <div className={`detail-hero accent-${selectedCapability.accent}`}>
              <span className="capability-icon"><Icon name={selectedCapability.icon} size={22} /></span>
              <StatusChip status={selectedCapability.status} compact />
            </div>
            <span className="overline">{selectedCapability.id} · {selectedCapability.domain}</span>
            <h2>{selectedCapability.title}</h2>
            <p>{selectedCapability.description}</p>
            <dl className="detail-facts">
              <div><dt>Skills</dt><dd>{selectedCapability.skillCount}</dd></div>
              <div><dt>Schemas</dt><dd>{selectedCapability.schemaCount}</dd></div>
              <div><dt>外部证据</dt><dd className="warning-text">NOT_RUN</dd></div>
            </dl>
            <div className="gate-block"><span>唯一认证门禁</span><code>{selectedCapability.gateCommand}</code></div>
            {selectedCapability.id === "M36" && <div className="feature-callout"><Icon name="spark" size={17} /><div><strong>开发者预览已接入</strong><small>支持来源—目标导航、受保护区域和无写入预览；真实 IDE Host 证据仍未运行。</small></div></div>}
            <div className="detail-actions"><button className="button button-secondary" onClick={() => openDialog(selectedCapability.id)}>以此创建草稿</button><a className="icon-button bordered" href={`/api/capabilities/migration`} target="_blank" rel="noreferrer" aria-label="打开能力 API"><Icon name="external" size={17} /></a></div>
          </aside>}
        </section>
      ) : (
        <Marketplace extensions={extensions} query={query} setQuery={setQuery} />
      )}

      <div className={`feedback-toast ${feedback ? "visible" : ""}`} role="status" aria-live="polite" aria-atomic="true"><span><Icon name="check" size={17} /></span>{feedback}</div>

      {dialogOpen && (
        <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeDialog(); }}>
          <section ref={dialogPanel} className="modal-card" role="dialog" aria-modal="true" aria-labelledby="new-assessment-title" aria-describedby="new-assessment-description">
            <div className="modal-heading"><div><span className="overline">LOCAL DRAFT</span><h2 id="new-assessment-title">新建迁移评估</h2></div><button className="icon-button" aria-label="关闭" onClick={closeDialog}><Icon name="close" /></button></div>
            <p className="modal-intro" id="new-assessment-description">草稿只保存在当前浏览器，不会上传仓库、运行客户代码或触发认证。按 ESC 可随时关闭。</p>
            <form onSubmit={createDraft} className="form-stack">
              <label><span>评估名称</span><input ref={draftNameInput} name="name" required autoComplete="off" placeholder="例如：订单服务现代化" /></label>
              <div className="form-grid"><label><span>源技术栈</span><select name="source" defaultValue="Java 8 / Spring 4"><option>Java 8 / Spring 4</option><option>C# / .NET Framework 4.8</option><option>Python 3.8 / Django 2.2</option><option>AngularJS 1.8</option></select></label><label><span>目标技术栈</span><select name="target" defaultValue="Java 21 / Spring Boot 3"><option>Java 21 / Spring Boot 3</option><option>.NET 10</option><option>Python 3.14 / Django 5</option><option>React 19 / Next.js 16</option></select></label></div>
              <label><span>工作范围</span><select name="scope" defaultValue="单仓评估"><option>单仓评估</option><option>多仓依赖评估</option><option>组合级发现</option></select></label>
              <div className="form-note"><Icon name="lock" size={16} />凭证、生产数据与客户代码不会写入此草稿。{draftCapability ? ` 当前关联能力：${draftCapability}。` : ""}</div>
              <div className="modal-actions"><button type="button" className="button button-secondary" onClick={closeDialog}>取消</button><button className="button button-primary" type="submit">保存本地草稿</button></div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

function Marketplace({ extensions: items, query, setQuery }: { extensions: typeof extensions; query: string; setQuery: (value: string) => void }) {
  const needle = query.toLocaleLowerCase("zh-CN");
  const visible = items.filter((item) => !needle || `${item.name} ${item.type} ${item.description}`.toLocaleLowerCase("zh-CN").includes(needle));
  return (
    <section className="marketplace-layout">
      <div className="market-main">
        <div className="market-hero">
          <div><span className="overline">BATCH 37 · SAFE EXTENSIBILITY</span><h2>扩展核心之外的能力，<br/>不放宽核心边界。</h2><p>每个扩展都绑定精确 ABI、Publisher、签名、SBOM、Sandbox 与撤销策略。</p></div>
          <div className="market-symbol"><Icon name="box" size={34} /><span>36</span><small>Marketplace Skills</small></div>
        </div>
        <div className="market-toolbar"><label className="search-field"><Icon name="search" size={17} /><span className="sr-only">搜索扩展</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索扩展类型或能力" /></label><StatusChip status="NOT_RUN" /></div>
        <div className="extension-grid">
          {visible.map((extension) => <article className="extension-card" key={extension.name}>
            <div className="extension-top"><span className="extension-icon"><Icon name={extension.icon} size={21} /></span><StatusChip status={extension.status} compact /></div>
            <span className="overline">{extension.type}</span><h3>{extension.name}</h3><p>{extension.description}</p>
            <div className="extension-meta"><span><b>{extension.version}</b> 版本</span><span>{extension.compatibility}</span></div>
            <div className="publisher"><span className="mini-avatar">EL</span><span>{extension.publisher}<small>模板条目 · 尚未发布</small></span></div>
          </article>)}
          {visible.length === 0 && <div className="market-empty"><Icon name="search" size={22} /><strong>没有匹配的扩展</strong><span>请尝试名称、类型或能力关键词。</span><button className="button button-secondary" type="button" onClick={() => setQuery("")}>清除搜索</button></div>}
        </div>
      </div>
      <aside className="market-side">
        <div className="surface-card compact-card"><span className="overline">CERTIFICATION PATH</span><h3>发布前的 5 个门槛</h3><ol className="cert-path"><li className="done"><i>1</i><span><b>Manifest 与 ABI</b><small>类型化契约已定义</small></span></li><li className="done"><i>2</i><span><b>Sandbox 策略</b><small>默认拒绝权限</small></span></li><li><i>3</i><span><b>签名与供应链</b><small>外部信任根未运行</small></span></li><li><i>4</i><span><b>独立安全审核</b><small>待授权执行</small></span></li><li><i>5</i><span><b>Marketplace Gate</b><small>只有 Gate 能裁定</small></span></li></ol></div>
        <div className="surface-card safety-card"><Icon name="shield" size={20} /><div><strong>商业状态不能绕过安全认证</strong><p>付费、私有目录或紧急发布都不能跳过签名、兼容性、撤销和隔离检查。</p></div></div>
      </aside>
    </section>
  );
}
