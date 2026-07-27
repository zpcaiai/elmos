"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { generationStages, generationTargets } from "../lib/catalog";
import type {
  GenerationAnalysis,
  GenerationCapabilityResponse,
  GenerationJob,
  GenerationTargetId,
} from "../lib/contracts";
import { generationDeploymentGuidance } from "../lib/deploymentGuidance";
import { Icon, type IconName } from "../components/Icon";
import { RuntimeDeploymentGuide } from "../components/RuntimeDeploymentGuide";
import { StatusChip } from "../components/StatusChip";

type GenerationIntent = {
  name: string;
  namespace: string;
  description: string;
  entity: string;
  reviewer: string;
  targets: GenerationTargetId[];
  persistence: "in-memory" | "postgresql";
  authMode: "none" | "jwt" | "oidc";
};

type GenerationDraft = GenerationIntent & {
  id: string;
  createdAt: string;
};

type WorkflowCommand = {
  id: "analyze" | "approve" | "generate" | "verify" | "runtime";
  label: string;
  command: string;
};

type RunnerIdentity = {
  tenantId: string;
  actor: string;
};

type RunnerReadiness = {
  status: "READY" | "DISABLED" | "BLOCKED";
  isolation: "ROOTLESS_CONTAINER" | "HOST_DEVELOPMENT" | "NOT_CONFIGURED";
  storage: "READ_WRITE" | "NOT_RUN" | "BLOCKED";
  reason?: string;
};

const plannedAssets = [
  { icon: "workflow" as IconName, title: "需求与资产图", detail: "PSIR、Blueprint 与来源追踪" },
  { icon: "code" as IconName, title: "CRUD 与健康检查", detail: "多实体接口与 OpenAPI" },
  { icon: "test" as IconName, title: "测试与构建", detail: "单元测试、CI 与 Makefile" },
  { icon: "box" as IconName, title: "容器配置", detail: "非 root Dockerfile" },
  { icon: "cloud" as IconName, title: "运行清单", detail: "Kubernetes 探针与资源" },
  { icon: "file" as IconName, title: "证据与归档", detail: "逐目标结果与可交付 ZIP" },
];

const DRAFT_STORAGE_KEY = "elmos.project-generation-drafts.v1";
const generationTargetIds = new Set<GenerationTargetId>(generationTargets.map((target) => target.id));

function isStoredGenerationDraft(value: unknown): value is GenerationDraft {
  if (!value || typeof value !== "object") return false;
  const draft = value as Partial<GenerationDraft>;
  return typeof draft.id === "string" && draft.id.length <= 100
    && typeof draft.createdAt === "string" && !Number.isNaN(Date.parse(draft.createdAt))
    && typeof draft.name === "string" && draft.name.length <= 64
    && typeof draft.namespace === "string" && draft.namespace.length <= 200
    && typeof draft.description === "string" && draft.description.length <= 4_000
    && typeof draft.entity === "string" && draft.entity.length <= 64
    && typeof draft.reviewer === "string" && draft.reviewer.length <= 200
    && ["in-memory", "postgresql"].includes(draft.persistence ?? "in-memory")
    && ["none", "jwt", "oidc"].includes(draft.authMode ?? "none")
    && Array.isArray(draft.targets) && draft.targets.length > 0
    && draft.targets.every((target): target is GenerationTargetId => typeof target === "string" && generationTargetIds.has(target as GenerationTargetId));
}

function shellQuote(value: string) {
  return `'${value.replaceAll("'", "'\\''")}'`;
}

function runnerReasonMessage(reason?: string) {
  if (!reason) return "";
  if (reason.includes("ROOTLESS_CONTAINER_ENGINE_REQUIRED")) {
    return "当前容器引擎不是 rootless；生产一键运行保持关闭，请配置 rootless Podman/Docker。";
  }
  if (reason.includes("TOOLCHAIN_IMAGES_NOT_AVAILABLE_OFFLINE")) {
    return "精确工具链镜像尚未缓存，且构建网络为 none；请预加载 digest 镜像或审批受限构建网络。";
  }
  if (reason.includes("BUILD_NETWORK_NOT_APPROVED") || reason.includes("APPROVED_BUILD_NETWORK_MISSING")) {
    return "构建网络缺少 ELMOS 审批标签；运行器已拒绝未授权的网络出口。";
  }
  if (reason.includes("LOCAL_RUNNER_NOT_ENABLED")) {
    return "本地 Runner 未启用；仍可审阅并导出 Intent，执行入口保持关闭。";
  }
  return reason;
}

function buildWorkflowCommands(draft: GenerationIntent): WorkflowCommand[] {
  const workspace = `generated/${draft.name}`;
  return [
    {
      id: "analyze",
      label: "1 · 分析 Intent",
      command: "uv run elmos-project-synthesis analyze --intent project-intent.json --output synthesis-request.json",
    },
    {
      id: "approve",
      label: "2 · 审阅并批准",
      command: `uv run elmos-project-synthesis approve --request synthesis-request.json --actor ${shellQuote(draft.reviewer)} --output approved-request.json`,
    },
    {
      id: "generate",
      label: "3 · 生成工作区",
      command: `uv run elmos-project-synthesis generate --request approved-request.json --output ${shellQuote(workspace)}`,
    },
    {
      id: "verify",
      label: "4 · 真实构建验证",
      command: `uv run elmos-project-synthesis verify --workspace ${shellQuote(workspace)} --evidence verification.json`,
    },
    {
      id: "runtime",
      label: "5 · 生成运行计划",
      command: `uv run elmos-project-synthesis runtime-plan --workspace ${shellQuote(workspace)}`,
    },
  ];
}

export function ProjectGenerationStudio() {
  const [name, setName] = useState("order-service");
  const [namespace, setNamespace] = useState("io.elmos.orders");
  const [description, setDescription] = useState("提供订单创建、查询与状态管理的服务");
  const [entity, setEntity] = useState("order");
  const [reviewer, setReviewer] = useState("user:reviewer");
  const [targets, setTargets] = useState<GenerationTargetId[]>(["java", "python"]);
  const [persistence, setPersistence] = useState<"in-memory" | "postgresql">("in-memory");
  const [authMode, setAuthMode] = useState<"none" | "jwt" | "oidc">("none");
  const [draft, setDraft] = useState<GenerationDraft | null>(null);
  const [savedDrafts, setSavedDrafts] = useState<GenerationDraft[]>([]);
  const [draftsReady, setDraftsReady] = useState(false);
  const [capability, setCapability] = useState<GenerationCapabilityResponse | null>(null);
  const [capabilityError, setCapabilityError] = useState("");
  const [runnerReadiness, setRunnerReadiness] = useState<RunnerReadiness | null>(null);
  const [tenantId, setTenantId] = useState("local-dev");
  const [runnerToken, setRunnerToken] = useState("");
  const [analysis, setAnalysis] = useState<GenerationAnalysis | null>(null);
  const [approved, setApproved] = useState(false);
  const [job, setJob] = useState<GenerationJob | null>(null);
  const [recoveryJobId, setRecoveryJobId] = useState("");
  const [runnerBusy, setRunnerBusy] = useState(false);
  const [runtimeLanguage, setRuntimeLanguage] = useState<GenerationTargetId>("java");
  const [feedback, setFeedback] = useState("");
  const [targetError, setTargetError] = useState("");
  const feedbackTimer = useRef<number | null>(null);

  const selectedProfiles = useMemo(
    () => generationTargets.filter((profile) => targets.includes(profile.id)),
    [targets],
  );

  const preview = draft ?? {
    name,
    namespace,
    description,
    entity,
    reviewer,
    targets,
    persistence,
    authMode,
  };
  const previewProfiles = generationTargets.filter((profile) => preview.targets.includes(profile.id));
  const deploymentGuidance = capability?.deploymentGuidance ?? generationDeploymentGuidance();
  const workflowCommands = buildWorkflowCommands(preview);
  const workflowScript = workflowCommands.map((item) => item.command).join("\n");
  const runnerReady = capability?.localRunner.enabled === true
    && runnerReadiness?.status === "READY";
  const artifactGroups = useMemo(() => {
    const groups = new Map<string, GenerationJob["artifacts"]>();
    for (const artifact of job?.artifacts ?? []) {
      const root = artifact.path.includes("/") ? artifact.path.split("/", 1)[0] : "workspace";
      groups.set(root, [...(groups.get(root) ?? []), artifact]);
    }
    return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right));
  }, [job?.artifacts]);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/capabilities/generation", { cache: "no-store", signal: controller.signal })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("capability unavailable")))
      .then((payload: GenerationCapabilityResponse) => {
        setCapability(payload);
        setCapabilityError("");
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setCapability(null);
          setCapabilityError("无法读取项目生成能力契约；执行入口保持关闭，请检查 Web Console 服务端日志。");
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/health?probe=readiness", { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const payload = await response.json() as { localRunner?: RunnerReadiness };
        if (!payload.localRunner) throw new Error("runner readiness unavailable");
        return payload.localRunner;
      })
      .then(setRunnerReadiness)
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setRunnerReadiness({
            status: "BLOCKED",
            isolation: "NOT_CONFIGURED",
            storage: "BLOCKED",
            reason: "LOCAL_RUNNER_READINESS_UNAVAILABLE",
          });
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    try {
      const stored = JSON.parse(window.localStorage.getItem(DRAFT_STORAGE_KEY) ?? "[]") as unknown;
      if (Array.isArray(stored)) {
        setSavedDrafts(
          stored
            .filter(isStoredGenerationDraft)
            .map((item) => ({
              ...item,
              persistence: item.persistence ?? "in-memory",
              authMode: item.authMode ?? "none",
            }))
            .slice(0, 50),
        );
      }
    } catch {
      try { window.localStorage.removeItem(DRAFT_STORAGE_KEY); } catch { /* Storage may be disabled by policy. */ }
      setFeedback("本地草稿存储不可用；当前页面仍可准备一次性交接，但刷新后不会恢复。");
    } finally {
      setDraftsReady(true);
    }
  }, []);

  useEffect(() => {
    if (!draftsReady) return;
    try {
      window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(savedDrafts));
    } catch {
      announce("浏览器未允许保存本地草稿；请在离开页面前复制已锁定的交接命令。");
    }
  }, [draftsReady, savedDrafts]);

  useEffect(() => () => {
    if (feedbackTimer.current !== null) window.clearTimeout(feedbackTimer.current);
  }, []);

  useEffect(() => {
    if (!job || !runnerToken) return;
    const active = !["COMPLETED", "PARTIAL", "BLOCKED", "CANCELLED"].includes(job.status)
      || ["STARTING", "RUNNING"].includes(job.runtime.status);
    if (!active) return;
    const timer = window.setInterval(() => {
      void runnerRequest<GenerationJob>(`/api/generation/jobs/${job.id}`)
        .then(setJob)
        .catch(() => undefined);
    }, 1200);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.status, job?.runtime.status, runnerToken, tenantId]);

  function announce(message: string) {
    if (feedbackTimer.current !== null) window.clearTimeout(feedbackTimer.current);
    setFeedback(message);
    feedbackTimer.current = window.setTimeout(() => {
      setFeedback("");
      feedbackTimer.current = null;
    }, 4800);
  }

  function invalidateDraft() {
    setDraft(null);
    setAnalysis(null);
    setApproved(false);
  }

  function toggleTarget(id: GenerationTargetId) {
    if (persistence === "postgresql" && id !== "python") {
      setTargetError("PostgreSQL + JWT/OIDC 企业配置当前只对 Python 精确目标开放。");
      return;
    }
    setTargets((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
    setTargetError("");
    invalidateDraft();
  }

  function createDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (targets.length === 0) {
      setTargetError("请至少选择一个目标技术栈。");
      return;
    }
    if (
      persistence === "postgresql"
      && (targets.length !== 1 || targets[0] !== "python" || authMode === "none")
    ) {
      setTargetError("当前生产配置是精确的 Python + PostgreSQL + JWT/OIDC Profile；其他组合保持阻断。");
      return;
    }
    if (persistence === "in-memory" && authMode !== "none") {
      setTargetError("内存 Starter 只允许 auth=none；请选择 PostgreSQL 生产配置或恢复为无认证 Starter。");
      return;
    }
    const nextDraft: GenerationDraft = {
      id: crypto.randomUUID(),
      createdAt: new Date().toISOString(),
      name: name.trim(),
      namespace: namespace.trim(),
      description: description.trim(),
      entity: entity.trim(),
      reviewer: reviewer.trim(),
      targets,
      persistence,
      authMode,
    };
    setDraft(nextDraft);
    setAnalysis(null);
    setApproved(false);
    setSavedDrafts((current) => [nextDraft, ...current].slice(0, 50));
    announce(`“${nextDraft.name}”的五阶段生成交接已保存到此浏览器；仍未执行任何代码生成。`);
  }

  function restoreDraft(saved: GenerationDraft) {
    setName(saved.name);
    setNamespace(saved.namespace);
    setDescription(saved.description);
    setEntity(saved.entity);
    setReviewer(saved.reviewer);
    setTargets(saved.targets);
    setPersistence(saved.persistence ?? "in-memory");
    setAuthMode(saved.authMode ?? "none");
    setTargetError("");
    setDraft(saved);
    setAnalysis(null);
    setApproved(false);
    announce(`已恢复“${saved.name}”并重新锁定其受控命令。`);
  }

  function removeDraft(id: string) {
    const removed = savedDrafts.find((item) => item.id === id);
    setSavedDrafts((current) => current.filter((item) => item.id !== id));
    if (draft?.id === id) {
      setDraft(null);
      setAnalysis(null);
      setApproved(false);
    }
    if (removed) announce(`“${removed.name}”已从此浏览器删除。`);
  }

  async function copyText(value: string, successMessage: string) {
    if (!draft) {
      announce("请先提交并锁定当前计划预览，再复制受控命令。");
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      announce(successMessage);
    } catch {
      announce("浏览器未允许访问剪贴板，请手动选择并复制命令。");
    }
  }

  async function runnerRequest<T>(
    url: string,
    init?: RequestInit,
    identityOverride?: RunnerIdentity,
  ): Promise<T> {
    const isExistingJobRequest = Boolean(job && url.includes(`/jobs/${job.id}`));
    const actor = identityOverride?.actor
      ?? (isExistingJobRequest ? job!.actor : draft?.reviewer ?? reviewer);
    const requestTenantId = identityOverride?.tenantId
      ?? (isExistingJobRequest ? job!.tenantId : tenantId);
    const response = await fetch(url, {
      ...init,
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${runnerToken}`,
        "X-ELMOS-Tenant": requestTenantId,
        "X-ELMOS-Actor": actor,
        ...init?.headers,
      },
    });
    const payload = await response.json() as T & { reason?: string };
    if (!response.ok) throw new Error(payload.reason ?? `HTTP_${response.status}`);
    return payload;
  }

  async function recoverJob() {
    const exactJobId = recoveryJobId.trim().toLowerCase();
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(exactJobId)) {
      announce("请输入完整、有效的任务 UUID。");
      return;
    }
    if (!runnerToken) {
      announce("恢复任务需要重新输入短期 Runner 令牌；令牌不会持久化。");
      return;
    }
    setRunnerBusy(true);
    try {
      const next = await runnerRequest<GenerationJob>(
        `/api/generation/jobs/${exactJobId}`,
        undefined,
        { tenantId: tenantId.trim(), actor: reviewer.trim() },
      );
      setJob(next);
      setRecoveryJobId(next.id);
      setRuntimeLanguage(next.runtime.language ?? next.runtime.plans[0]?.language ?? "java");
      announce(`已按租户与操作者身份恢复任务 ${next.id.slice(0, 8)}；令牌仍只保存在页面内存。`);
    } catch (error) {
      announce(`任务恢复被阻断：${error instanceof Error ? error.message : "UNKNOWN_ERROR"}`);
    } finally {
      setRunnerBusy(false);
    }
  }

  async function analyzeDraft() {
    if (!draft) {
      announce("请先锁定当前项目意图。");
      return;
    }
    if (!runnerToken) {
      announce("请输入本地 Runner 的短期访问令牌后再分析需求。");
      return;
    }
    setRunnerBusy(true);
    setApproved(false);
    try {
      const result = await runnerRequest<GenerationAnalysis>("/api/generation/analyze", {
        method: "POST",
        body: JSON.stringify({
          name: draft.name,
          namespace: draft.namespace,
          description: draft.description,
          entity: draft.entity,
          targets: draft.targets,
          persistence: draft.persistence,
          authMode: draft.authMode,
        }),
      });
      setAnalysis(result);
      announce(
        result.request.open_questions.length > 0
          ? `需求已整理，但仍有 ${result.request.open_questions.length} 个开放问题，暂不能批准执行。`
          : `需求已整理为 ${result.request.entities.length} 个实体、${result.request.requirements.length} 项需求，请审阅后批准。`,
      );
    } catch (error) {
      setAnalysis(null);
      announce(`需求分析被阻断：${error instanceof Error ? error.message : "UNKNOWN_ERROR"}`);
    } finally {
      setRunnerBusy(false);
    }
  }

  async function executeJob() {
    if (!draft || !analysis || analysis.request.open_questions.length > 0 || !approved) {
      announce("请先完成需求分析、处理开放问题并批准当前锁定计划。");
      return;
    }
    if (!runnerToken) {
      announce("请输入本地 Runner 的短期访问令牌；令牌只保存在当前页面内存中。");
      return;
    }
    setRunnerBusy(true);
    try {
      const next = await runnerRequest<GenerationJob>("/api/generation/jobs", {
        method: "POST",
        body: JSON.stringify({
          name: draft.name,
          namespace: draft.namespace,
          description: draft.description,
          entity: draft.entity,
          reviewer: draft.reviewer,
          targets: draft.targets,
          persistence: draft.persistence,
          authMode: draft.authMode,
          approved: true,
          analysisDigest: analysis.requestDigest,
        }),
      });
      setJob(next);
      setRuntimeLanguage(draft.targets[0]);
      announce(`受控任务 ${next.id.slice(0, 8)} 已进入执行队列。`);
    } catch (error) {
      announce(`执行被阻断：${error instanceof Error ? error.message : "UNKNOWN_ERROR"}`);
    } finally {
      setRunnerBusy(false);
    }
  }

  async function postJobAction(action: "cancel" | "run" | "stop") {
    if (!job) return;
    setRunnerBusy(true);
    try {
      const next = await runnerRequest<GenerationJob>(
        `/api/generation/jobs/${job.id}/${action}`,
        {
          method: "POST",
          body: action === "run" ? JSON.stringify({ language: runtimeLanguage }) : "{}",
        },
      );
      setJob(next);
      announce(action === "cancel" ? "任务已请求取消。" : action === "run" ? "运行进程已启动，正在等待健康探针。" : "运行进程已停止。");
    } catch (error) {
      announce(`操作被阻断：${error instanceof Error ? error.message : "UNKNOWN_ERROR"}`);
    } finally {
      setRunnerBusy(false);
    }
  }

  async function downloadArtifact() {
    if (!job?.artifactReady) return;
    try {
      const response = await fetch(`/api/generation/jobs/${job.id}/artifact`, {
        cache: "no-store",
        headers: {
          "Authorization": `Bearer ${runnerToken}`,
          "X-ELMOS-Tenant": job.tenantId,
          "X-ELMOS-Actor": job.actor,
        },
      });
      if (!response.ok) {
        const payload = await response.json() as { reason?: string };
        throw new Error(payload.reason ?? `HTTP_${response.status}`);
      }
      const expectedDigest = response.headers.get("x-content-sha256");
      const blob = await response.blob();
      const actualDigest = [...new Uint8Array(await crypto.subtle.digest(
        "SHA-256",
        await blob.arrayBuffer(),
      ))].map((value) => value.toString(16).padStart(2, "0")).join("");
      if (
        !expectedDigest
        || expectedDigest !== actualDigest
        || expectedDigest !== job.artifactSha256
      ) {
        throw new Error("ARTIFACT_INTEGRITY_MISMATCH");
      }
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${draft?.name ?? "generated-project"}.zip`;
      anchor.click();
      URL.revokeObjectURL(url);
      announce(
        job.status === "COMPLETED"
          ? "归档摘要已复算并下载；本次目标构建与启动探针均通过。"
          : "归档摘要已复算并下载；其中仍含 PARTIAL / NOT_RUN 证据，请先查看任务结果。",
      );
    } catch (error) {
      announce(`归档下载失败：${error instanceof Error ? error.message : "UNKNOWN_ERROR"}`);
    }
  }

  function downloadIntent() {
    if (!draft) {
      announce("请先提交并锁定项目意图，再导出结构化 Intent。");
      return;
    }
    const intent = {
      schema_version: "1.1.0",
      name: draft.name,
      namespace: draft.namespace,
      description: draft.description,
      entity: draft.entity,
      languages: draft.targets,
      project_kind: "api",
      persistence: draft.persistence,
      auth_mode: draft.authMode,
      business_rules: [],
      permissions: [],
      ui_handoff: {
        created_at: draft.createdAt,
        reviewer: draft.reviewer,
        execution_status: "NOT_RUN",
        certification_status: "NOT_CERTIFIED",
      },
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(intent, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "project-intent.json";
    anchor.click();
    URL.revokeObjectURL(url);
    announce("project-intent.json 已导出；请在受控终端从 Analyze 阶段开始。");
  }

  return (
    <div className="page-stack generation-page">
      <section className="page-header generation-header">
        <div>
          <span className="overline">PROJECT SYNTHESIS · B46–B80</span>
          <h1>多语言项目生成</h1>
          <p>用同一份受审项目意图生成 Java、Python、C#、TypeScript、Go、Kotlin、PHP 与 Rust 工程；逐目标构建、探针和证据互不替代。</p>
        </div>
        <div className="generation-header-status"><StatusChip status={draft ? "REVIEW" : "DRAFT"} /><StatusChip status={job?.status ?? "NOT_RUN"} /></div>
      </section>

      <section className="metric-grid metric-grid-four" aria-label="项目生成能力摘要">
        <article className="metric-card"><span>项目合成 Skills</span><strong>{capability?.projectSkillCount ?? 417}</strong><small>B46–B80 结构化能力</small></article>
        <article className="metric-card"><span>精确目标栈</span><strong>{capability?.targets.length ?? generationTargets.length}</strong><small>8 个独立 emitter / verifier</small></article>
        <article className="metric-card"><span>已选目标</span><strong>{selectedProfiles.length}</strong><small>一个意图，多份独立工程</small></article>
        <article className="metric-card"><span>本地 Runner</span><strong className={`metric-word ${runnerReady ? "" : "warning-text"}`}>{runnerReady ? "READY" : runnerReadiness?.status ?? "CHECKING"}</strong><small>{runnerReadiness?.isolation ?? capability?.localRunner.isolation ?? "NOT_CONFIGURED"} · 持久恢复</small></article>
      </section>

      <section className="source-notice generation-notice" role={capabilityError ? "alert" : "status"}>
        <Icon name="lock" size={16} />
        <span>{capabilityError || runnerReasonMessage(runnerReadiness?.reason) || capability?.note || "正在读取仓库内 Project Synthesis 契约与本地 Runner 状态。"}</span>
        <StatusChip status={capabilityError || runnerReadiness?.status === "BLOCKED" ? "BLOCKED" : capability?.source ?? "REPOSITORY_CONTRACT"} compact />
      </section>

      <div className="generation-layout">
        <form className="surface-card generation-form" onSubmit={createDraft} aria-labelledby="generation-form-title">
          <div className="generation-section-heading">
            <div><span className="overline">PROJECT INTENT</span><h2 id="generation-form-title">描述并审阅项目意图</h2></div>
            <span className="step-label">01 / 02</span>
          </div>

          <div className="generation-fields">
            <label className="generation-field"><span>项目名称</span><input value={name} onChange={(event) => { setName(event.target.value); invalidateDraft(); }} required pattern={"[a-z][a-z0-9\\-]{1,62}[a-z0-9]"} autoComplete="off" aria-describedby="project-name-hint" /><small id="project-name-hint">小写字母、数字与连字符，例如 order-service</small></label>
            <label className="generation-field"><span>命名空间</span><input value={namespace} onChange={(event) => { setNamespace(event.target.value); invalidateDraft(); }} required pattern={"[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+"} autoComplete="off" aria-describedby="namespace-hint" /><small id="namespace-hint">稳定的点分命名空间，例如 io.elmos.orders</small></label>
            <label className="generation-field generation-field-wide"><span>项目说明</span><textarea value={description} onChange={(event) => { setDescription(event.target.value); invalidateDraft(); }} required rows={7} maxLength={4_000} aria-describedby="description-hint" /><small id="description-hint">最多 4,000 字；可写“实体 / 字段 / 关系 / 规则 / 权限”标记，不要粘贴凭证、生产数据或客户代码。</small></label>
            <label className="generation-field"><span>核心实体</span><input value={entity} onChange={(event) => { setEntity(event.target.value); invalidateDraft(); }} required pattern={"[a-z][a-z0-9_]{1,62}[a-z0-9]"} autoComplete="off" aria-describedby="entity-hint" /><small id="entity-hint">可在描述中继续写“实体: order, customer”和字段定义；默认生成内存 API starter。</small></label>
            <label className="generation-field"><span>审批者标识</span><input value={reviewer} onChange={(event) => { setReviewer(event.target.value); invalidateDraft(); }} required pattern={"[A-Za-z0-9](?:[A-Za-z0-9._:@]|/|-){2,199}"} autoComplete="off" aria-describedby="reviewer-hint" /><small id="reviewer-hint">必须与短期 Runner 凭证绑定的 Actor 完全一致；不填写密钥或邮箱凭证。</small></label>
            <label className="generation-field" htmlFor="generation-persistence">
              <span>数据配置</span>
              <select id="generation-persistence" value={persistence} onChange={(event) => {
                const next = event.target.value as "in-memory" | "postgresql";
                setPersistence(next);
                if (next === "in-memory") setAuthMode("none");
                else {
                  setTargets(["python"]);
                  if (authMode === "none") setAuthMode("jwt");
                }
                invalidateDraft();
              }}>
                <option value="in-memory">内存 Starter</option>
                <option value="postgresql">PostgreSQL 17.5 生产配置</option>
              </select>
              <small>生产配置生成前向迁移、RLS、恢复与真实集成测试；目前精确支持 Python。</small>
            </label>
            <label className="generation-field" htmlFor="generation-auth-mode">
              <span>认证配置</span>
              <select id="generation-auth-mode" value={authMode} disabled={persistence === "in-memory"} onChange={(event) => {
                setAuthMode(event.target.value as "none" | "jwt" | "oidc");
                invalidateDraft();
              }}>
                <option value="none">无认证（仅 Starter）</option>
                <option value="jwt">JWT HS256 + Secret 文件</option>
                <option value="oidc">OIDC + 受控 JWKS 文件</option>
              </select>
              <small>身份必须包含 issuer、audience、subject、tenant_id 与 roles；权限默认拒绝。</small>
            </label>
            <label className="generation-field"><span>租户标识</span><input value={tenantId} onChange={(event) => setTenantId(event.target.value)} required pattern={"[a-z][a-z0-9\\-]{2,62}"} autoComplete="off" aria-describedby="tenant-hint" /><small id="tenant-hint">必须与短期 Runner 凭证绑定的租户完全一致；请求头不能自行切换租户。</small></label>
            <label className="generation-field"><span>本地 Runner 令牌</span><input type="password" value={runnerToken} onChange={(event) => setRunnerToken(event.target.value)} minLength={24} autoComplete="off" aria-describedby="runner-token-hint" /><small id="runner-token-hint">仅保存在当前页面内存，不写入草稿、日志或生成项目。</small></label>
          </div>

          <fieldset className="target-fieldset" aria-describedby="target-hint target-error">
            <legend><span><span className="overline">EXACT TARGETS</span><strong>选择目标技术栈</strong></span><span className="step-label">02 / 02</span></legend>
            <p id="target-hint">每个目标都有独立模板、工具链、构建和启动探针；缺失工具只会令该目标保持 NOT_RUN。</p>
            <div className="target-grid">
              {generationTargets.map((profile) => {
                const checked = targets.includes(profile.id);
                return (
                  <label className={`target-card target-${profile.accent} ${checked ? "selected" : ""}`} key={profile.id}>
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={persistence === "postgresql" && profile.id !== "python"}
                      onChange={() => toggleTarget(profile.id)}
                    />
                    <span className="target-check"><Icon name="check" size={13} /></span>
                    <span className="target-icon"><Icon name={profile.icon} size={21} /></span>
                    <span className="target-copy"><strong>{profile.language} {profile.runtime}</strong><small>{profile.framework} · {profile.maturity}</small><em>{profile.sourceSkill} · :{profile.port}</em></span>
                  </label>
                );
              })}
            </div>
            <span className="field-error" id="target-error" role="alert">{targetError}</span>
          </fieldset>

          <section className="generation-draft-library" aria-labelledby="generation-drafts-title">
            <div className="generation-section-heading compact">
              <div><span className="overline">LOCAL REVIEW DRAFTS</span><h3 id="generation-drafts-title">已保存的生成交接</h3></div>
              <span>{savedDrafts.length} / 50</span>
            </div>
            {savedDrafts.length === 0 ? (
              <p className="generation-drafts-empty">提交有效项目意图后，草稿会保存在当前浏览器，刷新页面仍可恢复。</p>
            ) : (
              <div className="generation-draft-list">
                {savedDrafts.map((saved) => (
                  <article className={`generation-draft-row ${draft?.id === saved.id ? "active" : ""}`} key={saved.id}>
                    <span className="capability-icon accent-cyan"><Icon name="repository" size={17} /></span>
                    <div><strong>{saved.name}</strong><small>{saved.targets.join(" + ")} · {new Date(saved.createdAt).toLocaleString("zh-CN")}</small></div>
                    <StatusChip status={draft?.id === saved.id ? "REVIEW" : "DRAFT"} compact />
                    <button type="button" className="button button-secondary compact-button" onClick={() => restoreDraft(saved)} aria-label={`恢复草稿 ${saved.name}`}>恢复</button>
                    <button type="button" className="icon-button" onClick={() => removeDraft(saved.id)} aria-label={`删除草稿 ${saved.name}`}><Icon name="close" size={13} /></button>
                  </article>
                ))}
              </div>
            )}
          </section>

          <div className="planned-assets" aria-labelledby="assets-title">
            <div className="generation-section-heading compact"><div><span className="overline">PLANNED ASSETS</span><h3 id="assets-title">生成计划包含</h3></div><span>{job ? job.status : "实际未生成"}</span></div>
            <div className="asset-grid">{plannedAssets.map((asset) => <div className="asset-item" key={asset.title}><span><Icon name={asset.icon} size={17} /></span><div><strong>{asset.title}</strong><small>{asset.detail}</small></div></div>)}</div>
          </div>

          <section className="generation-analysis" aria-labelledby="generation-analysis-title">
            <div className="generation-section-heading compact">
              <div><span className="overline">REQUIREMENT REVIEW</span><h3 id="generation-analysis-title">结构化需求审阅</h3></div>
              <StatusChip status={analysis ? (analysis.request.open_questions.length ? "BLOCKED" : "REVIEW") : "NOT_RUN"} compact />
            </div>
            {!analysis ? (
              <p className="generation-drafts-empty">锁定 Intent 后运行需求分析；批准前必须查看实体、字段、规则、权限和开放问题。</p>
            ) : (
              <div className="generation-analysis-grid">
                <div className="generation-analysis-card">
                  <strong>实体与字段 · {analysis.request.entities.length}</strong>
                  {analysis.request.entities.map((item) => (
                    <div className="analysis-entity" key={item.singular}>
                      <span>{item.singular} → {item.plural}</span>
                      <small>{item.fields.map((field) => `${field.name}:${field.type}${field.required ? "!" : "?"}`).join(" · ")}</small>
                    </div>
                  ))}
                </div>
                <div className="generation-analysis-card">
                  <strong>需求与规则</strong>
                  <small>{analysis.request.requirements.length} 项需求 · {analysis.request.acceptance_criteria.length} 项验收条件 · {analysis.request.business_rules.length} 条业务规则</small>
                  <span>审阅摘要 · {analysis.requestDigest.slice(0, 16)}</span>
                  {analysis.request.business_rules.map((rule) => <span key={rule.id}>{rule.id} · {rule.statement}</span>)}
                </div>
                <div className="generation-analysis-card">
                  <strong>关系与权限</strong>
                  <small>
                    {analysis.request.relations.length} 条关系 · {analysis.request.permissions.length} 条声明性权限；
                    {analysis.request.project.auth_mode === "none"
                      ? "当前无认证，仅用于本地 Starter。"
                      : `当前 ${analysis.request.project.auth_mode.toUpperCase()} 默认拒绝并执行租户/权限契约。`}
                  </small>
                  {analysis.request.relations.map((relation) => (
                    <span key={`${relation.source}-${relation.source_field ?? ""}-${relation.target}-${relation.target_field ?? ""}`}>
                      {relation.source}{relation.source_field ? `.${relation.source_field}` : ""} {relation.kind} {relation.target}{relation.target_field ? `.${relation.target_field}` : ""}
                    </span>
                  ))}
                  {analysis.request.relations.length === 0 && <span>当前未声明实体关系</span>}
                  {analysis.request.permissions.map((permission) => (
                    <span key={`${permission.actor}-${permission.action}-${permission.resource}-${permission.effect}`}>
                      {permission.actor} · {permission.effect} {permission.action} · {permission.resource}
                    </span>
                  ))}
                </div>
                <div className={`generation-analysis-card ${analysis.request.open_questions.length ? "analysis-blocked" : ""}`}>
                  <strong>开放问题 · {analysis.request.open_questions.length}</strong>
                  {analysis.request.open_questions.map((question) => <span key={question.id}>{question.id} · {question.question}</span>)}
                  {analysis.request.open_questions.length === 0 && <span>无阻断性开放问题，可以进入显式批准。</span>}
                </div>
              </div>
            )}
          </section>

          <section className="generation-runner" aria-labelledby="generation-runner-title">
            <div className="generation-section-heading compact">
              <div><span className="overline">GOVERNED LOCAL RUNNER</span><h3 id="generation-runner-title">执行、验证与一键运行</h3></div>
              <StatusChip status={job?.status ?? (runnerReady ? "READY" : runnerReadiness?.status === "BLOCKED" ? "BLOCKED" : "NOT_CONFIGURED")} compact />
            </div>
            <div className="generation-job-recovery">
              <label>
                <span>恢复任务 ID</span>
                <input
                  value={recoveryJobId}
                  onChange={(event) => setRecoveryJobId(event.target.value)}
                  placeholder="完整任务 UUID"
                  inputMode="text"
                  autoComplete="off"
                  maxLength={36}
                />
              </label>
              <button className="button button-secondary" type="button" disabled={runnerBusy || !runnerReady} onClick={() => void recoverJob()}>
                <Icon name="refresh" size={15} />恢复任务
              </button>
              <small>使用当前租户、审批者与重新输入的短期令牌恢复服务端原子持久化任务；浏览器不保存令牌。</small>
            </div>
            <label className="generation-approval">
              <input type="checkbox" checked={approved} onChange={(event) => setApproved(event.target.checked)} disabled={!draft || !analysis || analysis.request.open_questions.length > 0 || runnerBusy} />
              <span><strong>我已审阅结构化需求，并批准当前 Intent 在本机受控 Runner 中执行</strong><small>只允许固定的 Project Synthesis 子命令；任务失败、重启或工具链缺失时保持 BLOCKED / PARTIAL。</small></span>
            </label>
            {job && (
              <div className="generation-job" aria-live="polite">
                <div className="generation-job-summary">
                  <div><span>任务</span><strong>{job.id.slice(0, 8)}</strong></div>
                  <div><span>阶段</span><strong>{job.stage}</strong></div>
                  <div><span>结果</span><strong>{job.resultStatus}</strong></div>
                  <div><span>运行</span><strong>{job.runtime.status}</strong></div>
                  <div><span>隔离</span><strong>{job.runtime.executor ?? capability?.localRunner.isolation ?? "NOT_CONFIGURED"}</strong></div>
                  {job.artifactSha256 && <div><span>归档摘要</span><strong>{job.artifactSha256.slice(0, 12)}</strong></div>}
                </div>
                <div className="generation-progress" role="progressbar" aria-valuenow={job.progress} aria-valuemin={0} aria-valuemax={100} aria-label="任务进度"><i style={{ width: `${job.progress}%` }} /></div>
                {job.reason && <p className="generation-job-reason" role="alert">{runnerReasonMessage(job.reason)}</p>}
                <pre className="generation-job-logs" tabIndex={0} aria-label="任务日志">{job.logs.slice(-60).map((entry) => `[${new Date(entry.at).toLocaleTimeString("zh-CN")}] ${entry.stream}: ${entry.message}`).join("\n") || "等待任务日志…"}</pre>
                {job.artifacts.length > 0 && (
                  <div className="generation-artifact-tree" aria-label="生成文件树">
                    <div><strong>生成文件树</strong><span>{job.artifacts.length} 个内容寻址文件</span></div>
                    {artifactGroups.map(([root, artifacts]) => (
                      <details key={root}>
                        <summary><span>{root}/</span><small>{artifacts.length}</small></summary>
                        <ul>{artifacts.map((artifact) => <li key={artifact.path}><code>{artifact.path}</code><span>{artifact.sha256.slice(0, 12)}</span></li>)}</ul>
                      </details>
                    ))}
                  </div>
                )}
                <div className="generation-runtime-controls">
                  <label><span>运行目标</span><select value={runtimeLanguage} onChange={(event) => setRuntimeLanguage(event.target.value as GenerationTargetId)} disabled={["STARTING", "RUNNING"].includes(job.runtime.status)}>{job.runtime.plans.map((plan) => <option key={plan.language} value={plan.language}>{plan.language} · :{plan.port}</option>)}</select></label>
                  <button className="button button-secondary" type="button" disabled={runnerBusy || job.runtime.plans.length === 0 || ["STARTING", "RUNNING"].includes(job.runtime.status)} onClick={() => void postJobAction("run")}><Icon name="play" size={15} />一键运行</button>
                  <button className="button button-secondary" type="button" disabled={runnerBusy || !["STARTING", "RUNNING"].includes(job.runtime.status)} onClick={() => void postJobAction("stop")}><Icon name="close" size={15} />停止</button>
                  <button className="button button-primary" type="button" disabled={!job.artifactReady} onClick={() => void downloadArtifact()}><Icon name="file" size={15} />下载归档</button>
                </div>
              </div>
            )}
          </section>

          <div className="generation-submit-row">
            <div><Icon name="lock" size={16} /><span><strong>显式批准后才允许执行</strong><small>未配置 Runner 时仍可导出 Intent 与 CLI 交接</small></span></div>
            <div className="generation-submit-actions">
              {job && !["COMPLETED", "PARTIAL", "BLOCKED", "CANCELLED"].includes(job.status) && <button className="button button-secondary" type="button" disabled={runnerBusy} onClick={() => void postJobAction("cancel")}><Icon name="close" size={16} />取消任务</button>}
              <button className="button button-secondary" type="button" disabled={!draft} onClick={downloadIntent}><Icon name="external" size={16} />导出 Intent</button>
              <button className="button button-secondary" type="submit"><Icon name="spark" size={16} />锁定生成计划</button>
              <button className="button button-secondary" type="button" disabled={!draft || !runnerReady || runnerBusy} onClick={() => void analyzeDraft()}><Icon name="workflow" size={16} />分析并整理需求</button>
              <button className="button button-primary" type="button" disabled={!draft || !analysis || analysis.request.open_questions.length > 0 || !approved || !runnerReady || runnerBusy} onClick={() => void executeJob()}><Icon name="play" size={16} />执行并验证</button>
            </div>
          </div>
        </form>

        <aside className="generation-preview" aria-label="生成计划预览">
          <div className="generation-preview-hero">
            <div className="preview-status-row"><span className="overline">GOVERNED PLAN PREVIEW</span><StatusChip status={draft ? "REVIEW" : "DRAFT"} compact /></div>
            <span className="preview-project-icon"><Icon name="repository" size={24} /></span>
            <h2>{preview.name || "未命名项目"}</h2>
            <p>{preview.description || "填写项目说明后，这里会显示生成计划摘要。"}</p>
            <div className="preview-tags"><span>{preview.entity || "未指定实体"}</span><span>{preview.namespace || "未指定命名空间"}</span><span>{preview.reviewer || "未指定审批者"}</span></div>
          </div>

          <div className="preview-section">
            <div className="preview-section-title"><span>目标输出</span><b>{previewProfiles.length}</b></div>
            <div className="preview-target-list">
              {previewProfiles.map((profile) => <div key={profile.id}><span className={`mini-target target-${profile.accent}`}><Icon name={profile.icon} size={15} /></span><span><strong>{profile.language} {profile.runtime}</strong><small>{profile.framework} · {profile.verificationStatus}</small></span><em>:{profile.port}</em></div>)}
              {previewProfiles.length === 0 && <p className="preview-empty">尚未选择目标技术栈。</p>}
            </div>
          </div>

          <div className="preview-section pipeline-section">
            <div className="preview-section-title"><span>受控生成阶段</span><b>{generationStages.length}</b></div>
            <ol className="generation-pipeline">
              {generationStages.map((phase, index) => <li key={phase.batch}><i>{index + 1}</i><span><strong>{phase.title}</strong><small>{phase.batch} · {phase.detail}</small></span></li>)}
            </ol>
          </div>

          <div className="preview-command">
            <div><span>完整 CLI 交接</span><button type="button" disabled={!draft} onClick={() => copyText(workflowScript, "五阶段 CLI 命令已复制，请在项目合成引擎目录中依次执行。")}><Icon name="copy" size={13} />复制全部</button></div>
            <ol className="workflow-command-list">
              {workflowCommands.map((item) => (
                <li className="workflow-command-item" key={item.id}>
                  <div><strong>{item.label}</strong><button type="button" disabled={!draft} aria-label={`复制${item.label}命令`} onClick={() => copyText(item.command, `${item.label}命令已复制。`)}><Icon name="copy" size={12} />复制</button></div>
                  <code>{item.command}</code>
                </li>
              ))}
            </ol>
            <small>{draft ? "先导出 project-intent.json；命令与 Project Synthesis 1.2.0 引擎契约对应，任何一步失败都应停止。" : "先提交有效表单以锁定 Intent 和命令，防止复制仍在变化的未审阅输入。"}</small>
          </div>

          <div className="generation-boundary">
            <Icon name="shield" size={19} />
            <div><strong>证据边界保持关闭</strong><small>数据库迁移、身份/租户执行、监控、备份恢复与隔离运行配置已生成；真实云部署、恢复演练、人工辅助技术验收、独立用户验收和外部认证仍是 NOT_RUN。</small></div>
            <StatusChip status="NOT_CERTIFIED" compact />
          </div>
        </aside>
      </div>

      <RuntimeDeploymentGuide
        id="generation-runtime-deployment"
        guidance={deploymentGuidance}
        selectedTargets={preview.targets}
      />

      <div className={`feedback-toast ${feedback ? "visible" : ""}`} role="status" aria-live="polite" aria-atomic="true"><span><Icon name="check" size={17} /></span>{feedback}</div>
    </div>
  );
}
