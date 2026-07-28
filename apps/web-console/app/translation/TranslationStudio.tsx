"use client";

import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import { Icon } from "../components/Icon";
import { StatusChip } from "../components/StatusChip";
import { directedLanguageRoutes, translationLanguages } from "../lib/businessLines";
import type {
  DirectedLanguageRoute,
  TranslationCapabilityResponse,
  TranslationDiscoveryReport,
  TranslationDiscoveryResult,
  TranslationJob,
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

type TranslationRunnerHealth = {
  status: "READY" | "DISABLED" | "BLOCKED";
  isolation: "ROOTLESS_CONTAINER" | "HOST_DEVELOPMENT" | "NOT_CONFIGURED";
  sourceStorage: "READ_ONLY" | "NOT_RUN" | "BLOCKED";
  activeJobs: number;
  reason?: string;
};

const STORAGE_KEY = "elmos.translation-handoff.v3";
const JOB_STORAGE_KEY = "elmos.translation.latest-job-id";
const WORK_UNIT_PAGE_SIZE = 25;
const routeIds = new Set(directedLanguageRoutes.map((route) => route.id));

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

/**
 * The console renders whatever the repository route contract reports. It never
 * upgrades a status on its own: a route that the contract does not describe, or
 * whose local profile has not passed, stays unselectable and visibly NOT_RUN.
 */
function routeCellLabel(route: DirectedLanguageRoute | undefined): string {
  if (!route) return "NO ROUTE";
  if (route.localExecution === "PASSED") return "LOCAL PASS";
  if (route.localExecution === "FAILED") return "LOCAL FAIL";
  return "NOT_RUN";
}

function routeCellIcon(route: DirectedLanguageRoute | undefined) {
  if (!route) return "close" as const;
  if (route.localExecution === "PASSED") return "check" as const;
  return "lock" as const;
}

export function TranslationStudio() {
  const [sourceLanguage, setSourceLanguage] = useState<TranslationLanguageId>("java");
  const [targetLanguage, setTargetLanguage] = useState<TranslationLanguageId>("python");
  const [repositoryRef, setRepositoryRef] = useState("local:customer-repository");
  const [scope, setScope] = useState<Handoff["scope"]>("repository");
  const [handoff, setHandoff] = useState<Handoff | null>(null);
  const [repositoryPlan, setRepositoryPlan] = useState<TranslationRepositoryPlan | null>(null);
  const [discovery, setDiscovery] = useState<TranslationDiscoveryReport | null>(null);
  const [workUnitFilter, setWorkUnitFilter] = useState("");
  const [workUnitPage, setWorkUnitPage] = useState(0);
  const [capability, setCapability] = useState<TranslationCapabilityResponse | null>(null);
  const [capabilityError, setCapabilityError] = useState("");
  const [importing, setImporting] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [actorId, setActorId] = useState("");
  const [runnerToken, setRunnerToken] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [casesBundleId, setCasesBundleId] = useState("");
  const [recoveryJobId, setRecoveryJobId] = useState("");
  const [runnerHealth, setRunnerHealth] = useState<TranslationRunnerHealth | null>(null);
  const [job, setJob] = useState<TranslationJob | null>(null);
  const [jobBusy, setJobBusy] = useState(false);

  const languages = capability?.languages ?? translationLanguages;
  const routes = capability?.routes ?? directedLanguageRoutes;
  const routeByPair = useMemo(() => {
    const index = new Map<string, DirectedLanguageRoute>();
    for (const route of routes) index.set(`${route.source}>${route.target}`, route);
    return index;
  }, [routes]);
  const selectedRoute = routeByPair.get(`${sourceLanguage}>${targetLanguage}`);
  const selectedRouteExecutable = selectedRoute?.localExecution === "PASSED";

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/capabilities/translation", { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const payload = await response.json().catch(() => null) as
          | TranslationCapabilityResponse
          | { status?: string; errorCode?: string; message?: string }
          | null;
        if (!response.ok || !payload || !("routes" in payload)) {
          const detail = payload && "errorCode" in payload && payload.errorCode
            ? `${payload.errorCode}：${payload.message ?? ""}`
            : `HTTP_${response.status}`;
          throw new Error(detail);
        }
        setCapability(payload);
        setCapabilityError("");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setCapability(null);
        setCapabilityError(
          `路线能力契约不可读取（${error instanceof Error ? error.message : "UNKNOWN"}）；`
          + "所有路线状态保持 NOT_RUN，页面不会展示未读取到的通过结论。",
        );
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
    fetch("/api/translation/health", { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json() as TranslationRunnerHealth;
        setRunnerHealth(payload);
      })
      .catch(() => setRunnerHealth({
        status: "BLOCKED",
        isolation: "NOT_CONFIGURED",
        sourceStorage: "BLOCKED",
        activeJobs: 0,
        reason: "TRANSLATION_RUNNER_HEALTH_UNAVAILABLE",
      }));
    const latest = window.sessionStorage.getItem(JOB_STORAGE_KEY);
    if (latest && /^[0-9a-f-]{36}$/.test(latest)) setRecoveryJobId(latest);
  }, []);

  useEffect(() => {
    if (!job || !["QUEUED", "RUNNING"].includes(job.status)) return;
    const timer = window.setInterval(() => {
      void runnerRequest<TranslationJob>(`/api/translation/jobs/${job.id}`)
        .then(setJob)
        .catch((error: Error) => setFeedback(`任务刷新失败：${error.message}`));
    }, 1_500);
    return () => window.clearInterval(timer);
  }, [job, tenantId, actorId, runnerToken]);

  useEffect(() => {
    if (!feedback) return;
    const timer = window.setTimeout(() => setFeedback(""), 5_200);
    return () => window.clearTimeout(timer);
  }, [feedback]);

  const sourceProfile = languages.find((language) => language.id === sourceLanguage);
  const targetProfile = languages.find((language) => language.id === targetLanguage);
  const routeCommand = `uv --directory engines/polyglot-route-engine run --locked elmos-polyglot-route --source <SOURCE_FILE> --source-language ${sourceLanguage} --target-language ${targetLanguage} --function <FUNCTION_NAME> --cases <CASES_JSON> --output <NEW_OUTPUT_DIR>`;
  const engineCommand = "uv --directory engines/polyglot-route-engine run --locked elmos-polyglot-route";
  const inventoryCommand = `${engineCommand} inventory --repository <READ_ONLY_REPOSITORY> --repository-ref ${repositoryRef.trim() || "<SAFE_REPOSITORY_REF>"} --source-language ${sourceLanguage} --target-language ${targetLanguage} --output repository-route-plan.json`;
  const discoverCommand = `${engineCommand} discover --repository <READ_ONLY_REPOSITORY> --plan repository-route-plan.json --output repository-discovery-report.json`;
  const batchCommand = `${engineCommand} batch --repository <READ_ONLY_REPOSITORY> --discovery repository-discovery-report.json --cases-directory <BEHAVIOR_CASES_DIR> --output <NEW_BATCH_OUTPUT_DIR>`;
  const repositoryCommands = [inventoryCommand, discoverCommand, batchCommand];
  const validationCommands = selectedRoute ? [
    `python3 scripts/batch29/validate_route.py routes/${selectedRoute.id}`,
    `python3 scripts/batch29/run_route_gate.py routes/${selectedRoute.id}`,
  ] : [];
  const routeCounts = useMemo(() => ({
    total: routes.length,
    locallyPassed: routes.filter((route) => route.localExecution === "PASSED").length,
    externallyPending: routes.filter((route) => route.externalVerification === "NOT_RUN").length,
  }), [routes]);

  const filteredWorkUnits = useMemo(() => {
    const units = repositoryPlan?.work_units ?? [];
    const needle = workUnitFilter.trim().toLowerCase();
    if (!needle) return units;
    return units.filter((unit) => unit.source_path.toLowerCase().includes(needle));
  }, [repositoryPlan, workUnitFilter]);
  const workUnitPageCount = Math.max(1, Math.ceil(filteredWorkUnits.length / WORK_UNIT_PAGE_SIZE));
  const visibleWorkUnits = filteredWorkUnits.slice(
    workUnitPage * WORK_UNIT_PAGE_SIZE,
    workUnitPage * WORK_UNIT_PAGE_SIZE + WORK_UNIT_PAGE_SIZE,
  );

  const discoveryByUnit = useMemo(() => {
    const index = new Map<string, TranslationDiscoveryResult>();
    for (const result of discovery?.results ?? []) index.set(result.id, result);
    return index;
  }, [discovery]);

  function resetDerivedState() {
    setHandoff(null);
    setRepositoryPlan(null);
    setDiscovery(null);
    setWorkUnitFilter("");
    setWorkUnitPage(0);
  }

  function chooseSource(id: TranslationLanguageId) {
    setSourceLanguage(id);
    if (id === targetLanguage) {
      const replacement = languages.find((language) => language.id !== id);
      if (replacement) setTargetLanguage(replacement.id);
    }
    resetDerivedState();
  }

  function chooseTarget(id: TranslationLanguageId) {
    if (id === sourceLanguage) return;
    setTargetLanguage(id);
    resetDerivedState();
  }

  function saveHandoff() {
    if (!selectedRoute) {
      setFeedback("当前源/目标组合在仓库路线契约中不存在，无法生成交接。");
      return;
    }
    if (!isSafeRepositoryRef(repositoryRef.trim())) {
      setFeedback("仓库引用仅接受不含凭证、查询参数或本机路径的 local: 标识或 HTTPS 地址。");
      return;
    }
    if (!selectedRouteExecutable) {
      setFeedback(`路线 ${selectedRoute.id} 的本地受限 Profile 状态为 ${selectedRoute.localExecution}，不生成交接。`);
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
    if (!selectedRoute) {
      setFeedback("当前源/目标组合不在仓库路线契约中，拒绝导入清单。");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      setFeedback("仓库清单超过 8 MB 上限，请缩小评估范围。");
      return;
    }
    setImporting(true);
    try {
      const plan = JSON.parse(await file.text()) as unknown;
      // The browser never decides acceptance. The server re-reads the route
      // contract and re-validates every field before the plan is bound here.
      const response = await fetch("/api/translation/repository-plan", {
        method: "POST",
        cache: "no-store",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          repositoryRef: repositoryRef.trim(),
          routeId: selectedRoute.id,
          sourceLanguage,
          targetLanguage,
          plan,
        }),
      });
      const payload = await response.json().catch(() => null) as
        | { status: "ACCEPTED"; plan: TranslationRepositoryPlan }
        | { status: "BLOCKED"; errorCode: string; message: string }
        | null;
      if (!response.ok || !payload || payload.status !== "ACCEPTED") {
        const code = payload && payload.status === "BLOCKED" ? payload.errorCode : `HTTP_${response.status}`;
        const detail = payload && payload.status === "BLOCKED" ? payload.message : "服务端拒绝了该清单。";
        throw new Error(`${code}：${detail}`);
      }
      setRepositoryPlan(payload.plan);
      setHandoff(null);
      setDiscovery(null);
      setWorkUnitFilter("");
      setWorkUnitPage(0);
      setFeedback(
        `服务端已校验只读清单：${payload.plan.source_file_count} 个源文件拆为 `
        + `${payload.plan.work_units.length} 个待发现工作单元，执行状态仍为 NOT_RUN。`,
      );
    } catch (error) {
      setRepositoryPlan(null);
      setFeedback(`仓库清单导入失败：${error instanceof Error ? error.message : "REPOSITORY_PLAN_INVALID"}`);
    } finally {
      setImporting(false);
    }
  }

  async function importDiscovery(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !selectedRoute || !repositoryPlan) return;
    if (file.size > 8 * 1024 * 1024) {
      setFeedback("发现报告超过 8 MB 上限，请缩小评估范围。");
      return;
    }
    setImporting(true);
    try {
      const report = JSON.parse(await file.text()) as unknown;
      const response = await fetch("/api/translation/discovery-report", {
        method: "POST",
        cache: "no-store",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          repositoryRef: repositoryRef.trim(),
          routeId: selectedRoute.id,
          snapshotSha256: repositoryPlan.snapshot_sha256,
          sourceLanguage,
          targetLanguage,
          report,
        }),
      });
      const payload = await response.json().catch(() => null) as
        | { status: "ACCEPTED"; report: TranslationDiscoveryReport }
        | { status: "BLOCKED"; errorCode: string; message: string }
        | null;
      if (!response.ok || !payload || payload.status !== "ACCEPTED") {
        const code = payload && payload.status === "BLOCKED" ? payload.errorCode : `HTTP_${response.status}`;
        const detail = payload && payload.status === "BLOCKED" ? payload.message : "服务端拒绝了该发现报告。";
        throw new Error(`${code}：${detail}`);
      }
      setDiscovery(payload.report);
      setWorkUnitPage(0);
      setFeedback(
        `服务端已校验发现报告：${payload.report.discovered_count} 个单元完成判定，`
        + `${payload.report.ready_count} 个 READY；转换执行仍为 NOT_RUN。`,
      );
    } catch (error) {
      setDiscovery(null);
      setFeedback(`发现报告导入失败：${error instanceof Error ? error.message : "DISCOVERY_INVALID"}`);
    } finally {
      setImporting(false);
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

  async function runnerRequest<T>(url: string, init?: RequestInit): Promise<T> {
    const response = await fetch(url, {
      cache: "no-store",
      ...init,
      headers: {
        ...(init?.body ? { "content-type": "application/json" } : {}),
        authorization: `Bearer ${runnerToken}`,
        "x-elmos-tenant": tenantId,
        "x-elmos-actor": actorId,
        ...init?.headers,
      },
    });
    const payload = await response.json().catch(() => null) as
      | T
      | { reason?: string; errorCode?: string }
      | null;
    if (!response.ok) {
      const reason = payload && typeof payload === "object" && "reason" in payload
        ? payload.reason
        : payload && typeof payload === "object" && "errorCode" in payload
          ? payload.errorCode
          : `HTTP_${response.status}`;
      throw new Error(reason || `HTTP_${response.status}`);
    }
    return payload as T;
  }

  async function startRepositoryPipeline() {
    if (!selectedRouteExecutable) {
      setFeedback("当前路线没有本地 Profile 通过证据，受控执行保持关闭。");
      return;
    }
    setJobBusy(true);
    try {
      const next = await runnerRequest<TranslationJob>("/api/translation/jobs", {
        method: "POST",
        body: JSON.stringify({
          workspaceId: workspaceId.trim(),
          casesBundleId: casesBundleId.trim(),
          sourceLanguage,
          targetLanguage,
        }),
      });
      setJob(next);
      setRecoveryJobId(next.id);
      window.sessionStorage.setItem(JOB_STORAGE_KEY, next.id);
      setFeedback("整库任务已进入持久队列；页面将显示真实编译、回放、装配与构建状态。");
    } catch (error) {
      setFeedback(`整库执行被阻断：${error instanceof Error ? error.message : "TRANSLATION_RUNNER_ERROR"}`);
    } finally {
      setJobBusy(false);
    }
  }

  async function recoverRepositoryPipeline() {
    setJobBusy(true);
    try {
      const next = await runnerRequest<TranslationJob>(
        `/api/translation/jobs/${recoveryJobId.trim()}`,
      );
      setJob(next);
      window.sessionStorage.setItem(JOB_STORAGE_KEY, next.id);
      setFeedback("已按任务 UUID 与当前租户身份恢复持久任务。");
    } catch (error) {
      setFeedback(`任务恢复失败：${error instanceof Error ? error.message : "TRANSLATION_JOB_NOT_FOUND"}`);
    } finally {
      setJobBusy(false);
    }
  }

  async function cancelRepositoryPipeline() {
    if (!job) return;
    setJobBusy(true);
    try {
      setJob(await runnerRequest<TranslationJob>(`/api/translation/jobs/${job.id}/cancel`, {
        method: "POST",
      }));
      setFeedback("任务已取消；已经写入的检查点保留为审计事实。");
    } catch (error) {
      setFeedback(`取消失败：${error instanceof Error ? error.message : "TRANSLATION_CANCEL_FAILED"}`);
    } finally {
      setJobBusy(false);
    }
  }

  async function downloadRepositoryArtifact() {
    if (!job?.artifactReady || !job.artifactSha256 || !job.artifactSize) return;
    setJobBusy(true);
    try {
      const response = await fetch(`/api/translation/jobs/${job.id}/artifact`, {
        cache: "no-store",
        headers: {
          authorization: `Bearer ${runnerToken}`,
          "x-elmos-tenant": tenantId,
          "x-elmos-actor": actorId,
        },
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { reason?: string } | null;
        throw new Error(payload?.reason ?? `HTTP_${response.status}`);
      }
      const blob = await response.blob();
      const digest = [...new Uint8Array(await crypto.subtle.digest(
        "SHA-256",
        await blob.arrayBuffer(),
      ))].map((value) => value.toString(16).padStart(2, "0")).join("");
      if (
        response.headers.get("x-content-sha256") !== job.artifactSha256
        || digest !== job.artifactSha256
        || blob.size !== job.artifactSize
      ) {
        throw new Error("TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH");
      }
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${job.sourceLanguage}-to-${job.targetLanguage}-${job.status.toLowerCase()}.zip`;
      anchor.click();
      URL.revokeObjectURL(url);
      setFeedback(`已复算 ZIP 摘要并下载；结果状态 ${job.status}，外部验证仍为 NOT_RUN。`);
    } catch (error) {
      setFeedback(`归档下载失败：${error instanceof Error ? error.message : "TRANSLATION_DOWNLOAD_FAILED"}`);
    } finally {
      setJobBusy(false);
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
      contractPath: capability?.contractPath ?? "UNREAD",
      semanticProfile: capability?.semanticProfile ?? "UNKNOWN",
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

  function exportWorkUnits() {
    if (!repositoryPlan) return;
    const header = "source_path,source_sha256,source_bytes,status,execution_status,unsupported_until_discovered\n";
    const rows = repositoryPlan.work_units.map((unit) => [
      unit.source_path,
      unit.source_sha256,
      String(unit.source_bytes),
      unit.status,
      unit.execution_status,
      unit.unsupported_until_discovered.join(" | "),
    ].map((cell) => `"${cell.replaceAll('"', '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([header + rows + "\n"], { type: "text/csv" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${repositoryPlan.route_id}-work-units.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
    setFeedback("工作单元清单已导出为 CSV；每个单元的执行状态仍为 NOT_RUN。");
  }

  return (
    <div className="page-stack business-page">
      <section className="page-header business-hero">
        <div>
          <span className="overline">DIRECTED LANGUAGE ROUTES · BATCH 29</span>
          <h1>全库跨语言转换</h1>
          <p>Java、C#、Python 与 TypeScript 形成 12 条方向独立的转换路线；每条路线分别绑定语义风险、精确工具链、语料和认证证据。</p>
        </div>
        <div className="header-actions">
          <StatusChip
            status={capability
              ? routes.some((route) => route.status === "LIMITED")
                ? "LIMITED"
                : "EXPERIMENTAL"
              : "BLOCKED"}
          />
          <StatusChip status={capability?.certificationStatus === "CERTIFIED" ? "READY" : "NOT_CERTIFIED"} />
        </div>
      </section>

      <section className="metric-grid metric-grid-four" aria-label="跨语言路线摘要">
        <article className="metric-card"><span>语言引擎</span><strong>{languages.length}</strong><small>精确版本、相互独立</small></article>
        <article className="metric-card"><span>有向路线</span><strong>{capability?.routePackageCount ?? routeCounts.total}</strong><small>反向路线不复用结论</small></article>
        <article className="metric-card"><span>本地受限 Profile</span><strong className={routeCounts.locallyPassed > 0 ? "" : "warning-text"}>{routeCounts.locallyPassed}</strong><small>{capability?.semanticProfile ?? "契约未读取"}</small></article>
        <article className="metric-card"><span>独立验证待办</span><strong className="warning-text">{routeCounts.externallyPending}</strong><small>外部证据 {capability?.externalExecutionEvidence ?? "UNREAD"}</small></article>
      </section>

      <section className="source-notice" role={capabilityError ? "alert" : "status"}>
        <Icon name="route" size={16} />
        <span>{capabilityError || capability?.note || "正在读取仓库路线契约。"}</span>
        <StatusChip status={capabilityError ? "BLOCKED" : "REPOSITORY_CONTRACT"} compact />
      </section>

      <div className="translation-layout">
        <section className="surface-card route-picker" aria-labelledby="route-picker-title">
          <div className="business-section-heading"><div><span className="overline">DIRECTION MATTERS</span><h2 id="route-picker-title">选择源语言与目标语言</h2></div><span className="route-direction">{sourceProfile?.label} <Icon name="arrow" size={15} /> {targetProfile?.label}</span></div>
          <div className="language-pickers">
            <fieldset><legend>1 · 源语言</legend><div>{languages.map((language) => <button type="button" className={sourceLanguage === language.id ? "selected" : ""} key={language.id} onClick={() => chooseSource(language.id)} aria-pressed={sourceLanguage === language.id}><strong>{language.label}</strong><small>{language.compiler}</small></button>)}</div></fieldset>
            <fieldset><legend>2 · 目标语言</legend><div>{languages.map((language) => <button type="button" disabled={sourceLanguage === language.id} className={targetLanguage === language.id ? "selected" : ""} key={language.id} onClick={() => chooseTarget(language.id)} aria-pressed={targetLanguage === language.id}><strong>{language.label}</strong><small>{language.runtime}</small></button>)}</div></fieldset>
          </div>
          <div className="route-matrix" role="table" aria-label={`${routeCounts.total} 条有向语言路线的本地执行状态`}>
            <div className="route-matrix-row route-matrix-head" role="row"><span role="columnheader">源 \\ 目标</span>{languages.map((language) => <b role="columnheader" key={language.id}>{language.label}</b>)}</div>
            {languages.map((source) => (
              <div className="route-matrix-row" role="row" key={source.id}>
                <b role="rowheader">{source.label}</b>
                {languages.map((target) => {
                  const route = routeByPair.get(`${source.id}>${target.id}`);
                  const passed = route?.localExecution === "PASSED";
                  return (
                    <span className="route-matrix-cell" role="cell" key={target.id}>
                      {source.id === target.id
                        ? <span className="route-na">—</span>
                        : (
                          <button
                            type="button"
                            disabled={!route}
                            className={[
                              sourceLanguage === source.id && targetLanguage === target.id ? "selected" : "",
                              passed ? "" : "route-not-run",
                            ].filter(Boolean).join(" ")}
                            onClick={() => {
                              if (!route) return;
                              setSourceLanguage(source.id);
                              setTargetLanguage(target.id);
                              resetDerivedState();
                            }}
                            aria-label={route
                              ? `${source.label} 到 ${target.label}，本地执行 ${route.localExecution}，`
                                + `独立验证 ${route.independentVerification}，外部认证 ${route.externalVerification}`
                              : `${source.label} 到 ${target.label}，仓库路线契约中不存在该路线`}
                          >
                            <Icon name={routeCellIcon(route)} size={12} />
                            <span>{routeCellLabel(route)}</span>
                          </button>
                        )}
                    </span>
                  );
                })}
              </div>
            ))}
          </div>
        </section>

        {selectedRoute
          ? <aside className="surface-card route-detail">
              <div className="business-section-heading"><div><span className="overline">{selectedRoute.id}</span><h2>{sourceProfile?.label} → {targetProfile?.label}</h2></div><StatusChip status={selectedRoute.status} compact /></div>
              <dl className="route-profile-facts">
                <div><dt>源工具链</dt><dd>{sourceProfile?.compiler}</dd></div>
                <div><dt>目标运行时</dt><dd>{targetProfile?.runtime}</dd></div>
                <div><dt>方向 Skill</dt><dd>${selectedRoute.skill}</dd></div>
                <div><dt>本地执行</dt><dd>{selectedRoute.localExecution}</dd></div>
                <div><dt>独立验证</dt><dd>{selectedRoute.independentVerification}</dd></div>
                <div><dt>外部认证</dt><dd>{selectedRoute.externalVerification}</dd></div>
              </dl>
              <h3>必须显式处理的语义风险</h3>
              <ul className="hazard-list">{selectedRoute.hazards.map((hazard) => <li key={hazard}><Icon name="clock" size={13} />{hazard}</li>)}</ul>
              <h3>适用边界与剩余阻断</h3>
              <ul className="blocker-list compact">{selectedRoute.blockers.map((blocker) => <li key={blocker}><Icon name="lock" size={13} /><span>{blocker}</span></li>)}</ul>
            </aside>
          : <aside className="surface-card route-detail">
              <div className="business-section-heading"><div><span className="overline">NO ROUTE</span><h2>{sourceProfile?.label} → {targetProfile?.label}</h2></div><StatusChip status="BLOCKED" compact /></div>
              <p className="route-empty-detail">仓库路线契约中没有这条有向路线，或契约尚未读取成功。页面不会为未读取到的路线推断状态。</p>
            </aside>}
      </div>

      <section className="surface-card route-handoff" aria-labelledby="route-handoff-title">
        <div className="business-section-heading"><div><span className="overline">CONTROLLED HANDOFF</span><h2 id="route-handoff-title">准备定向路线，不伪造转换结果</h2></div><StatusChip status={handoff ? "REVIEW" : "DRAFT"} compact /></div>
        <div className="route-handoff-grid">
          <label><span>仓库引用</span><input value={repositoryRef} onChange={(event) => { setRepositoryRef(event.target.value); resetDerivedState(); }} maxLength={180} aria-describedby="repository-ref-hint" /><small id="repository-ref-hint">只填写引用，不填写 Token、客户代码或本机绝对路径。</small></label>
          <label><span>评估范围</span><select value={scope} onChange={(event) => { setScope(event.target.value as Handoff["scope"]); setHandoff(null); if (event.target.value !== "repository") { setRepositoryPlan(null); setWorkUnitFilter(""); setWorkUnitPage(0); } }}><option value="single-module">单个受限纯函数（可本地执行）</option><option value="repository">整个仓库（只读清单 + 工作单元）</option><option value="portfolio">多仓组合（发现与拆分计划）</option></select></label>
          {scope === "repository" && (
            <div className="repository-plan-import">
              <div><span>整库只读清单</span><StatusChip status={repositoryPlan ? "READY" : "NOT_RUN"} compact /></div>
              <label className={`button button-secondary ${!selectedRouteExecutable || importing ? "button-disabled" : ""}`}>
                <Icon name="file" size={15} />
                <span>{importing ? "服务端校验中…" : "导入仓库清单 JSON"}</span>
                <input
                  type="file"
                  accept="application/json,.json"
                  disabled={!selectedRouteExecutable || importing}
                  onChange={(event) => void importInventory(event)}
                />
              </label>
              {repositoryPlan
                ? <dl><div><dt>Snapshot</dt><dd>{repositoryPlan.snapshot_sha256.slice(0, 12)}…</dd></div><div><dt>源文件</dt><dd>{repositoryPlan.source_file_count}</dd></div><div><dt>工作单元</dt><dd>{repositoryPlan.work_units.length}</dd></div><div><dt>执行</dt><dd>{repositoryPlan.execution_status}</dd></div></dl>
                : <small>{selectedRouteExecutable
                    ? "先在只读仓库目录执行清单命令；符号链接、构建目录、超大或变化中的文件会被忽略或失败关闭。清单由服务端按仓库路线契约重新校验。"
                    : "当前路线的本地受限 Profile 未通过，导入入口保持关闭。"}</small>}
            </div>
          )}
          <div className="route-command-stack"><span>{scope === "repository" ? "整库三段式命令：清单 → 发现 → 批量执行" : "精确 Profile 执行模板"}</span><code>{scope === "repository" ? repositoryCommands.join("\n\n") : routeCommand}</code><small>{scope === "single-module" ? "命令只接受 typed-pure-function-v1；任何越界语义都会失败关闭。" : scope === "repository" ? "清单只读取受支持源文件；discover 用真实编译器分析器逐单元判定；batch 只执行 READY 且有独立行为语料的单元，可断点续跑，任何跳过或失败都让批次保持 PARTIAL。" : "多仓组合必须先逐仓生成清单并形成显式依赖图；当前不会把单函数证据扩张成组合成功。"}</small></div>
          <div className="route-handoff-actions"><button type="button" className="button button-primary" onClick={saveHandoff} disabled={!selectedRouteExecutable}><Icon name="file" size={15} />保存路线交接</button><button type="button" className="button button-secondary" onClick={exportHandoff}><Icon name="external" size={15} />导出 JSON</button><button type="button" className="button button-secondary" onClick={() => copyText([...(scope === "repository" ? repositoryCommands : [routeCommand]), ...validationCommands].join("\n"), "精确执行模板与保守门禁命令已复制。")}><Icon name="copy" size={15} />复制命令</button></div>
        </div>
      </section>

      <section className="surface-card route-handoff translation-runner-card" aria-labelledby="translation-runner-title">
        <div className="business-section-heading">
          <div>
            <span className="overline">PERSISTENT CONTROLLED RUNNER</span>
            <h2 id="translation-runner-title">一键执行整库受限转换</h2>
          </div>
          <StatusChip status={job?.status ?? runnerHealth?.status ?? "NOT_RUN"} compact />
        </div>
        <p>
          Runner 从管理员预先材料化的只读源码与独立行为用例目录读取输入，自动完成清单、编译器发现、
          断点批处理、无冲突装配、真实构建和内容寻址归档。它只覆盖 typed-pure-function-v1；
          `PARTIAL` 会完整保留跳过与失败，绝不等同于整库完成。
        </p>
        <div className="business-form-grid">
          <label>
            <span>租户标识</span>
            <input aria-label="跨语言租户标识" value={tenantId} onChange={(event) => setTenantId(event.target.value)} autoComplete="off" />
          </label>
          <label>
            <span>执行者标识</span>
            <input aria-label="跨语言执行者标识" value={actorId} onChange={(event) => setActorId(event.target.value)} autoComplete="off" />
          </label>
          <label className="spring-field-wide">
            <span>本地 Runner 短期令牌</span>
            <input aria-label="跨语言 Runner 令牌" type="password" value={runnerToken} onChange={(event) => setRunnerToken(event.target.value)} autoComplete="off" />
          </label>
          <label>
            <span>受控源码工作区 ID</span>
            <input value={workspaceId} onChange={(event) => setWorkspaceId(event.target.value)} pattern="[a-z0-9][a-z0-9._-]{2,80}" placeholder="customer-repository" />
          </label>
          <label>
            <span>独立行为用例包 ID</span>
            <input value={casesBundleId} onChange={(event) => setCasesBundleId(event.target.value)} pattern="[a-z0-9][a-z0-9._-]{2,80}" placeholder="customer-repository-holdout" />
          </label>
          <div className="locked-target spring-field-wide">
            <span>执行边界</span>
            <strong>
              {runnerHealth?.status ?? "CHECKING"} · {runnerHealth?.isolation ?? "NOT_CONFIGURED"}
            </strong>
            <small>
              源存储 {runnerHealth?.sourceStorage ?? "NOT_RUN"} · 活跃任务 {runnerHealth?.activeJobs ?? 0}。
              {runnerHealth?.reason ? ` ${runnerHealth.reason}` : " 生产模式只允许不可变镜像的 Rootless Container。"}
            </small>
          </div>
          <label className="spring-field-wide">
            <span>恢复任务 UUID</span>
            <input value={recoveryJobId} onChange={(event) => setRecoveryJobId(event.target.value.toLowerCase())} pattern="[0-9a-f-]{36}" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
          </label>
        </div>
        <div className="business-actions">
          <button
            type="button"
            className="button button-primary"
            disabled={jobBusy || runnerHealth?.status !== "READY" || !selectedRouteExecutable}
            onClick={() => void startRepositoryPipeline()}
          >
            <Icon name="workflow" size={15} />启动整库转换
          </button>
          <button
            type="button"
            className="button button-secondary"
            disabled={jobBusy || !/^[0-9a-f-]{36}$/.test(recoveryJobId)}
            onClick={() => void recoverRepositoryPipeline()}
          >
            <Icon name="refresh" size={15} />恢复任务
          </button>
          <button
            type="button"
            className="button button-secondary"
            disabled={jobBusy || !job || !["QUEUED", "RUNNING"].includes(job.status)}
            onClick={() => void cancelRepositoryPipeline()}
          >
            取消
          </button>
          <button
            type="button"
            className="button button-secondary"
            disabled={jobBusy || !job?.artifactReady}
            onClick={() => void downloadRepositoryArtifact()}
          >
            <Icon name="file" size={15} />下载摘要校验归档
          </button>
        </div>
        {job && (
          <div className="spring-run-summary">
            <dl className="spring-run-facts">
              <div><dt>任务</dt><dd>{job.id}</dd></div>
              <div><dt>阶段 / 进度</dt><dd>{job.stage} · {job.progress}%</dd></div>
              <div><dt>路线</dt><dd>{job.sourceLanguage} → {job.targetLanguage}</dd></div>
              <div><dt>工作单元</dt><dd>{job.includedUnitCount ?? 0} / {job.workUnitCount ?? "NOT_RUN"}</dd></div>
              <div><dt>真实构建</dt><dd>{job.buildVerification?.status ?? "NOT_RUN"}</dd></div>
              <div><dt>外部证据</dt><dd>{job.externalVerificationStatus} · {job.certificationStatus}</dd></div>
            </dl>
            {job.reason && <p className="warning-text">{job.reason}</p>}
            <pre aria-label="跨语言任务日志">{job.logs.map((entry) => `[${entry.stream}] ${entry.message}`).join("\n") || "日志尚未产生。"}</pre>
          </div>
        )}
      </section>

      {repositoryPlan && (
        <section className="surface-card work-unit-card" aria-labelledby="work-unit-title">
          <div className="business-section-heading">
            <div><span className="overline">DISCOVERY BACKLOG</span><h2 id="work-unit-title">整库工作单元</h2></div>
            <StatusChip status="NOT_RUN" compact />
          </div>
          <p className="work-unit-summary">
            {repositoryPlan.work_units.length} 个工作单元来自 Snapshot {repositoryPlan.snapshot_sha256.slice(0, 12)}…，
            忽略符号链接 {repositoryPlan.ignored_symlink_count} 个。每个单元都必须补齐函数名与独立行为语料后才能逐个执行，
            当前全部保持 DISCOVERY_REQUIRED / NOT_RUN。
          </p>
          <div className="discovery-import">
            <div>
              <span>发现报告</span>
              <StatusChip status={discovery ? "READY" : "NOT_RUN"} compact />
            </div>
            <label className={`button button-secondary ${importing ? "button-disabled" : ""}`}>
              <Icon name="file" size={15} />
              <span>{importing ? "服务端校验中…" : "导入发现报告 JSON"}</span>
              <input
                type="file"
                accept="application/json,.json"
                disabled={importing}
                onChange={(event) => void importDiscovery(event)}
              />
            </label>
            {discovery
              ? (
                <dl>
                  {Object.entries(discovery.verdict_counts).map(([verdict, count]) => (
                    <div key={verdict}><dt>{verdict}</dt><dd>{count}</dd></div>
                  ))}
                </dl>
              )
              : <small>
                  先执行 discover 子命令，用真实编译器分析器把每个单元判定为 READY 或给出精确的不支持原因；
                  报告由服务端按同一 Snapshot 摘要重新校验，判定为 READY 必须携带函数名、签名与分析器来源。
                </small>}
          </div>
          <div className="work-unit-toolbar">
            <label>
              <span>按路径筛选</span>
              <input
                value={workUnitFilter}
                onChange={(event) => { setWorkUnitFilter(event.target.value); setWorkUnitPage(0); }}
                maxLength={200}
                placeholder="src/main/java/..."
              />
            </label>
            <button type="button" className="button button-secondary" onClick={exportWorkUnits}>
              <Icon name="external" size={15} />导出 CSV
            </button>
          </div>
          {/* Horizontally scrollable regions must be keyboard reachable. */}
          <div className="work-unit-table" role="table" aria-label="整库工作单元列表" tabIndex={0}>
            <div className="work-unit-row work-unit-head" role="row">
              <span role="columnheader">源文件</span>
              <span role="columnheader">摘要</span>
              <span role="columnheader">字节</span>
              <span role="columnheader">发现判定</span>
              <span role="columnheader">函数 / 阻断原因</span>
            </div>
            {visibleWorkUnits.map((unit) => {
              const result = discoveryByUnit.get(unit.id);
              return (
                <div className="work-unit-row" role="row" key={unit.id}>
                  <span role="cell" title={unit.source_path}>{unit.source_path}</span>
                  <span role="cell">{unit.source_sha256.slice(0, 10)}…</span>
                  <span role="cell">{unit.source_bytes}</span>
                  <span role="cell">
                    {result ? `${result.verdict} · ${result.execution_status}` : `${unit.status} · ${unit.execution_status}`}
                  </span>
                  <span
                    role="cell"
                    title={result?.rejected_candidates.map((entry) => `${entry.candidate}: ${entry.reason}`).join("\n")}
                  >
                    {result?.verdict === "READY"
                      ? `${result.function_name}(${result.parameter_count}) · ${result.analyzer ?? ""}`
                      : result?.reason
                        ?? unit.unsupported_until_discovered.join("、")
                        ?? "待发现"}
                  </span>
                </div>
              );
            })}
            {visibleWorkUnits.length === 0 && (
              <div className="work-unit-row" role="row"><span role="cell">没有匹配当前筛选的工作单元。</span></div>
            )}
          </div>
          <div className="work-unit-pager">
            <button type="button" className="button button-ghost" disabled={workUnitPage === 0} onClick={() => setWorkUnitPage((page) => Math.max(0, page - 1))}>上一页</button>
            <small>{filteredWorkUnits.length} 个匹配 · 第 {workUnitPage + 1} / {workUnitPageCount} 页</small>
            <button type="button" className="button button-ghost" disabled={workUnitPage + 1 >= workUnitPageCount} onClick={() => setWorkUnitPage((page) => Math.min(workUnitPageCount - 1, page + 1))}>下一页</button>
          </div>
        </section>
      )}

      <div className={`feedback-toast ${feedback ? "visible" : ""}`} role="status" aria-live="polite" aria-atomic="true"><span><Icon name="check" size={17} /></span>{feedback}</div>
    </div>
  );
}
