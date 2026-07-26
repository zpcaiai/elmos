"use client";

import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import { Icon } from "../components/Icon";
import { StatusChip } from "../components/StatusChip";
import { directedLanguageRoutes, translationLanguages } from "../lib/businessLines";
import type {
  DirectedLanguageRoute,
  TranslationCapabilityResponse,
  TranslationLanguageId,
  TranslationRepositoryPlan,
} from "../lib/contracts";

type Handoff = {
  schemaVersion: "1.1.0";
  repositoryRef: string;
  routeId: string;
  scope: "single-module" | "repository" | "portfolio";
  inventorySnapshotSha256?: string;
  workUnitCount?: number;
  requestedStatus: "EXPERIMENTAL_EVALUATION";
  executionStatus: "NOT_RUN";
  certificationStatus: "NOT_CERTIFIED";
  blockers: string[];
  createdAt: string;
};

const STORAGE_KEY = "elmos.translation-handoff.v3";
const routeIds = new Set(directedLanguageRoutes.map((route) => route.id));
const languageIds = new Set<TranslationLanguageId>(translationLanguages.map((language) => language.id));

function isSafeRepositoryRef(value: string): boolean {
  if (
    value.length < 3
    || value.length > 180
    || /[\s\\?#]/.test(value)
    || value.startsWith("/")
    || value.startsWith("~")
  ) return false;
  if (/^local:[a-z0-9][a-z0-9._/-]{2,170}$/i.test(value)) return true;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:"
      && !parsed.username
      && !parsed.password
      && Boolean(parsed.hostname);
  } catch {
    return false;
  }
}

function isStoredHandoff(value: unknown): value is Handoff {
  if (!value || typeof value !== "object") return false;
  const stored = value as Partial<Handoff>;
  return stored.schemaVersion === "1.1.0"
    && typeof stored.repositoryRef === "string"
    && isSafeRepositoryRef(stored.repositoryRef)
    && typeof stored.routeId === "string"
    && routeIds.has(stored.routeId)
    && ["single-module", "repository", "portfolio"].includes(stored.scope ?? "")
    && stored.requestedStatus === "EXPERIMENTAL_EVALUATION"
    && stored.executionStatus === "NOT_RUN"
    && stored.certificationStatus === "NOT_CERTIFIED"
    && (
      stored.inventorySnapshotSha256 === undefined
      || /^[0-9a-f]{64}$/.test(stored.inventorySnapshotSha256)
    )
    && (
      stored.workUnitCount === undefined
      || Number.isInteger(stored.workUnitCount) && stored.workUnitCount >= 1 && stored.workUnitCount <= 5_000
    )
    && (
      stored.scope !== "repository"
      || stored.inventorySnapshotSha256 !== undefined && stored.workUnitCount !== undefined
    )
    && Array.isArray(stored.blockers)
    && stored.blockers.length <= 20
    && stored.blockers.every((blocker) => typeof blocker === "string" && blocker.length <= 300)
    && typeof stored.createdAt === "string"
    && !Number.isNaN(Date.parse(stored.createdAt));
}

function isRepositoryPlan(value: unknown): value is TranslationRepositoryPlan {
  if (!value || typeof value !== "object") return false;
  const plan = value as Partial<TranslationRepositoryPlan>;
  const counts = plan.language_counts;
  return plan.schema_version === "1.0.0"
    && plan.kind === "elmos.repository-route-plan"
    && plan.status === "PLANNED"
    && typeof plan.repository_ref === "string"
    && isSafeRepositoryRef(plan.repository_ref)
    && typeof plan.snapshot_sha256 === "string"
    && /^[0-9a-f]{64}$/.test(plan.snapshot_sha256)
    && plan.snapshot_consistency === "STABLE_READ_ONLY_SCAN"
    && typeof plan.route_id === "string"
    && routeIds.has(plan.route_id)
    && typeof plan.source_language === "string"
    && languageIds.has(plan.source_language as TranslationLanguageId)
    && typeof plan.target_language === "string"
    && languageIds.has(plan.target_language as TranslationLanguageId)
    && plan.source_language !== plan.target_language
    && Number.isInteger(plan.file_count) && (plan.file_count ?? -1) >= 1 && (plan.file_count ?? 0) <= 5_000
    && Number.isInteger(plan.source_file_count) && (plan.source_file_count ?? -1) >= 1
    && (plan.source_file_count ?? 5_001) <= (plan.file_count ?? 0)
    && Number.isInteger(plan.source_bytes) && (plan.source_bytes ?? -1) >= 1 && (plan.source_bytes ?? 0) <= 64 * 1024 * 1024
    && Boolean(counts)
    && [...languageIds].every((language) => Number.isInteger(counts?.[language]) && (counts?.[language] ?? -1) >= 0)
    && Number.isInteger(plan.ignored_symlink_count) && (plan.ignored_symlink_count ?? -1) >= 0
    && Array.isArray(plan.work_units)
    && plan.work_units.length === plan.source_file_count
    && plan.work_units.every((unit) =>
      Boolean(unit)
      && typeof unit.id === "string"
      && unit.route_id === plan.route_id
      && typeof unit.source_path === "string"
      && unit.source_path.length <= 500
      && !unit.source_path.startsWith("/")
      && !unit.source_path.split("/").includes("..")
      && /^[0-9a-f]{64}$/.test(unit.source_sha256)
      && Number.isInteger(unit.source_bytes) && unit.source_bytes >= 0 && unit.source_bytes <= 2 * 1024 * 1024
      && unit.status === "DISCOVERY_REQUIRED"
      && unit.execution_status === "NOT_RUN"
      && unit.declared_profile === "typed-pure-function-v1"
      && Array.isArray(unit.unsupported_until_discovered)
      && unit.unsupported_until_discovered.length <= 20
    )
    && plan.execution_status === "NOT_RUN"
    && plan.external_verification_status === "NOT_RUN"
    && plan.certification_status === "NOT_CERTIFIED"
    && Array.isArray(plan.limitations)
    && plan.limitations.length > 0
    && plan.limitations.length <= 20
    && plan.limitations.every((item) => typeof item === "string" && item.length <= 500);
}

export function TranslationStudio() {
  const [sourceLanguage, setSourceLanguage] = useState<TranslationLanguageId>("java");
  const [targetLanguage, setTargetLanguage] = useState<TranslationLanguageId>("python");
  const [repositoryRef, setRepositoryRef] = useState("local:customer-repository");
  const [scope, setScope] = useState<Handoff["scope"]>("repository");
  const [handoff, setHandoff] = useState<Handoff | null>(null);
  const [repositoryPlan, setRepositoryPlan] = useState<TranslationRepositoryPlan | null>(null);
  const [capability, setCapability] = useState<TranslationCapabilityResponse | null>(null);
  const [capabilityError, setCapabilityError] = useState("");
  const [feedback, setFeedback] = useState("");

  const languages = capability?.languages ?? translationLanguages;
  const routes = capability?.routes ?? directedLanguageRoutes;
  const selectedRoute = routes.find((route) =>
    route.source === sourceLanguage && route.target === targetLanguage) ?? routes[0];

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/capabilities/translation", { cache: "no-store", signal: controller.signal })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("capability unavailable")))
      .then((payload: TranslationCapabilityResponse) => {
        setCapability(payload);
        setCapabilityError("");
      })
      .catch(() => {
        setCapability(null);
        setCapabilityError("路线能力契约暂时不可读取；页面中的回退数据不作为最新执行证据。");
      });
    try {
      const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "null") as Handoff | null;
      if (isStoredHandoff(stored)) setHandoff(stored);
    } catch {
      try { window.localStorage.removeItem(STORAGE_KEY); } catch { /* Storage may be denied. */ }
    }
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!feedback) return;
    const timer = window.setTimeout(() => setFeedback(""), 4200);
    return () => window.clearTimeout(timer);
  }, [feedback]);

  const sourceProfile = languages.find((language) => language.id === sourceLanguage);
  const targetProfile = languages.find((language) => language.id === targetLanguage);
  const routeCommand = `uv --directory engines/polyglot-route-engine run --locked elmos-polyglot-route --source <SOURCE_FILE> --source-language ${sourceLanguage} --target-language ${targetLanguage} --function <FUNCTION_NAME> --cases <CASES_JSON> --output <NEW_OUTPUT_DIR>`;
  const inventoryCommand = `uv --directory engines/polyglot-route-engine run --locked elmos-polyglot-route inventory --repository <READ_ONLY_REPOSITORY> --repository-ref ${repositoryRef.trim() || "<SAFE_REPOSITORY_REF>"} --source-language ${sourceLanguage} --target-language ${targetLanguage} --output repository-route-plan.json`;
  const validationCommands = selectedRoute ? [
    `python3 scripts/batch29/validate_route.py routes/${selectedRoute.id}`,
    `python3 scripts/batch29/run_route_gate.py routes/${selectedRoute.id}`,
  ] : [];
  const routeCounts = useMemo(() => ({
    total: routes.length,
    locallyPassed: routes.filter((route) => route.localExecution === "PASSED").length,
    externallyPending: routes.filter((route) => route.externalVerification === "NOT_RUN").length,
  }), [routes]);

  function chooseSource(id: TranslationLanguageId) {
    setSourceLanguage(id);
    if (id === targetLanguage) {
      const replacement = languages.find((language) => language.id !== id);
      if (replacement) setTargetLanguage(replacement.id);
    }
    setHandoff(null);
    setRepositoryPlan(null);
  }

  function chooseTarget(id: TranslationLanguageId) {
    if (id === sourceLanguage) return;
    setTargetLanguage(id);
    setHandoff(null);
    setRepositoryPlan(null);
  }

  function saveHandoff() {
    if (!selectedRoute || !isSafeRepositoryRef(repositoryRef.trim())) {
      setFeedback("仓库引用仅接受不含凭证、查询参数或本机路径的 local: 标识或 HTTPS 地址。");
      return;
    }
    if (
      scope === "repository"
      && (!repositoryPlan
        || repositoryPlan.repository_ref !== repositoryRef.trim()
        || repositoryPlan.route_id !== selectedRoute.id
        || repositoryPlan.source_language !== sourceLanguage
        || repositoryPlan.target_language !== targetLanguage)
    ) {
      setFeedback("整个仓库必须先导入与当前仓库引用、源语言和目标语言完全匹配的只读清单 JSON。");
      return;
    }
    const next: Handoff = {
      schemaVersion: "1.1.0",
      repositoryRef: repositoryRef.trim(),
      routeId: selectedRoute.id,
      scope,
      inventorySnapshotSha256: scope === "repository" ? repositoryPlan?.snapshot_sha256 : undefined,
      workUnitCount: scope === "repository" ? repositoryPlan?.work_units.length : undefined,
      requestedStatus: "EXPERIMENTAL_EVALUATION",
      executionStatus: "NOT_RUN",
      certificationStatus: "NOT_CERTIFIED",
      blockers: selectedRoute.blockers,
      createdAt: new Date().toISOString(),
    };
    setHandoff(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      setFeedback(scope === "repository"
        ? `整库路线交接已绑定 ${repositoryPlan?.work_units.length ?? 0} 个工作单元；转换执行仍为 NOT_RUN。`
        : "定向路线交接已保存；未执行转换。");
    } catch {
      setFeedback("浏览器未允许保存；当前交接仍可导出。");
    }
  }

  async function importInventory(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) {
      setFeedback("仓库清单超过 8 MB 浏览器导入上限，请缩小评估范围。");
      return;
    }
    try {
      const value = JSON.parse(await file.text()) as unknown;
      if (!isRepositoryPlan(value)) throw new Error("REPOSITORY_PLAN_INVALID");
      if (
        value.repository_ref !== repositoryRef.trim()
        || value.route_id !== selectedRoute?.id
        || value.source_language !== sourceLanguage
        || value.target_language !== targetLanguage
      ) {
        throw new Error("REPOSITORY_PLAN_CONTEXT_MISMATCH");
      }
      setRepositoryPlan(value);
      setHandoff(null);
      setFeedback(`已验证只读清单：${value.source_file_count} 个源文件拆为 ${value.work_units.length} 个待发现工作单元。`);
    } catch (error) {
      setRepositoryPlan(null);
      setFeedback(`仓库清单导入失败：${error instanceof Error ? error.message : "REPOSITORY_PLAN_INVALID"}`);
    }
  }

  async function copyText(value: string, message: string) {
    try {
      await navigator.clipboard.writeText(value);
      setFeedback(message);
    } catch {
      setFeedback("浏览器未允许访问剪贴板，请手动复制。");
    }
  }

  function exportHandoff() {
    if (!handoff || !selectedRoute) {
      setFeedback("请先保存当前路线交接。");
      return;
    }
    if (handoff.scope === "repository" && !repositoryPlan) {
      setFeedback("为避免持久化客户文件路径，整库清单不会写入浏览器存储；刷新后请重新导入清单再导出。");
      return;
    }
    const payload = {
      ...handoff,
      route: selectedRoute,
      sourceProfile,
      targetProfile,
      commands: [routeCommand, ...validationCommands],
      repositoryPlan: handoff.scope === "repository" ? repositoryPlan : undefined,
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${handoff.routeId}-handoff.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    setFeedback("路线交接已导出，所有执行与认证状态保持 NOT_RUN / NOT_CERTIFIED。");
  }

  return (
    <div className="page-stack business-page">
      <section className="page-header business-hero">
        <div>
          <span className="overline">DIRECTED LANGUAGE ROUTES · BATCH 29</span>
          <h1>全库跨语言转换</h1>
          <p>Java、C#、Python 与 TypeScript 形成 12 条方向独立的转换路线；每条路线分别绑定语义风险、精确工具链、语料和认证证据。</p>
        </div>
        <div className="header-actions"><StatusChip status="EXPERIMENTAL" /><StatusChip status="NOT_CERTIFIED" /></div>
      </section>

      <section className="metric-grid metric-grid-four" aria-label="跨语言路线摘要">
        <article className="metric-card"><span>语言引擎</span><strong>{languages.length}</strong><small>精确版本、相互独立</small></article>
        <article className="metric-card"><span>有向路线</span><strong>{routeCounts.total}</strong><small>反向路线不复用结论</small></article>
        <article className="metric-card"><span>本地实验 Profile</span><strong>{routeCounts.locallyPassed}</strong><small>精确工具链 + 三类语料</small></article>
        <article className="metric-card"><span>独立验证待办</span><strong className="warning-text">{routeCounts.externallyPending}</strong><small>外部证据 NOT_RUN</small></article>
      </section>

      <section className="source-notice" role={capabilityError ? "alert" : "status"}>
        <Icon name="route" size={16} />
        <span>{capabilityError || capability?.note || "正在读取 12 个定向 Route Pack。"}</span>
        <StatusChip status={capabilityError ? "BLOCKED" : "REPOSITORY_CONTRACT"} compact />
      </section>

      <div className="translation-layout">
        <section className="surface-card route-picker" aria-labelledby="route-picker-title">
          <div className="business-section-heading"><div><span className="overline">DIRECTION MATTERS</span><h2 id="route-picker-title">选择源语言与目标语言</h2></div><span className="route-direction">{sourceProfile?.label} <Icon name="arrow" size={15} /> {targetProfile?.label}</span></div>
          <div className="language-pickers">
            <fieldset><legend>1 · 源语言</legend><div>{languages.map((language) => <button type="button" className={sourceLanguage === language.id ? "selected" : ""} key={language.id} onClick={() => chooseSource(language.id)} aria-pressed={sourceLanguage === language.id}><strong>{language.label}</strong><small>{language.compiler}</small></button>)}</div></fieldset>
            <fieldset><legend>2 · 目标语言</legend><div>{languages.map((language) => <button type="button" disabled={sourceLanguage === language.id} className={targetLanguage === language.id ? "selected" : ""} key={language.id} onClick={() => chooseTarget(language.id)} aria-pressed={targetLanguage === language.id}><strong>{language.label}</strong><small>{language.runtime}</small></button>)}</div></fieldset>
          </div>
          <div className="route-matrix" role="table" aria-label="12 条有向语言路线">
            <div className="route-matrix-row route-matrix-head" role="row"><span role="columnheader">源 \\ 目标</span>{languages.map((language) => <b role="columnheader" key={language.id}>{language.label}</b>)}</div>
            {languages.map((source) => (
              <div className="route-matrix-row" role="row" key={source.id}>
                <b role="rowheader">{source.label}</b>
                {languages.map((target) => (
                  <span className="route-matrix-cell" role="cell" key={target.id}>
                    {source.id === target.id
                      ? <span className="route-na">—</span>
                      : (
                        <button
                          type="button"
                          className={sourceLanguage === source.id && targetLanguage === target.id ? "selected" : ""}
                          onClick={() => {
                            setSourceLanguage(source.id);
                            setTargetLanguage(target.id);
                            setHandoff(null);
                            setRepositoryPlan(null);
                          }}
                          aria-label={`${source.label} 到 ${target.label}，本地实验 profile 已通过，独立验证未运行`}
                        >
                          <Icon name="check" size={12} />
                          <span>LOCAL PASS</span>
                        </button>
                      )}
                  </span>
                ))}
              </div>
            ))}
          </div>
        </section>

        {selectedRoute && <aside className="surface-card route-detail">
          <div className="business-section-heading"><div><span className="overline">{selectedRoute.id}</span><h2>{sourceProfile?.label} → {targetProfile?.label}</h2></div><StatusChip status={selectedRoute.status} compact /></div>
          <dl className="route-profile-facts"><div><dt>源工具链</dt><dd>{sourceProfile?.compiler}</dd></div><div><dt>目标运行时</dt><dd>{targetProfile?.runtime}</dd></div><div><dt>方向 Skill</dt><dd>${selectedRoute.skill}</dd></div></dl>
          <h3>必须显式处理的语义风险</h3>
          <ul className="hazard-list">{selectedRoute.hazards.map((hazard) => <li key={hazard}><Icon name="clock" size={13} />{hazard}</li>)}</ul>
          <h3>适用边界与剩余阻断</h3>
          <ul className="blocker-list compact">{selectedRoute.blockers.map((blocker) => <li key={blocker}><Icon name="lock" size={13} /><span>{blocker}</span></li>)}</ul>
        </aside>}
      </div>

      <section className="surface-card route-handoff" aria-labelledby="route-handoff-title">
        <div className="business-section-heading"><div><span className="overline">CONTROLLED HANDOFF</span><h2 id="route-handoff-title">准备定向路线，不伪造转换结果</h2></div><StatusChip status={handoff ? "REVIEW" : "DRAFT"} compact /></div>
        <div className="route-handoff-grid">
          <label><span>仓库引用</span><input value={repositoryRef} onChange={(event) => { setRepositoryRef(event.target.value); setHandoff(null); setRepositoryPlan(null); }} maxLength={180} aria-describedby="repository-ref-hint" /><small id="repository-ref-hint">只填写引用，不填写 Token、客户代码或本机绝对路径。</small></label>
          <label><span>评估范围</span><select value={scope} onChange={(event) => { setScope(event.target.value as Handoff["scope"]); setHandoff(null); if (event.target.value !== "repository") setRepositoryPlan(null); }}><option value="single-module">单个受限纯函数（可本地执行）</option><option value="repository">整个仓库（只读清单 + 工作单元）</option><option value="portfolio">多仓组合（发现与拆分计划）</option></select></label>
          {scope === "repository" && (
            <div className="repository-plan-import">
              <div><span>整库只读清单</span><StatusChip status={repositoryPlan ? "READY" : "NOT_RUN"} compact /></div>
              <label className="button button-secondary">
                <Icon name="file" size={15} />
                <span>导入仓库清单 JSON</span>
                <input type="file" accept="application/json,.json" onChange={(event) => void importInventory(event)} />
              </label>
              {repositoryPlan
                ? <dl><div><dt>Snapshot</dt><dd>{repositoryPlan.snapshot_sha256.slice(0, 12)}…</dd></div><div><dt>源文件</dt><dd>{repositoryPlan.source_file_count}</dd></div><div><dt>工作单元</dt><dd>{repositoryPlan.work_units.length}</dd></div><div><dt>执行</dt><dd>NOT_RUN</dd></div></dl>
                : <small>先在只读仓库目录执行清单命令；符号链接、构建目录、超大或变化中的文件会被忽略或失败关闭。</small>}
            </div>
          )}
          <div className="route-command-stack"><span>{scope === "repository" ? "只读清单生成命令" : "精确 Profile 执行模板"}</span><code>{scope === "repository" ? inventoryCommand : routeCommand}</code><small>{scope === "single-module" ? "命令只接受 typed-pure-function-v1；任何越界语义都会失败关闭。" : scope === "repository" ? "清单只读取受支持源文件并生成内容摘要与工作单元；不会执行客户代码或伪造转换成功。" : "多仓组合必须先逐仓生成清单并形成显式依赖图；当前不会把单函数证据扩张成组合成功。"}</small></div>
          <div className="route-handoff-actions"><button type="button" className="button button-primary" onClick={saveHandoff}><Icon name="file" size={15} />保存路线交接</button><button type="button" className="button button-secondary" onClick={exportHandoff}><Icon name="external" size={15} />导出 JSON</button><button type="button" className="button button-secondary" onClick={() => copyText([scope === "repository" ? inventoryCommand : routeCommand, ...validationCommands].join("\n"), "精确执行模板与保守门禁命令已复制。")}><Icon name="copy" size={15} />复制命令</button></div>
        </div>
      </section>

      <div className={`feedback-toast ${feedback ? "visible" : ""}`} role="status" aria-live="polite" aria-atomic="true"><span><Icon name="check" size={17} /></span>{feedback}</div>
    </div>
  );
}
