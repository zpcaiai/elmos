"use client";

import { useEffect, useMemo, useState } from "react";

import { Icon } from "../components/Icon";
import { useUiPreferences } from "../components/UiPreferencesProvider";
import { frtCatalog } from "../lib/frtCatalog.generated";
import styles from "./FrontendTransformationStudio.module.css";

type BatchId = (typeof frtCatalog.batches)[number]["id"];
type Stack = (typeof frtCatalog.technologyStacks)[number];
type FrtRunView = {
  runId: string;
  version: number;
  skillId: string;
  capabilityKey: string;
  contractDigest: string;
  sourceSnapshotDigest: string;
  action: string;
  state: "QUEUED" | "RUNNING" | "SUCCEEDED" | "BLOCKED" | "FAILED" | "CANCELLED";
  outcome: string;
  inputDigest: string;
  resultDigest: string;
  findings: Array<{ code: string; severity: string; message: string; blocking: boolean }>;
  evidence: Array<{ role: string; state: string; uri: string; digest: string }>;
  artifacts: Record<string, unknown>;
  certificateFragment: { eligibleForBatchGate: boolean; certification: string; evidenceRefs: string[] };
};
type FrtAuditView = { audit: Array<{ sequence: number; at: string; actor: string; event: string; state: string; version: number }> };

const deliveryStages = [
  { range: "G01–G04", title: "发现与类型化", detail: "仓库、框架、依赖、UI Interaction IR 与六类源适配器" },
  { range: "G05–G12", title: "规划与生成内核", detail: "差距决策、目标架构、生成、组件、状态、边界与平台能力" },
  { range: "G13–G17", title: "30 条有向路线", detail: "Vue 2、Vue 3、React、小程序、ArkUI 与 Flutter 两两转换" },
  { range: "G18–G20", title: "组合、证明与产品化", detail: "Pack 组合、Proof Obligation、Runtime、API、CLI 与 Console" },
  { range: "G21–G26", title: "产品与体验闭环", detail: "需求、业务、数据、管理端、可用性、无障碍与回归资格" },
  { range: "G27–G30", title: "生产就绪外部门禁", detail: "性能、韧性、安全与 SRE；需要授权的真实环境证据" },
] as const;

function lower(value: string): string {
  return value.toLocaleLowerCase("zh-CN");
}

const contractExamples: Readonly<Record<string, unknown>> = {
  invariants: [{ id: "tenant-scope", satisfied: true }],
  inventory: { workspaceKind: "monorepo", packages: [], routes: [], components: [] },
  target: { stack: "React", version: "19.2.7", language: "TypeScript" },
  targetProfile: { stack: "React", version: "19.2.7" },
  uiIr: { title: "Application", modules: ["app"] },
  astNodes: [{ id: "app", name: "App", kind: "component" }],
  components: [{ id: "app", props: [], events: [], slots: [], hooks: [] }],
  states: [{ id: "draft" }, { id: "ready" }],
  transitions: [{ id: "publish", from: "draft", to: "ready", sideEffect: false }],
  routes: [{ id: "home", path: "/" }],
  uiNodes: [{ id: "page-title", interactive: false }],
  requiredCapabilities: ["storage"],
  platformCapabilities: { web: ["storage"] },
  corpus: [{ id: "case-1", sourceDigest: `sha256:${"1".repeat(64)}`, expectedIrDigest: `sha256:${"2".repeat(64)}` }],
  packs: [{ id: "core", priority: 100, provides: ["ui"], requires: [] }],
  properties: [{ id: "state-valid", expression: "state != null", kind: "invariant", assumptions: [] }],
  resources: [{ id: "skill-registry", type: "registry", tenantBound: true, version: "1.0.0" }],
  requirements: [{ id: "REQ-1" }],
  capabilities: [{ id: "runs.read" }],
  roles: [{ id: "operator", permissions: ["runs.read"] }],
  operations: [{ id: "list-runs", roleId: "operator", permission: "runs.read", auditEvent: "runs.listed" }],
  workload: { concurrency: 10, durationSeconds: 60 },
  budgets: { p95LatencyMs: 500, maximumErrorRate: 0.01 },
  scenarios: [{ id: "dependency-loss", rollback: "restore service", blastRadius: "isolated-test-tenant" }],
  recoveryObjectives: { maximumRtoSeconds: 300, maximumRpoSeconds: 60 },
  assets: [{ id: "frontend-api", classification: "confidential" }],
  findings: [],
  slos: [{ serviceId: "frontend", target: 0.999 }],
  runbooks: [{ id: "frontend-errors", serviceId: "frontend" }],
};

function initialContractInput(skill: (typeof frtCatalog.skills)[number] | undefined): string {
  if (!skill) return "{}";
  const entries = skill.executionContract.inputContract.required
    .filter(key => key !== "files")
    .map(key => [key, contractExamples[key] ?? {}]);
  return JSON.stringify(Object.fromEntries(entries), null, 2);
}

function canonicalInput(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalInput).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalInput(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

export function FrontendTransformationStudio() {
  const preferences = useUiPreferences();
  const english = preferences.locale === "en";
  const t = (chinese: string, englishText: string) => english ? englishText : chinese;
  const [batch, setBatch] = useState<BatchId | "ALL">("ALL");
  const [query, setQuery] = useState("");
  const [source, setSource] = useState<Stack>("Vue 3");
  const [target, setTarget] = useState<Stack>("React");
  const [selectedSkillId, setSelectedSkillId] = useState("FRT-1305");
  const [workspaceId, setWorkspaceId] = useState("workspace-frt-console");
  const [projectId, setProjectId] = useState("project-frt-console");
  const [environmentId, setEnvironmentId] = useState("development");
  const [releaseId, setReleaseId] = useState("local-review");
  const [policyVersion, setPolicyVersion] = useState("frt-policy-1.0.0");
  const [risk, setRisk] = useState<"R0" | "R1" | "R2" | "R3" | "R4" | "R5">("R4");
  const [tenantId, setTenantId] = useState("");
  const [actorId, setActorId] = useState("");
  const [runnerToken, setRunnerToken] = useState("");
  const [sourceFiles, setSourceFiles] = useState<Record<string, string>>({});
  const [inputJson, setInputJson] = useState("{}");
  const [run, setRun] = useState<FrtRunView | null>(null);
  const [audit, setAudit] = useState<FrtAuditView["audit"]>([]);
  const [operationError, setOperationError] = useState("");
  const [busy, setBusy] = useState(false);

  const filteredSkills = useMemo(() => {
    const needle = lower(query.trim());
    return frtCatalog.skills.filter((skill) =>
      (batch === "ALL" || skill.batch === batch)
      && (!needle || lower(`${skill.id} ${skill.name} ${skill.title} ${skill.description}`).includes(needle)),
    );
  }, [batch, query]);
  const selectedRoute = frtCatalog.routes.find((route) => route.source === source && route.target === target);
  const selectedSkill = frtCatalog.skills.find((skill) => skill.id === selectedSkillId)
    ?? (selectedRoute ? frtCatalog.skills.find((skill) => skill.id === selectedRoute.skillId) : undefined)
    ?? filteredSkills[0];
  const visibleSkills = filteredSkills.slice(0, 72);
  const selectedInputContract = selectedSkill?.executionContract.inputContract;
  const acceptsFiles = Boolean(selectedInputContract
    && [...selectedInputContract.required, ...selectedInputContract.optional].includes("files"));

  useEffect(() => {
    setInputJson(initialContractInput(selectedSkill));
    setOperationError("");
  }, [selectedSkill?.id]);

  function requestHeaders(json = false): Record<string, string> {
    return {
      ...(json ? { "content-type": "application/json" } : {}),
      ...(tenantId && actorId && runnerToken ? {
        authorization: `Bearer ${runnerToken}`,
        "x-elmos-tenant": tenantId,
        "x-elmos-actor": actorId,
      } : {}),
    };
  }

  function scopedRunUrl(path: string): string {
    const query = new URLSearchParams({ workspaceId, projectId, environmentId, releaseId });
    return `${path}?${query.toString()}`;
  }

  async function sourceDigest(input: Readonly<Record<string, unknown>>): Promise<string> {
    const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonicalInput(input)));
    return `sha256:${Array.from(new Uint8Array(bytes), value => value.toString(16).padStart(2, "0")).join("")}`;
  }

  async function chooseRepositoryFiles(files: FileList | null) {
    if (!files) return;
    setOperationError("");
    const selected = [...files];
    if (!selected.length || selected.length > 512 || selected.some(file => file.size > 1_000_000)) {
      setOperationError("请选择 1–512 个文本文件，单文件不得超过 1 MB。");
      return;
    }
    const loaded: Record<string, string> = {};
    for (const file of selected) loaded[file.webkitRelativePath || file.name] = await file.text();
    setSourceFiles(loaded);
  }

  async function refreshRun(runId = run?.runId) {
    if (!runId) return;
    // A transient disconnect on one read surface must not discard the other
    // successful response or leave the mutation controls permanently busy.
    // The polling loop will retry either resource independently.
    const options = {
      headers: requestHeaders(),
      cache: "no-store" as const,
      signal: AbortSignal.timeout(8_000),
    };
    const [runResult, auditResult] = await Promise.allSettled([
      fetch(scopedRunUrl(`/api/frt/runs/${runId}`), options),
      fetch(scopedRunUrl(`/api/frt/runs/${runId}/audit`), options),
    ]);
    if (runResult.status === "fulfilled" && runResult.value.ok) {
      setRun(await runResult.value.json() as FrtRunView);
    }
    if (auditResult.status === "fulfilled" && auditResult.value.ok) {
      setAudit((await auditResult.value.json() as FrtAuditView).audit);
    }
  }

  useEffect(() => {
    if (!run || !["QUEUED", "RUNNING"].includes(run.state)) return;
    const timer = window.setInterval(() => void refreshRun(run.runId), 1_500);
    return () => window.clearInterval(timer);
  }, [run?.runId, run?.state, tenantId, actorId, runnerToken, workspaceId, projectId, environmentId, releaseId]);

  async function startRun(action: "PLAN" | "ANALYZE" | "EXECUTE" | "VERIFY") {
    if (!selectedSkill) return;
    setBusy(true);
    setOperationError("");
    try {
      if (action === "VERIFY" && (!run || run.skillId !== selectedSkill.id
        || ["QUEUED", "RUNNING"].includes(run.state))) {
        throw new Error("VERIFY 需要当前 Skill 在同一资源作用域内已有终态 Run。");
      }
      let parsedInput: unknown;
      try {
        parsedInput = JSON.parse(inputJson) as unknown;
      } catch {
        throw new Error("Skill 输入必须是有效 JSON。");
      }
      if (!parsedInput || typeof parsedInput !== "object" || Array.isArray(parsedInput)) {
        throw new Error("Skill 输入必须是 JSON object。");
      }
      const typedInput: Record<string, unknown> = { ...(parsedInput as Record<string, unknown>) };
      if (acceptsFiles && Object.keys(sourceFiles).length) typedInput.files = sourceFiles;
      const allowed = new Set<string>([
        ...selectedSkill.executionContract.inputContract.required,
        ...selectedSkill.executionContract.inputContract.optional,
      ]);
      const unknown = Object.keys(typedInput).filter(key => !allowed.has(key));
      if (unknown.length) throw new Error(`未声明的输入字段：${unknown.join(", ")}`);
      if (["ANALYZE", "EXECUTE"].includes(action)) {
        const missing = selectedSkill.executionContract.inputContract.required
          .filter(key => !Object.hasOwn(typedInput, key));
        if (missing.length) throw new Error(`缺少必需输入：${missing.join(", ")}`);
      }
      const submittedInput = action === "VERIFY" ? {} : typedInput;
      const response = await fetch("/api/frt/runs", {
        method: "POST",
        headers: requestHeaders(true),
        body: JSON.stringify({
          skillId: selectedSkill.id,
          action,
          idempotencyKey: `console-${crypto.randomUUID()}`,
          workspaceId,
          projectId,
          environmentId,
          releaseId,
          sourceSnapshotDigest: action === "VERIFY" ? run!.sourceSnapshotDigest : await sourceDigest(submittedInput),
          policyVersion,
          risk,
          ...(action === "VERIFY" ? {
            verificationSubject: { runId: run!.runId, resultDigest: run!.resultDigest },
          } : {}),
          ...(action === "VERIFY" || Object.keys(submittedInput).length === 0 ? {} : { input: submittedInput }),
        }),
      });
      const payload = await response.json() as FrtRunView & { reason?: string; errorCode?: string };
      if (!response.ok) throw new Error(payload.reason ?? payload.errorCode ?? "FRT_RUN_REJECTED");
      setRun(payload);
      setAudit([]);
      void refreshRun(payload.runId);
    } catch (error) {
      setOperationError(error instanceof Error ? error.message : "FRT_RUN_REJECTED");
    } finally {
      setBusy(false);
    }
  }

  async function transition(operation: "claim" | "heartbeat" | "cancel" | "retry") {
    if (!run) return;
    setBusy(true);
    setOperationError("");
    try {
      const response = await fetch(scopedRunUrl(`/api/frt/runs/${run.runId}/${operation}`), {
        method: "POST",
        headers: requestHeaders(true),
        body: JSON.stringify({ expectedVersion: run.version }),
      });
      const payload = await response.json() as FrtRunView & { reason?: string; errorCode?: string };
      if (!response.ok) throw new Error(payload.reason ?? payload.errorCode ?? "FRT_TRANSITION_REJECTED");
      setRun(payload);
      void refreshRun(payload.runId);
    } catch (error) {
      setOperationError(error instanceof Error ? error.message : "FRT_TRANSITION_REJECTED");
    } finally {
      setBusy(false);
    }
  }

  function downloadArtifacts() {
    if (!run) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(run.artifacts, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${run.runId}-artifacts.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function chooseSource(value: Stack) {
    setSource(value);
    if (value === target) {
      setTarget(frtCatalog.technologyStacks.find((candidate) => candidate !== value) ?? "React");
    }
  }

  function chooseTarget(value: Stack) {
    setTarget(value);
    if (value === source) {
      setSource(frtCatalog.technologyStacks.find((candidate) => candidate !== value) ?? "Vue 3");
    }
  }

  function openRouteSkill() {
    if (!selectedRoute) return;
    setBatch(selectedRoute.batch);
    setQuery(selectedRoute.skillId);
    setSelectedSkillId(selectedRoute.skillId);
    document.getElementById("frt-skill-catalog")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className={styles.page}>
      <section className={styles.hero} aria-labelledby="frt-title">
        <div className={styles.heroCopy}>
          <span className={styles.eyebrow}><Icon name="workflow" size={15} /> FRT G01–G30</span>
          <h1 id="frt-title">{t("前端仓库转换工厂", "Frontend repository transformation factory")}</h1>
          <p>{t("从仓库发现、类型化语义 IR 和 30 条方向路线，一直编排到产品闭环与生产就绪门禁。所有未知语义和未运行证据保持显式。", "Orchestrate repository discovery, typed UI semantics, 30 directed routes, product closure, and production-readiness gates. Unknown semantics and unexecuted evidence remain explicit.")}</p>
          <div className={styles.heroActions}>
            <a className={styles.primaryAction} href="#route-planner">{t("选择转换路线", "Choose a directed route")} <Icon name="arrow" size={15} /></a>
            <a className={styles.secondaryAction} href="#frt-skill-catalog">{t("浏览全部 Skills", "Browse every Skill")}</a>
          </div>
        </div>
        <div className={styles.heroMetrics} aria-label="FRT 能力规模" tabIndex={0}>
          <article><strong>30</strong><span>Generation Batches</span><small>线性依赖与失效传播</small></article>
          <article><strong>472</strong><span>Runtime Skills</span><small>全部可发现、可计划、可验证</small></article>
          <article><strong>30</strong><span>Directed routes</span><small>六类技术栈两两有向转换</small></article>
          <article className={styles.boundaryMetric}><strong>NOT_RUN</strong><span>Production evidence</span><small>真实设备、性能与生产门禁未冒充通过</small></article>
        </div>
      </section>

      <section className={styles.stageSection} aria-labelledby="stage-title">
        <div className={styles.sectionHeading}>
          <div><span className={styles.kicker}>Delivery chain</span><h2 id="stage-title">{t("六段式实施路径", "Six-stage delivery path")}</h2></div>
          <p>上游契约、Policy 或 Evidence Digest 变化会使下游结果进入 STALE / RETEST_REQUIRED。</p>
        </div>
        <ol className={styles.stageGrid}>
          {deliveryStages.map((stage, index) => (
            <li key={stage.range}>
              <span className={styles.stageNumber}>{String(index + 1).padStart(2, "0")}</span>
              <small>{stage.range}</small>
              <strong>{stage.title}</strong>
              <p>{stage.detail}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className={styles.routePlanner} id="route-planner" aria-labelledby="route-title">
        <div className={styles.routeHeader}>
          <div>
            <span className={styles.kicker}>Route Planner</span>
            <h2 id="route-title">{t("选择一条精确的有向转换路线", "Choose an exact directed transformation route")}</h2>
            <p>反向转换属于另一条独立 Route Pack，不沿用当前路线的证据或结论。</p>
          </div>
          <span className={styles.routeCount}><i /> 30 / 30 路线已注册</span>
        </div>
        <div className={styles.routeControls}>
          <label>
            <span>{t("源技术栈", "Source stack")}</span>
            <select value={source} onChange={(event) => chooseSource(event.target.value as Stack)}>
              {frtCatalog.technologyStacks.map((stack) => <option key={stack} value={stack}>{stack}</option>)}
            </select>
          </label>
          <span className={styles.routeArrow} aria-hidden="true"><Icon name="arrow" size={20} /></span>
          <label>
            <span>{t("目标技术栈", "Target stack")}</span>
            <select value={target} onChange={(event) => chooseTarget(event.target.value as Stack)}>
              {frtCatalog.technologyStacks.map((stack) => <option key={stack} value={stack}>{stack}</option>)}
            </select>
          </label>
        </div>
        {selectedRoute ? (
          <article className={styles.routeResult}>
            <div className={styles.routeIdentity}>
              <span className={styles.routeGlyph}>{source.slice(0, 1)}<i>→</i>{target.slice(0, 1)}</span>
              <div><small>{selectedRoute.batch} · {selectedRoute.skillId}</small><h3>{source} → {target}</h3><code>{selectedRoute.skillName}</code></div>
            </div>
            <dl className={styles.routeStates}>
              <div><dt>静态 Runtime</dt><dd data-state="ready">READY</dd></div>
              <div><dt>源 / 目标构建</dt><dd data-state="not-run">NOT_RUN</dd></div>
              <div><dt>浏览器 / 设备</dt><dd data-state="not-run">NOT_RUN</dd></div>
              <div><dt>认证</dt><dd data-state="blocked">NOT_CERTIFIED</dd></div>
            </dl>
            <button type="button" onClick={openRouteSkill}>查看 Route Skill <Icon name="arrow" size={15} /></button>
          </article>
        ) : <p className={styles.routeUnavailable}>源技术栈和目标技术栈必须不同。</p>}
      </section>

      <section className={styles.catalogSection} id="frt-skill-catalog" aria-labelledby="catalog-title">
        <div className={styles.sectionHeading}>
          <div><span className={styles.kicker}>Runtime Catalog</span><h2 id="catalog-title">{t("472 个实现级 Skill", "472 implementation-level Skills")}</h2></div>
          <p>每个 Skill 共用同一受治理 Runtime、Scope、幂等与 Evidence 协议，避免建立 472 套平行子系统。</p>
        </div>
        <div className={styles.catalogLayout}>
          <nav className={styles.batchRail} aria-label="按 Batch 筛选 Skill">
            <button className={batch === "ALL" ? styles.activeBatch : ""} type="button" onClick={() => setBatch("ALL")}>
              <span>ALL</span><strong>全部能力</strong><small>{frtCatalog.skillCount}</small>
            </button>
            {frtCatalog.batches.map((item) => (
              <button className={batch === item.id ? styles.activeBatch : ""} type="button" key={item.id} onClick={() => { setBatch(item.id); setQuery(""); }}>
                <span>{item.id}</span><strong>{item.title}</strong><small>{item.skillCount}</small>
              </button>
            ))}
          </nav>
          <div className={styles.catalogContent}>
            <div className={styles.catalogToolbar}>
              <label className={styles.searchBox}>
                <Icon name="search" size={17} />
                <span className="sr-only">搜索 Skill</span>
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 ID、名称或能力…" />
                {query && <button type="button" aria-label="清空搜索" onClick={() => setQuery("")}><Icon name="close" size={14} /></button>}
              </label>
              <span className={styles.resultCount}>显示 {visibleSkills.length} / {filteredSkills.length}</span>
            </div>
            {visibleSkills.length ? (
              <div className={styles.skillGrid}>
                {visibleSkills.map((skill) => (
                  <button
                    type="button"
                    className={`${styles.skillCard} ${selectedSkill?.id === skill.id ? styles.selectedSkill : ""}`}
                    key={skill.id}
                    onClick={() => setSelectedSkillId(skill.id)}
                    aria-pressed={selectedSkill?.id === skill.id}
                  >
                    <span className={styles.skillMeta}><b>{skill.id}</b><i>{skill.batch}</i></span>
                    <strong>{skill.title}</strong>
                    <code>{skill.name}</code>
                    <span className={styles.skillFooter}><small>Runtime interface ready</small><Icon name="chevron" size={14} /></span>
                  </button>
                ))}
              </div>
            ) : <div className={styles.emptyState}><Icon name="search" size={24} /><strong>没有匹配的 Skill</strong><p>尝试更换 Batch 或缩短搜索词。</p></div>}
            {filteredSkills.length > visibleSkills.length && <p className={styles.limitNote}>为保持页面响应速度，当前最多展示 72 项；请继续按 Batch 或关键词缩小范围。</p>}
          </div>
          <aside className={styles.skillInspector} aria-live="polite">
            {selectedSkill ? (
              <>
                <span className={styles.inspectorBatch}>{selectedSkill.batch} / {selectedSkill.certificateFamily} family</span>
                <h3>{selectedSkill.title}</h3>
                <code>{selectedSkill.id}</code>
                <p>{selectedSkill.description}</p>
                <dl>
                  <div><dt>风险</dt><dd>{selectedSkill.risk}</dd></div>
                  <div><dt>Capability</dt><dd>{selectedSkill.executionContract.capabilityKey}</dd></div>
                  <div><dt>执行级别</dt><dd>{selectedSkill.executionContract.executionClass}</dd></div>
                  <div><dt>前置证书</dt><dd>{selectedSkill.requiresCertificate ?? "System charter inputs"}</dd></div>
                  <div><dt>版本</dt><dd>{selectedSkill.version}</dd></div>
                  <div><dt>生产认证</dt><dd className={styles.notCertified}>NOT_CERTIFIED</dd></div>
                </dl>
                <div className={styles.operationList}>
                  <span>PLAN</span><span>ANALYZE</span><span>EXECUTE*</span><span>VERIFY</span>
                </div>
                <small className={styles.inspectorNote}>* EXECUTE 只准备受限提案；客户代码、真实 Provider、设备与生产操作需要外部 Runner 和授权。</small>
              </>
            ) : <p>选择一个 Skill 查看契约。</p>}
          </aside>
        </div>
        <section className={styles.operationConsole} aria-labelledby="operation-title" id="frt-operation-console">
          <div className={styles.operationHeading}>
            <div>
              <span className={styles.kicker}>Repository execution</span>
              <h3 id="operation-title">{t("仓库 → 计划 → 执行 → 证据闭环", "Repository → plan → execute → evidence loop")}</h3>
              <p>当前操作绑定 <strong>{selectedSkill?.id}</strong>；组织、租户与执行者由已认证账户或受限本地身份租约派生。</p>
            </div>
            <span className={styles.persistenceBadge}><i /> Durable / tenant-scoped</span>
          </div>

          <div className={styles.executionForm}>
            <fieldset>
              <legend>1. 运行作用域</legend>
              <div className={styles.fieldGrid}>
                <label><span>Workspace</span><input aria-label="FRT Workspace" value={workspaceId} onChange={event => setWorkspaceId(event.target.value)} /></label>
                <label><span>Project</span><input aria-label="FRT Project" value={projectId} onChange={event => setProjectId(event.target.value)} /></label>
                <label><span>Environment</span><input aria-label="FRT Environment" value={environmentId} onChange={event => setEnvironmentId(event.target.value)} /></label>
                <label><span>Release</span><input aria-label="FRT Release" value={releaseId} onChange={event => setReleaseId(event.target.value)} /></label>
                <label><span>Policy</span><input aria-label="FRT Policy" value={policyVersion} onChange={event => setPolicyVersion(event.target.value)} /></label>
                <label><span>Risk</span><select aria-label="FRT Risk" value={risk} onChange={event => setRisk(event.target.value as typeof risk)}>{["R0", "R1", "R2", "R3", "R4", "R5"].map(value => <option key={value}>{value}</option>)}</select></label>
              </div>
            </fieldset>

            <fieldset>
              <legend>2. Skill 类型化输入</legend>
              <div className={styles.contractSummary}>
                <span>必需</span>
                {selectedInputContract?.required.length
                  ? selectedInputContract.required.map(key => <code key={`required-${key}`}>{key}</code>)
                  : <small>无</small>}
                <span>可选</span>
                {selectedInputContract?.optional.length
                  ? selectedInputContract.optional.map(key => <code key={`optional-${key}`}>{key}</code>)
                  : <small>无</small>}
              </div>
              {acceptsFiles && (
                <>
                  <label className={styles.filePicker}>
                    <Icon name="repository" size={18} />
                    <span><strong>选择仓库文本文件</strong><small>最多 512 个、总计 ≤ 16 MB、单字段 ≤ 1 MB；安全相对路径和内容共同计算 Snapshot Digest。</small></span>
                    <input aria-label="选择 FRT 仓库文件" type="file" multiple onChange={event => void chooseRepositoryFiles(event.target.files)} />
                  </label>
                  <div className={styles.fileSummary} aria-live="polite">
                    <strong>{Object.keys(sourceFiles).length}</strong> 个文件已绑定
                    {Object.keys(sourceFiles).slice(0, 5).map(path => <code key={path}>{path}</code>)}
                    {Object.keys(sourceFiles).length > 5 && <small>+{Object.keys(sourceFiles).length - 5} more</small>}
                  </div>
                </>
              )}
              <label className={styles.jsonInput}>
                <span>输入 JSON（`files` 由上方选择器安全合并）</span>
                <textarea
                  aria-label="FRT Skill 类型化输入 JSON"
                  spellCheck={false}
                  value={inputJson}
                  onChange={event => setInputJson(event.target.value)}
                />
              </label>
              <button
                className={styles.resetInput}
                type="button"
                onClick={() => setInputJson(initialContractInput(selectedSkill))}
              >恢复契约示例</button>
            </fieldset>

            <details className={styles.localIdentity}>
              <summary>{t("本地开发身份租约（生产环境使用账户会话）", "Local development identity lease (production uses account sessions)")}</summary>
              <div className={styles.fieldGrid}>
                <label><span>租户标识</span><input aria-label="FRT 本地租户标识" value={tenantId} onChange={event => setTenantId(event.target.value)} /></label>
                <label><span>执行者标识</span><input aria-label="FRT 本地执行者标识" value={actorId} onChange={event => setActorId(event.target.value)} /></label>
                <label><span>本地 Runner 令牌</span><input aria-label="FRT 本地 Runner 令牌" type="password" autoComplete="off" value={runnerToken} onChange={event => setRunnerToken(event.target.value)} /></label>
              </div>
            </details>

            <div className={styles.runActions} aria-label="FRT 运行操作">
              {(["PLAN", "ANALYZE", "EXECUTE", "VERIFY"] as const).map(action => (
                <button type="button" key={action} disabled={busy} onClick={() => void startRun(action)}>{action}</button>
              ))}
            </div>
            {operationError && <p className={styles.operationError} role="alert">{operationError}</p>}
          </div>

          <div className={styles.runWorkspace} aria-live="polite">
            <div className={styles.runSummary}>
              <div><span>Run</span><strong>{run?.runId ?? "尚未创建"}</strong></div>
              <div><span>状态</span><strong data-run-state={run?.state ?? "EMPTY"}>{run?.state ?? "EMPTY"}</strong></div>
              <div><span>结果</span><strong>{run?.outcome ?? "等待操作"}</strong></div>
              <div><span>版本</span><strong>{run?.version ?? 0}</strong></div>
              {run && <div className={styles.lifecycleActions}>
                <button type="button" disabled={busy || run.state !== "QUEUED"} onClick={() => void transition("claim")}>Runner 领取</button>
                <button type="button" disabled={busy || run.state !== "RUNNING"} onClick={() => void transition("heartbeat")}>续租</button>
                <button type="button" disabled={busy || !["QUEUED", "RUNNING"].includes(run.state)} onClick={() => void transition("cancel")}>取消</button>
                <button type="button" disabled={busy || !["BLOCKED", "FAILED", "CANCELLED"].includes(run.state) || run.action !== "EXECUTE"} onClick={() => void transition("retry")}>重试</button>
                <button type="button" disabled={busy} onClick={() => void refreshRun()}>刷新</button>
              </div>}
            </div>

            <div className={styles.resultPanels}>
              <article>
                <h4>Findings <span>{run?.findings.length ?? 0}</span></h4>
                {run?.findings.length ? <ul tabIndex={0} aria-label="FRT Findings 列表">{run.findings.map((item, index) => <li key={`${item.code}-${index}`} data-severity={item.severity}><strong>{item.code}</strong><p>{item.message}</p><small>{item.blocking ? "BLOCKING" : item.severity}</small></li>)}</ul> : <p>暂无 Finding。</p>}
              </article>
              <article>
                <h4>Artifacts <button type="button" disabled={!run} onClick={downloadArtifacts}>下载 JSON</button></h4>
                <pre tabIndex={0} aria-label="FRT 运行产物 JSON">{run ? JSON.stringify(run.artifacts, null, 2) : "{}"}</pre>
              </article>
              <article>
                <h4>Evidence <span>{run?.evidence.length ?? 0}</span></h4>
                {run?.evidence.length ? <ul tabIndex={0} aria-label="FRT Evidence 列表">{run.evidence.map(item => <li key={`${item.role}-${item.uri}`}><strong>{item.role}</strong><code>{item.state}</code><small>{item.digest}</small></li>)}</ul> : <p>没有签名 Evidence；VERIFY 将 fail-closed。</p>}
                {run && <small>Gate eligible: {String(run.certificateFragment.eligibleForBatchGate)} · {run.certificateFragment.certification}</small>}
              </article>
              <article>
                <h4>Audit trail <span>{audit.length}</span></h4>
                {audit.length ? <ol tabIndex={0} aria-label="FRT Audit trail">{audit.map(item => <li key={item.sequence}><strong>{item.event}</strong><span>{item.state} · v{item.version}</span><small>{item.actor} · {new Date(item.at).toLocaleString()}</small></li>)}</ol> : <p>运行创建后显示持久化审计事件。</p>}
              </article>
            </div>
          </div>
        </section>
      </section>

      <section className={styles.boundarySection} aria-labelledby="boundary-title">
        <div><span className={styles.kicker}>Evidence boundary</span><h2 id="boundary-title">{t("已经实现，不代表已经生产认证", "Implemented does not mean production-certified")}</h2></div>
        <div className={styles.boundaryGrid}>
          <article><Icon name="check" size={18} /><div><strong>本地已就绪</strong><p>包完整性、472 接口、类型化 Runtime、目录/API/CLI、Scope、幂等、证据角色和失败关闭。</p></div></article>
          <article><Icon name="clock" size={18} /><div><strong>等待真实执行</strong><p>源/目标构建、浏览器与设备矩阵、独立 Holdout、Proof Kernel、性能、Chaos、安全测试。</p></div></article>
          <article><Icon name="lock" size={18} /><div><strong>外部权威保留</strong><p>Batch Certificate、Production Closure、发布、回滚、客户验收和持续认证不能由页面或模型签发。</p></div></article>
        </div>
      </section>
    </div>
  );
}
